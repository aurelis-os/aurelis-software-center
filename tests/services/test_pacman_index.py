"""Tests for PacmanIndex (Phase 6, FEAT-002)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


class FakeRunner:
    """Fake command runner for testing PacmanIndex without real pacman."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> tuple[int, str, str]:
        self.calls.append(cmd)
        return self.returncode, self.stdout, self.stderr


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Temporary database path."""
    return tmp_path / "test_pacman.db"


@pytest.fixture
def temp_sync_dir(tmp_path: Path) -> Path:
    """Temporary sync directory with mock .db files."""
    sync_dir = tmp_path / "sync"
    sync_dir.mkdir()
    # Create some mock .db files
    (sync_dir / "core.db").touch()
    (sync_dir / "extra.db").touch()
    return sync_dir


@pytest.fixture
def sample_si_output() -> str:
    """Sample pacman -Si output with 3 packages."""
    return """Repository      : core
Name            : bash
Version         : 5.2.015-1
Description     : The GNU Bourne Again shell
Architecture    : x86_64
URL             : https://www.gnu.org/software/bash/bash.html
Licenses        : GPL3
Groups          : base
Provides        : sh
Depends On      : readline  glibc  ncurses
Optional Deps   : bash-completion: for tab completion
Conflicts With  : None
Replaces        : None
Download Size   : 1.60 MiB
Installed Size  : 8.12 MiB
Packager        : Jan Alexander Steffens (heftig) <heftig@archlinux.org>
Build Date      : Mon 21 Oct 2024 08:45:12 AM UTC
Validated By    : MD5 Sum  SHA-256 Sum  Signature

Repository      : extra
Name            : firefox
Version         : 131.0-1
Description     : Standalone web browser from mozilla.org
Architecture    : x86_64
URL             : https://www.mozilla.org/firefox/
Licenses        : MPL-2.0
Groups          : None
Provides        : None
Depends On      : dbus  ffmpeg  gtk3  libpulse  libxcomposite
Optional Deps   : None
Conflicts With  : None
Replaces        : None
Download Size   : 60.12 MiB
Installed Size  : 223.45 MiB
Packager        : Jan Alexander Steffens (heftig) <heftig@archlinux.org>
Build Date      : Wed 16 Oct 2024 11:23:45 AM UTC
Validated By    : MD5 Sum  SHA-256 Sum  Signature

Repository      : core
Name            : python
Version         : 3.11.5-1
Description     : The Python programming language
Architecture    : x86_64
URL             : https://www.python.org/
Licenses        : PSF-2.0
Groups          : None
Provides        : python3
Depends On      : bzip2  expat  gdbm  libffi  libnsl  libxcrypt  openssl  zlib
Optional Deps   : python-setuptools  python-pip
Conflicts With  : None
Replaces        : None
Download Size   : 18.43 MiB
Installed Size  : 106.78 MiB
Packager        : Angel Velasquez <angvp@archlinux.org>
Build Date      : Thu 24 Aug 2024 02:15:33 PM UTC
Validated By    : MD5 Sum  SHA-256 Sum  Signature

"""


def test_needs_rebuild_true_when_db_missing(temp_db: Path, temp_sync_dir: Path) -> None:
    """needs_rebuild returns True when database doesn't exist."""
    from aurelis_software.services.pacman_index import PacmanIndex

    index = PacmanIndex(temp_db, temp_sync_dir)
    assert index.needs_rebuild() is True


def test_needs_rebuild_false_when_sync_dir_missing(temp_db: Path, tmp_path: Path) -> None:
    """needs_rebuild returns False when sync_dir doesn't exist."""
    from aurelis_software.services.pacman_index import PacmanIndex

    missing_sync = tmp_path / "nonexistent"
    index = PacmanIndex(temp_db, missing_sync)
    assert index.needs_rebuild() is False


def test_needs_rebuild_false_when_mtime_unchanged(
    temp_db: Path, temp_sync_dir: Path, sample_si_output: str
) -> None:
    """needs_rebuild returns False when mtime hasn't changed."""
    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(stdout=sample_si_output)
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)

    # Build initial index
    index.rebuild()

    # Check needs_rebuild without changing sync_dir
    assert index.needs_rebuild() is False


def test_needs_rebuild_true_when_mtime_changed(
    temp_db: Path, temp_sync_dir: Path, sample_si_output: str
) -> None:
    """needs_rebuild returns True when sync_dir mtime has changed."""
    import time

    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(stdout=sample_si_output)
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)

    # Build initial index
    index.rebuild()

    # Touch a .db file to change mtime
    time.sleep(0.01)  # Ensure mtime changes
    (temp_sync_dir / "core.db").touch()

    assert index.needs_rebuild() is True


def test_rebuild_creates_tables(temp_db: Path, temp_sync_dir: Path, sample_si_output: str) -> None:
    """rebuild creates the required tables."""
    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(stdout=sample_si_output)
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)
    index.rebuild()

    conn = sqlite3.connect(temp_db)
    try:
        # Check tables exist
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {row[0] for row in tables}
        assert "packages" in table_names
        assert "packages_fts" in table_names
        assert "meta" in table_names
    finally:
        conn.close()


