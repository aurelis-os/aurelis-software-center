"""Flathub AppStream index (Phase 5.1, requirements R8.1-R8.4).

Parses the local Flatpak AppStream XML (optionally gzip-compressed) into a
SQLite database with an FTS5 table on ``name``, ``summary`` and
``keywords``. Pure stdlib (``sqlite3``, ``xml.etree.ElementTree``,
``gzip``) and no Qt, so it can run in a worker thread without a
``QApplication`` and is testable headlessly.

Locale handling (R8.4): for ``<name>``, ``<summary>`` and ``<keywords>``
the element whose ``xml:lang`` matches the requested locale is preferred,
falling back to the language part (``en`` for ``en_US``) and then to the
untagged element.
"""

from __future__ import annotations

import contextlib
import gzip
import json
import logging
import re
import sqlite3
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BATCH_SIZE = 500
_PAGE_SIZE = 48
_GZIP_MAGIC = b"\x1f\x8b"
_SCHEMA_VERSION = "1"
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# Strip FTS5 query-syntax characters so the user's raw input cannot raise
# or be mis-parsed; keeps unicode word characters (letters/digits incl.
# Greek) and whitespace, then we build a prefix-AND query.
_FTS_KEEP = re.compile(r"[^\w\s]")

_INSERT_APP_SQL = (
    "INSERT INTO apps(id,name,summary,version,icon_name,categories,raw) VALUES (?,?,?,?,?,?,?)"
)
_INSERT_FTS_SQL = "INSERT INTO apps_fts(id,name,summary,keywords) VALUES (?,?,?,?)"

__all__ = ["FlathubIndex"]


