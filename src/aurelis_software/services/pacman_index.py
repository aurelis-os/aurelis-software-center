"""Pacman package index (Phase 6, FEAT-002).

Parses pacman -Si output into a SQLite database with an FTS5 table on
``name`` and ``description``. Pure stdlib (``sqlite3``, ``subprocess``) and
no Qt, so it can run in a worker thread without a ``QApplication`` and is
testable headlessly.

The index tracks the max mtime of /var/lib/pacman/sync/*.db files to detect
when a rebuild is needed.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BATCH_SIZE = 100
_SCHEMA_VERSION = "1"

# Strip FTS5 query-syntax characters so the user's raw input cannot raise
# or be mis-parsed; keeps unicode word characters (letters/digits incl.
# Greek) and whitespace, then we build a prefix-AND query.
_FTS_KEEP = re.compile(r"[^\w\s]")

__all__ = ["PacmanIndex"]


def _default_runner(cmd: list[str]) -> tuple[int, str, str]:
    """Default runner using subprocess.run."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result.returncode, result.stdout, result.stderr


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS packages ("
        "name TEXT PRIMARY KEY, version TEXT, description TEXT, "
        "repo TEXT, groups TEXT, installed_size TEXT, download_size TEXT, "
        "url TEXT, license TEXT, depends TEXT, raw TEXT)"
    )
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS packages_fts USING fts5(name, description)")
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    raw = json.loads(row[10]) if row[10] else {}
    return {
        "name": row[0],
        "version": row[1],
        "description": row[2] or "",
        "repo": row[3] or "",
        "groups": json.loads(row[4]) if row[4] else [],
        "installed_size": row[5] or "",
        "download_size": row[6] or "",
        "url": row[7] or "",
        "license": row[8] or "",
        "depends": json.loads(row[9]) if row[9] else [],
        "raw": raw,
    }


def _fts_query(query: str) -> str:
    """Build a safe FTS5 prefix-AND match expression; '' means no query."""
    cleaned = _FTS_KEEP.sub(" ", query).strip()
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return ""
    return " ".join(f"{t}*" for t in tokens)