def test_rebuild_inserts_parsed_packages(
    temp_db: Path, temp_sync_dir: Path, sample_si_output: str
) -> None:
    """rebuild correctly parses and inserts packages."""
    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(stdout=sample_si_output)
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)
    index.rebuild()

    conn = sqlite3.connect(temp_db)
    try:
        # Check package count
        count = conn.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
        assert count == 3

        # Check specific package
        row = conn.execute(
            "SELECT name, version, description, repo FROM packages WHERE name='bash'"
        ).fetchone()
        assert row is not None
        assert row[0] == "bash"
        assert row[1] == "5.2.015-1"
        assert row[2] == "The GNU Bourne Again shell"
        assert row[3] == "core"

        # Check FTS table populated
        fts_count = conn.execute("SELECT COUNT(*) FROM packages_fts").fetchone()[0]
        assert fts_count == 3
    finally:
        conn.close()


def test_rebuild_calls_progress_cb(
    temp_db: Path, temp_sync_dir: Path, sample_si_output: str
) -> None:
    """rebuild calls progress_cb during indexing."""
    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(stdout=sample_si_output)
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)

    progress_calls: list[float] = []

    def progress_cb(fraction: float) -> None:
        progress_calls.append(fraction)

    index.rebuild(progress_cb=progress_cb)

    # Should have at least one call with 1.0 at the end
    assert len(progress_calls) > 0
    assert progress_calls[-1] == 1.0
    # All fractions should be in [0.0, 1.0]
    assert all(0.0 <= f <= 1.0 for f in progress_calls)


def test_search_returns_fts_results(
    temp_db: Path, temp_sync_dir: Path, sample_si_output: str
) -> None:
    """search returns FTS5-ranked results."""
    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(stdout=sample_si_output)
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)
    index.rebuild()

    # Search for "shell"
    results = index.search("shell")
    assert len(results) == 1
    assert results[0]["name"] == "bash"
    assert "shell" in results[0]["description"].lower()


def test_search_with_pagination(temp_db: Path, temp_sync_dir: Path, sample_si_output: str) -> None:
    """search supports limit and offset."""
    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(stdout=sample_si_output)
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)
    index.rebuild()

    # Search for all packages (generic term)
    results_page1 = index.search("the", limit=2, offset=0)
    results_page2 = index.search("the", limit=2, offset=2)

    # Should get different results
    assert len(results_page1) <= 2
    if len(results_page1) == 2 and len(results_page2) > 0:
        assert results_page1[0]["name"] != results_page2[0]["name"]


def test_search_empty_query(temp_db: Path, temp_sync_dir: Path, sample_si_output: str) -> None:
    """search returns empty list for empty query."""
    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(stdout=sample_si_output)
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)
    index.rebuild()

    results = index.search("")
    assert results == []


def test_search_no_matches(temp_db: Path, temp_sync_dir: Path, sample_si_output: str) -> None:
    """search returns empty list when no matches found."""
    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(stdout=sample_si_output)
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)
    index.rebuild()

    results = index.search("xyznonexistent")
    assert results == []


def test_get_returns_single_record(
    temp_db: Path, temp_sync_dir: Path, sample_si_output: str
) -> None:
    """get returns a single package dict by name."""
    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(stdout=sample_si_output)
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)
    index.rebuild()

    pkg = index.get("python")
    assert pkg is not None
    assert pkg["name"] == "python"
    assert pkg["version"] == "3.11.5-1"
    assert "Python programming language" in pkg["description"]


def test_get_returns_none_for_missing(
    temp_db: Path, temp_sync_dir: Path, sample_si_output: str
) -> None:
    """get returns None for nonexistent package."""
    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(stdout=sample_si_output)
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)
    index.rebuild()

    pkg = index.get("nonexistent")
    assert pkg is None


def test_rebuild_idempotent(temp_db: Path, temp_sync_dir: Path, sample_si_output: str) -> None:
    """rebuild is idempotent (running twice produces same result)."""
    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(stdout=sample_si_output)
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)

    # First rebuild
    index.rebuild()
    conn = sqlite3.connect(temp_db)
    try:
        count1 = conn.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
    finally:
        conn.close()

    # Second rebuild
    index.rebuild()
    conn = sqlite3.connect(temp_db)
    try:
        count2 = conn.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
    finally:
        conn.close()

    assert count1 == count2 == 3


def test_categories_returns_empty_list(
    temp_db: Path, temp_sync_dir: Path, sample_si_output: str
) -> None:
    """categories returns empty list (pacman has groups, not categories)."""
    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(stdout=sample_si_output)
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)
    index.rebuild()

    assert index.categories() == []


def test_rebuild_handles_runner_failure(temp_db: Path, temp_sync_dir: Path) -> None:
    """rebuild raises RuntimeError when pacman command fails."""
    from aurelis_software.services.pacman_index import PacmanIndex

    runner = FakeRunner(returncode=1, stderr="pacman: error: unable to query database")
    index = PacmanIndex(temp_db, temp_sync_dir, runner=runner)

    with pytest.raises(RuntimeError, match="pacman -Si failed"):
        index.rebuild()


def test_get_missing_db(temp_db: Path, temp_sync_dir: Path) -> None:
    """get returns None when database doesn't exist."""
    from aurelis_software.services.pacman_index import PacmanIndex

    index = PacmanIndex(temp_db, temp_sync_dir)
    pkg = index.get("bash")
    assert pkg is None


def test_search_missing_db(temp_db: Path, temp_sync_dir: Path) -> None:
    """search returns empty list when database doesn't exist."""
    from aurelis_software.services.pacman_index import PacmanIndex

    index = PacmanIndex(temp_db, temp_sync_dir)
    results = index.search("bash")
    assert results == []
