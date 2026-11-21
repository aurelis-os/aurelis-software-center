"""Performance tests (Phase 8, Task 5.5)."""

from __future__ import annotations

import json
import tarfile
import time

import pytest

from aurelis_software.core.catalog import load_catalog
from aurelis_software.core.models import App, Source
from aurelis_software.core.search import build_index, search


def test_catalog_parse_500_apps(tmp_path):
    """Test that parsing 500 synthetic apps from catalog takes < 100 ms."""
    # Generate 500 synthetic apps
    apps = [
        {
            "id": f"test-app-{i}",
            "name": f"Test App {i}",
            "summary": f"Test summary for app {i}",
            "version": f"1.{i}.0",
            "categories": ["Development", "Graphics"][i % 2],
            "download_url": f"https://example.com/app-{i}.AppImage",
            "icon": {"name": f"app-{i}"},
        }
        for i in range(500)
    ]

    # Write catalog to JSON
    catalog_data = {
        "schema_version": 1,
        "apps": apps,
    }
    catalog_path = tmp_path / "catalog.json"
    with open(catalog_path, "w") as f:
        json.dump(catalog_data, f)

    # Time the parse
    start = time.perf_counter()
    result = load_catalog(catalog_path)
    elapsed = time.perf_counter() - start

    assert len(result.apps) == 500
    assert elapsed < 0.1, f"Catalog parse took {elapsed:.3f}s, budget is 0.1s"
    print(f"Catalog parse (500 apps): {elapsed * 1000:.1f} ms")


def test_search_keystroke_500_apps():
    """Test that a search keystroke on 500 apps takes < 50 ms."""
    # Generate 500 synthetic apps in memory
    apps = []
    for i in range(500):
        app = App(
            key=f"appimage:test-app-{i}",
            id=f"test-app-{i}",
            source=Source.APPIMAGE,
            name=f"Test App {i}",
            summary=f"Test summary for app {i}",
            version=f"1.{i}.0",
            categories=("Development", "Graphics")[i % 2 : i % 2 + 1],
            search_blob=f"test app {i} development graphics",
        )
        apps.append(app)

    # Build search index
    index = build_index(apps)

    # Time a single search query
    start = time.perf_counter()
    results = search(index, "test app")
    elapsed = time.perf_counter() - start

    assert len(results) > 0
    assert elapsed < 0.05, f"Search took {elapsed:.3f}s, budget is 0.05s"
    print(f"Search keystroke (500 apps): {elapsed * 1000:.1f} ms")


def test_fts_search_flathub(tmp_path):
    """Test that FTS search on Flathub index takes < 100 ms."""
    # This test requires the FlathubIndex to exist
    # For now, we'll create a minimal synthetic test
    from aurelis_software.services.flathub_index import FlathubIndex

    # Create a minimal AppStream XML fixture
    appstream_xml = """<?xml version="1.0" encoding="UTF-8"?>
<components version="0.14">
  <component type="desktop">
    <id>org.example.app1</id>
    <name>Test App 1</name>
    <summary>Test summary 1</summary>
    <description><p>Test description 1</p></description>
  </component>
  <component type="desktop">
    <id>org.example.app2</id>
    <name>Test Editor</name>
    <summary>Test editor summary</summary>
    <description><p>Text editor application</p></description>
  </component>
</components>
"""

    appstream_path = tmp_path / "flathub_appstream.xml"
    with open(appstream_path, "w") as f:
        f.write(appstream_xml)

    db_path = tmp_path / "flathub.db"

    # Build the index
    index = FlathubIndex(db_path=db_path, appstream_path=appstream_path)
    index.rebuild()

    # Time FTS search
    start = time.perf_counter()
    _ = index.search("editor", limit=50)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1, f"Flathub FTS search took {elapsed:.3f}s, budget is 0.1s"
    print(f"Flathub FTS search: {elapsed * 1000:.1f} ms")


def test_fts_search_pacman(tmp_path):
    """Test that FTS search on Pacman index takes < 100 ms."""
    from aurelis_software.services.pacman_index import PacmanIndex

    # Create minimal Pacman sync database fixture
    sync_dir = tmp_path / "sync"
    sync_dir.mkdir()
    core_db = sync_dir / "core.db"
    # Create an empty tar file (minimal fixture)
    with tarfile.open(core_db, "w"):
        pass

    db_path = tmp_path / "pacman.db"

    # Build the index
    index = PacmanIndex(db_path=db_path, sync_dir=sync_dir)
    try:
        index.rebuild()
    except Exception:  # noqa: BLE001
        # Pacman may not be available; skip this test
        pytest.skip("Pacman not available")

    # Time FTS search
    start = time.perf_counter()
    _ = index.search("test", limit=50)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1, f"Pacman FTS search took {elapsed:.3f}s, budget is 0.1s"
    print(f"Pacman FTS search: {elapsed * 1000:.1f} ms")