def _local(tag: str) -> str:
    """Return the local part of a (possibly namespaced) element tag."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _pick_localized(elements: list[ET.Element], locale: str) -> ET.Element | None:
    """Choose the element matching *locale* (exact, then language part, then untagged)."""
    if not elements:
        return None
    lang = locale.split("_", 1)[0] if locale else ""
    for e in elements:
        if e.get(_XML_LANG) == locale:
            return e
    if lang:
        for e in elements:
            if e.get(_XML_LANG) == lang:
                return e
    for e in elements:
        if e.get(_XML_LANG) is None:
            return e
    return elements[0]


def _localized_text(elements: list[ET.Element], locale: str) -> str:
    e = _pick_localized(elements, locale)
    return (e.text or "").strip() if e is not None else ""


def _localized_text_joined(elements: list[ET.Element], locale: str) -> str:
    """Join all text within a localized block (for ``<description>``)."""
    e = _pick_localized(elements, locale)
    if e is None:
        return ""
    return "".join(e.itertext()).strip()


def _localized_keywords(elements: list[ET.Element], locale: str) -> list[str]:
    block = _pick_localized(elements, locale)
    if block is None:
        return []
    out: list[str] = []
    for k in block:
        if _local(k.tag) != "keyword":
            continue
        text = (k.text or "").strip()
        if text:
            out.append(text)
    return out


def _extract_version(releases_elems: list[ET.Element]) -> str | None:
    if not releases_elems:
        return None
    for r in releases_elems[0]:
        if _local(r.tag) == "release":
            version = r.get("version")
            if version:
                return version
    return None


def _extract_icon(icon_elems: list[ET.Element]) -> str:
    for ic in icon_elems:
        if ic.get("type") == "cached" and ic.text:
            return ic.text.strip()
    for ic in icon_elems:
        if ic.get("type") == "stock" and ic.text:
            return ic.text.strip()
    for ic in icon_elems:
        if ic.text:
            return ic.text.strip()
    return ""


def _extract_categories(cats_elems: list[ET.Element]) -> list[str]:
    if not cats_elems:
        return []
    out: list[str] = []
    for c in cats_elems[0]:
        if _local(c.tag) != "category":
            continue
        text = (c.text or "").strip()
        if text:
            out.append(text)
    return out


def _extract_screenshots(ss_elems: list[ET.Element]) -> list[dict[str, Any]]:
    if not ss_elems:
        return []
    out: list[dict[str, Any]] = []
    for shot in ss_elems[0]:
        if _local(shot.tag) != "screenshot":
            continue
        image = None
        for child in shot:
            if _local(child.tag) == "image" and child.text:
                image = child.text.strip()
                break
        if image:
            out.append({"image": image, "default": shot.get("type") == "default"})
    return out


def _extract_homepage(url_elems: list[ET.Element]) -> str:
    for u in url_elems:
        if u.get("type") == "homepage" and u.text:
            return u.text.strip()
    return ""


def _first_text(elems: list[ET.Element]) -> str:
    if not elems:
        return ""
    return (elems[0].text or "").strip()


def _parse_component(comp: ET.Element, locale: str) -> dict[str, Any] | None:
    """Extract a record dict from one ``<component>`` element, or None to skip."""
    by_tag: dict[str, list[ET.Element]] = {}
    for child in comp:
        by_tag.setdefault(_local(child.tag), []).append(child)

    cid = _first_text(by_tag.get("id", []))
    if not cid:
        return None
    name = _localized_text(by_tag.get("name", []), locale)
    if not name:
        return None

    return {
        "id": cid,
        "name": name,
        "summary": _localized_text(by_tag.get("summary", []), locale),
        "version": _extract_version(by_tag.get("releases", [])),
        "icon_name": _extract_icon(by_tag.get("icon", [])),
        "categories": _extract_categories(by_tag.get("categories", [])),
        "keywords": _localized_keywords(by_tag.get("keywords", []), locale),
        "description": _localized_text_joined(by_tag.get("description", []), locale),
        "screenshots": _extract_screenshots(by_tag.get("screenshots", [])),
        "homepage": _extract_homepage(by_tag.get("url", [])),
        "license": _first_text(by_tag.get("project_license", [])),
        "bundle": _first_text(by_tag.get("bundle", [])),
        "launchable": _first_text(by_tag.get("launchable", [])),
        "type": comp.get("type") or "",
    }


class _CountingReader:
    """Wraps a binary file object, counting compressed bytes read for progress."""

    def __init__(self, fh) -> None:
        self._fh = fh
        self.consumed = 0

    def read(self, n: int = -1) -> bytes:
        data = self._fh.read(n)
        self.consumed += len(data)
        return data

    def __getattr__(self, name: str) -> Any:
        return getattr(self._fh, name)


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS apps ("
        "id TEXT PRIMARY KEY, name TEXT NOT NULL, summary TEXT, "
        "version TEXT, icon_name TEXT, categories TEXT, raw TEXT)"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS apps_fts USING fts5("
        "id UNINDEXED, name, summary, keywords)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    raw = json.loads(row[6]) if row[6] else {}
    return {
        "id": row[0],
        "name": row[1],
        "summary": row[2] or "",
        "version": row[3],
        "icon_name": row[4] or "",
        "categories": json.loads(row[5]) if row[5] else [],
        "keywords": raw.get("keywords", []),
        "raw": raw,
    }


def _fts_query(query: str) -> str:
    """Build a safe FTS5 prefix-AND match expression; '' means no query."""
    cleaned = _FTS_KEEP.sub(" ", query).strip()
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return ""
    return " ".join(f"{t}*" for t in tokens)


class FlathubIndex:
    """SQLite + FTS5 index over the local Flatpak AppStream XML.

    The connection is opened per call (no long-lived handle), so ``rebuild``
    can run in a worker thread and ``search``/``get`` can run in the UI
    thread without cross-thread issues.
    """

    def __init__(
        self,
        db_path: Path | str,
        appstream_path: Path | str,
        locale: str = "en",
    ) -> None:
        self.db_path = Path(db_path)
        self.appstream_path = Path(appstream_path)
        self.locale = locale

    def needs_rebuild(self) -> bool:
        """True when the index is missing or the AppStream mtime changed (R8.3)."""
        if not self.appstream_path.exists():
            return False
        if not self.db_path.exists():
            return True
        conn = sqlite3.connect(self.db_path)
        try:
            if not _table_exists(conn, "meta") or not _table_exists(conn, "apps_fts"):
                return True
            row = conn.execute("SELECT value FROM meta WHERE key='appstream_mtime_ns'").fetchone()
            if not row:
                return True
            try:
                stored = int(row[0])
            except (TypeError, ValueError):
                return True
            return stored != self.appstream_path.stat().st_mtime_ns
        finally:
            conn.close()

    def rebuild(self, progress_cb: Callable[[float], None] | None = None) -> None:
        """Parse the AppStream XML and repopulate the index (R8.1, R8.2).

        *progress_cb* is called with a fraction in [0.0, 1.0] every
        ``_BATCH_SIZE`` entries and once with 1.0 at the end. The whole
        population runs inside one SQLite transaction; on any error the
        previous index is left untouched.
        """
        path = self.appstream_path
        if not path.exists():
            msg = "AppStream file not found: " + str(path)
            raise FileNotFoundError(msg)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        mtime = path.stat().st_mtime_ns
        total = path.stat().st_size
        conn = sqlite3.connect(self.db_path)
        conn.isolation_level = None  # manage the transaction explicitly
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            _create_schema(conn)
            conn.execute("BEGIN")
            try:
                conn.execute("DELETE FROM apps_fts")
                conn.execute("DELETE FROM apps")
                seen: set[str] = set()
                apps_batch: list[tuple[Any, ...]] = []
                fts_batch: list[tuple[Any, ...]] = []
                processed = 0
                for record, consumed in self._iter_records(path):
                    if record is None:
                        continue
                    rid = record["id"]
                    if rid in seen:
                        continue
                    seen.add(rid)
                    apps_batch.append(
                        (
                            rid,
                            record["name"],
                            record["summary"],
                            record["version"],
                            record["icon_name"],
                            json.dumps(record["categories"]),
                            json.dumps(record),
                        )
                    )
                    fts_batch.append(
                        (
                            rid,
                            record["name"],
                            record["summary"],
                            " ".join(record["keywords"]),
                        )
                    )
                    processed += 1
                    if len(apps_batch) >= _BATCH_SIZE:
                        conn.executemany(_INSERT_APP_SQL, apps_batch)
                        conn.executemany(_INSERT_FTS_SQL, fts_batch)
                        apps_batch.clear()
                        fts_batch.clear()
                    if processed % _BATCH_SIZE == 0 and progress_cb is not None:
                        progress_cb(min(consumed / total, 1.0) if total else 0.0)
                if apps_batch:
                    conn.executemany(_INSERT_APP_SQL, apps_batch)
                    conn.executemany(_INSERT_FTS_SQL, fts_batch)
                conn.execute(
                    "INSERT OR REPLACE INTO meta(key,value) VALUES ('appstream_mtime_ns', ?)",
                    (str(mtime),),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO meta(key,value) VALUES ('schema_version', ?)",
                    (_SCHEMA_VERSION,),
                )
                conn.execute("COMMIT")
                if progress_cb is not None:
                    progress_cb(1.0)
            except (sqlite3.Error, ET.ParseError, OSError, ValueError):
                conn.execute("ROLLBACK")
                raise
            log.info("Flathub index rebuilt: %d apps", processed)
        finally:
            conn.close()

    def _iter_records(self, path: Path):
        """Stream-parse the (optionally gzipped) AppStream XML.

        Yields ``(record_dict_or_None, compressed_bytes_consumed)`` for each
        ``<component>`` element, freeing each element after yielding so the
        full tree is not held in memory.
        """
        with open(path, "rb") as raw:
            counter = _CountingReader(raw)
            head = raw.read(2)
            raw.seek(0)
            counter.consumed = 0
            src = gzip.GzipFile(fileobj=counter) if head == _GZIP_MAGIC else counter
            with contextlib.closing(src):
                for _event, elem in ET.iterparse(src, events=("end",)):
                    if _local(elem.tag) == "component":
                        record = _parse_component(elem, self.locale)
                        yield record, counter.consumed
                        elem.clear()

    def search(
        self,
        query: str,
        limit: int = _PAGE_SIZE,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """FTS5-ranked search; returns a page of record dicts (R8.1, R9.1)."""
        match = _fts_query(query)
        if not match:
            return []
        if not self.db_path.exists():
            return []
        conn = sqlite3.connect(self.db_path)
        try:
            if not _table_exists(conn, "apps_fts"):
                return []
            rows = conn.execute(
                "SELECT a.id, a.name, a.summary, a.version, a.icon_name, "
                "a.categories, a.raw FROM apps_fts JOIN apps a ON a.id = apps_fts.id "
                "WHERE apps_fts MATCH ? ORDER BY rank LIMIT ? OFFSET ?",
                (match, limit, offset),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def get(self, app_id: str) -> dict[str, Any] | None:
        """Return one record dict by id, or None (R9.3 'also available as')."""
        if not self.db_path.exists():
            return None
        conn = sqlite3.connect(self.db_path)
        try:
            if not _table_exists(conn, "apps"):
                return None
            row = conn.execute(
                "SELECT id, name, summary, version, icon_name, categories, raw "
                "FROM apps WHERE id=?",
                (app_id,),
            ).fetchone()
            return _row_to_dict(row) if row is not None else None
        finally:
            conn.close()

    def categories(self) -> list[str]:
        """Distinct category names across all apps, in first-seen order."""
        if not self.db_path.exists():
            return []
        conn = sqlite3.connect(self.db_path)
        try:
            if not _table_exists(conn, "apps"):
                return []
            seen: set[str] = set()
            out: list[str] = []
            for (cj,) in conn.execute("SELECT categories FROM apps").fetchall():
                for c in json.loads(cj) if cj else []:
                    if c and c not in seen:
                        seen.add(c)
                        out.append(c)
            return out
        finally:
            conn.close()