class PacmanIndex:
    """SQLite + FTS5 index over pacman -Si output.

    The connection is opened per call (no long-lived handle), so ``rebuild``
    can run in a worker thread and ``search``/``get`` can run in the UI
    thread without cross-thread issues.
    """

    def __init__(
        self,
        db_path: Path | str,
        sync_dir: Path | str,
        runner: Callable[[list[str]], tuple[int, str, str]] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.sync_dir = Path(sync_dir)
        self.runner = runner if runner is not None else _default_runner

    def needs_rebuild(self) -> bool:
        """True when the index is missing or the sync_dir mtime changed."""
        if not self.sync_dir.exists():
            return False
        if not self.db_path.exists():
            return True

        conn = sqlite3.connect(self.db_path)
        try:
            return self._check_rebuild_needed(conn)
        finally:
            conn.close()

    def _check_rebuild_needed(self, conn: sqlite3.Connection) -> bool:
        """Check if rebuild is needed based on schema and mtime."""
        if not _table_exists(conn, "meta") or not _table_exists(conn, "packages_fts"):
            return True

        row = conn.execute("SELECT value FROM meta WHERE key='max_sync_mtime'").fetchone()
        if not row:
            return True

        try:
            stored = int(row[0])
        except (TypeError, ValueError):
            return True

        current_mtime = self._get_max_sync_mtime()
        return current_mtime is not None and stored != current_mtime

    def _get_max_sync_mtime(self) -> int | None:
        """Get max mtime of *.db files in sync_dir, or None if no files."""
        db_files = list(self.sync_dir.glob("*.db"))
        if not db_files:
            return None
        return max(f.stat().st_mtime_ns for f in db_files)

    def rebuild(self, progress_cb: Callable[[float], None] | None = None) -> None:
        """Parse pacman -Si output and repopulate the index.

        *progress_cb* is called with a fraction in [0.0, 1.0] every
        ``_BATCH_SIZE`` entries and once with 1.0 at the end. The whole
        population runs inside one SQLite transaction; on any error the
        previous index is left untouched.
        """
        # Import here to allow graceful degradation when module unavailable
        from aurelis_software.core import pacman_parser

        returncode, stdout, stderr = self.runner(["pacman", "-Si"])
        if returncode != 0:
            msg = f"pacman -Si failed: {stderr}"
            raise RuntimeError(msg)

        packages = pacman_parser.parse_si_output(stdout)
        if not packages:
            log.warning("No packages found in pacman -Si output")

        max_mtime = self._get_max_sync_mtime() or 0

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.isolation_level = None  # manage the transaction explicitly
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            _create_schema(conn)
            conn.execute("BEGIN")
            try:
                self._populate_db(conn, packages, progress_cb)
                self._store_metadata(conn, max_mtime)
                conn.execute("COMMIT")
                if progress_cb is not None:
                    progress_cb(1.0)
            except (sqlite3.Error, ValueError):
                conn.execute("ROLLBACK")
                raise
            log.info("Pacman index rebuilt: %d packages", len(packages))
        finally:
            conn.close()

    def _populate_db(
        self,
        conn: sqlite3.Connection,
        packages: list[dict],
        progress_cb: Callable[[float], None] | None,
    ) -> None:
        """Populate database with parsed packages."""
        conn.execute("DELETE FROM packages_fts")
        conn.execute("DELETE FROM packages")

        packages_batch: list[tuple[Any, ...]] = []
        fts_batch: list[tuple[Any, ...]] = []
        processed = 0

        for pkg in packages:
            name = pkg.get("name", "")
            if not name:
                continue

            # Extract fields
            version = pkg.get("version", "")
            description = pkg.get("description", "")
            repo = pkg.get("repository", "")
            groups = pkg.get("groups", [])
            installed_size = pkg.get("installed_size", "")
            download_size = pkg.get("download_size", "")
            url = pkg.get("url", "")
            license_val = pkg.get("licenses", "")
            depends = pkg.get("depends_on", [])

            packages_batch.append(
                (
                    name,
                    version,
                    description,
                    repo,
                    json.dumps(groups),
                    installed_size,
                    download_size,
                    url,
                    license_val,
                    json.dumps(depends),
                    json.dumps(pkg),
                )
            )
            fts_batch.append((name, description))
            processed += 1

            if len(packages_batch) >= _BATCH_SIZE:
                self._insert_batch(conn, packages_batch, fts_batch)
                packages_batch.clear()
                fts_batch.clear()
                if progress_cb is not None:
                    progress_cb(min(processed / len(packages), 1.0) if packages else 0.0)

        if packages_batch:
            self._insert_batch(conn, packages_batch, fts_batch)

    def _insert_batch(
        self,
        conn: sqlite3.Connection,
        packages_batch: list[tuple[Any, ...]],
        fts_batch: list[tuple[Any, ...]],
    ) -> None:
        """Insert a batch of packages into the database."""
        conn.executemany(
            "INSERT INTO packages(name,version,description,repo,groups,"
            "installed_size,download_size,url,license,depends,raw) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            packages_batch,
        )
        conn.executemany(
            "INSERT INTO packages_fts(name,description) VALUES (?,?)",
            fts_batch,
        )

    def _store_metadata(self, conn: sqlite3.Connection, max_mtime: int) -> None:
        """Store metadata in the database."""
        conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES ('max_sync_mtime', ?)",
            (str(max_mtime),),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES ('schema_version', ?)",
            (_SCHEMA_VERSION,),
        )

    def search(
        self,
        query: str,
        limit: int = 48,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """FTS5-ranked search; returns a page of record dicts."""
        match = _fts_query(query)
        if not match:
            return []
        if not self.db_path.exists():
            return []
        conn = sqlite3.connect(self.db_path)
        try:
            if not _table_exists(conn, "packages_fts"):
                return []
            rows = conn.execute(
                "SELECT p.name, p.version, p.description, p.repo, p.groups, "
                "p.installed_size, p.download_size, p.url, p.license, p.depends, p.raw "
                "FROM packages_fts JOIN packages p ON p.name = packages_fts.name "
                "WHERE packages_fts MATCH ? ORDER BY rank LIMIT ? OFFSET ?",
                (match, limit, offset),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def get(self, name: str) -> dict[str, Any] | None:
        """Return one record dict by name, or None."""
        if not self.db_path.exists():
            return None
        conn = sqlite3.connect(self.db_path)
        try:
            if not _table_exists(conn, "packages"):
                return None
            row = conn.execute(
                "SELECT name, version, description, repo, groups, "
                "installed_size, download_size, url, license, depends, raw "
                "FROM packages WHERE name=?",
                (name,),
            ).fetchone()
            return _row_to_dict(row) if row is not None else None
        finally:
            conn.close()

    def categories(self) -> list[str]:
        """Return empty list (pacman has groups, not categories)."""
        return []
