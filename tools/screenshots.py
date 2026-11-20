#!/usr/bin/env python3
"""Render Phase 2 screenshots through the real MainWindow.

Run with: QT_QPA_PLATFORM=offscreen python tools/screenshots.py

States captured:
- Explore with real apps.db (real icons)
- Explore with edge DB (long, Greek, no icon)
- Detail full optional fields
- Detail no optional fields
- Detail A -> B switch
- No results (search)
- Empty catalog (valid empty catalog JSON)
- Missing cache (no catalog db)
- 800px wide
- 1600px wide
"""

from __future__ import annotations

import os
import shutil
import sys
import tarfile
import json
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from aurelis_software.core.config import Config
from aurelis_software.core.models import App, Source
from aurelis_software.core.paths import Paths
from aurelis_software.ui.main_window import MainWindow

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots" / "phase2"
OUT.mkdir(parents=True, exist_ok=True)

TMP = Path(tempfile.mkdtemp(prefix="phase2-screenshots-"))


def _make_paths(catalog_db: Path | None = None) -> Paths:
    paths = Paths(
        config_dir=TMP / "cfg",
        cache_dir=TMP / "cache",
        state_dir=TMP / "state",
    )
    paths.catalog_dir.mkdir(parents=True, exist_ok=True)
    if catalog_db is not None:
        shutil.copy(catalog_db, paths.catalog_db)
    # Extract app icons for real icons in UI
    icons_tar = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "app-icons.tar.gz"
    if icons_tar.exists():
        paths.icons_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(icons_tar, "r:gz") as tar:
            tar.extractall(paths.icons_dir)
    return paths


def _make_empty_catalog_paths() -> Paths:
    """Create paths with a valid empty catalog JSON (schema_version=1, apps=[])."""
    paths = Paths(
        config_dir=TMP / "cfg-empty",
        cache_dir=TMP / "cache-empty",
        state_dir=TMP / "state-empty",
    )
    paths.catalog_dir.mkdir(parents=True, exist_ok=True)
    # Write empty catalog JSON
    empty_catalog = {"schema_version": 1, "apps": [], "generated_at": "2024-01-01T00:00:00Z"}
    paths.catalog_db.write_text(json.dumps(empty_catalog))
    # Extract app icons for real icons in UI
    icons_tar = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "app-icons.tar.gz"
    if icons_tar.exists():
        paths.icons_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(icons_tar, "r:gz") as tar:
            tar.extractall(paths.icons_dir)
    return paths


def _make_no_catalog_paths() -> Paths:
    """Create paths with NO catalog db at all."""
    paths = Paths(
        config_dir=TMP / "cfg-none",
        cache_dir=TMP / "cache-none",
        state_dir=TMP / "state-none",
    )
    paths.catalog_dir.mkdir(parents=True, exist_ok=True)
    # Do NOT create catalog_db file
    # Extract app icons for real icons in UI
    icons_tar = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "app-icons.tar.gz"
    if icons_tar.exists():
        paths.icons_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(icons_tar, "r:gz") as tar:
            tar.extractall(paths.icons_dir)
    return paths


def _app_full() -> App:
    # Use a local test screenshot file for offline rendering
    test_screenshot = (
        Path(__file__).resolve().parent.parent
        / "tests"
        / "fixtures"
        / "screenshots"
        / "test-screenshot.png"
    )
    screenshot_url = (
        test_screenshot.as_uri() if test_screenshot.exists() else "https://example.com/s.png"
    )

    return App(
        key="appimage:org.kde.kate",
        id="org.kde.kate",
        source=Source.APPIMAGE,
        name="Kate",
        summary="Advanced text editor",
        version="26.08.1",
        raw={
            "repo": "KDE/kate",
            "developer": "KDE e.V.",
            "license": "GPL-2.0-only",
            "sha256": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "size": 45000000,
            "icon": {"name": "org.kde.kate.png"},
            "screenshots": [
                {
                    "default": True,
                    "images": [
                        {"type": "source", "width": 1280, "height": 800, "url": screenshot_url}
                    ],
                }
            ],
            "urls": {
                "homepage": "https://kate-editor.org",
                "vcs-browser": "https://invent.kde.org/utilities/kate",
            },
            "description": "A powerful text editor.\nSupports plugins and sessions.",
        },
    )


def _app_minimal() -> App:
    return App(
        key="appimage:io.github.giantpinkrobot.leap",
        id="io.github.giantpinkrobot.leap",
        source=Source.APPIMAGE,
        name="Leap",
        summary="",
        version="1.2.3",
        raw={
            "repo": "giantpinkrobot/leap",
            "download_url": "https://github.com/giantpinkrobot/leap/releases/download/v1.2.3/leap.AppImage",
            "size": None,
            "sha256": None,
            "arch": None,
            "developer": None,
            "license": None,
            "categories": [],
            "keywords": [],
            "urls": {},
            "icon": {"name": "io.github.giantpinkrobot.leap.png"},
            "screenshots": None,
        },
    )


def _grab(window: MainWindow, name: str, wait_ms: int = 300) -> None:
    """Process events, wait, then grab screenshot."""
    QApplication.processEvents()
    QTest.qWait(wait_ms)
    window.grab().save(str(OUT / name))
    print(f"  Saved {name}")


def _resize_and_wait(window: MainWindow, width: int, height: int) -> None:
    """Resize window and wait for layout to settle."""
    window.resize(width, height)
    QApplication.processEvents()
    QTest.qWait(300)


def _search_and_wait(window: MainWindow, query: str) -> None:
    """Set search text and wait for debounce + layout."""
    window._search.setText(query)
    QApplication.processEvents()
    QTest.qWait(300)  # wait for debounce (120ms) + layout


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Aurelis Screenshots")

    real_db = Path("tests/fixtures/apps.db")
    edge_db = Path("tests/fixtures/apps.edge.db")

    print("Generating screenshots...")

    # 1. Explore with real apps.db (real icons)
    print("1. Explore with real apps.db...")
    window = MainWindow(_make_paths(real_db), Config({"network": {"offline": True}}))
    _resize_and_wait(window, 1200, 800)
    window.show()
    _grab(window, "01-explore-real.png")

    # 2. Explore with edge DB (long, Greek, no icon)
    print("2. Explore with edge DB...")
    window2 = MainWindow(_make_paths(edge_db), Config({"network": {"offline": True}}))
    _resize_and_wait(window2, 1200, 800)
    window2.show()
    _grab(window2, "02-explore-edge.png")

    # 3. Detail full optional fields (using window2 with edge DB, select Kate)
    print("3. Detail full optional fields...")
    window2._detail.set_app(_app_full())
    window2._stack.setCurrentWidget(window2._detail)
    _grab(window2, "03-detail-full-fields.png")

    # 4. Detail no optional fields
    print("4. Detail no optional fields...")
    window2._detail.set_app(_app_minimal())
    _grab(window2, "04-detail-no-optional-fields.png")

    # 5. Detail A -> B switch (Kate -> Leap -> Kate)
    print("5. Detail A -> B -> A switch...")
    window2._detail.set_app(_app_full())
    _grab(window2, "05-detail-switch-kate.png")
    window2._detail.set_app(_app_minimal())
    _grab(window2, "06-detail-switch-leap.png")
    window2._detail.set_app(_app_full())
    _grab(window2, "07-detail-switch-kate-again.png")

    # 6. No results (search with no matches)
    print("6. No results (empty search)...")
    window2._stack.setCurrentWidget(window2._explore)
    _search_and_wait(window2, "zzznothing-match-xyz")
    _grab(window2, "08-empty-search.png")

    # 7. Empty catalog state (valid empty catalog JSON)
    print("7. Empty catalog...")
    window3 = MainWindow(_make_empty_catalog_paths(), Config({"network": {"offline": True}}))
    window3.show()
    QTest.qWait(300)
    _resize_and_wait(window3, 1200, 800)
    _grab(window3, "09-empty-catalog.png")

    # 8. Missing cache (no catalog db at all)
    print("8. Missing cache...")
    window4 = MainWindow(_make_no_catalog_paths(), Config({"network": {"offline": True}}))
    window4.show()
    QTest.qWait(300)
    _resize_and_wait(window4, 1200, 800)
    _grab(window4, "10-missing-cache.png")

    # 9. 800px wide explore
    print("9. 800px wide explore...")
    window5 = MainWindow(_make_paths(real_db), Config({"network": {"offline": True}}))
    _resize_and_wait(window5, 800, 800)
    window5.show()
    _grab(window5, "11-explore-800px.png")

    # 10. 1600px wide explore
    print("10. 1600px wide explore...")
    window6 = MainWindow(_make_paths(real_db), Config({"network": {"offline": True}}))
    _resize_and_wait(window6, 1600, 800)
    window6.show()
    _grab(window6, "12-explore-1600px.png")

    print(f"\nAll screenshots saved to {OUT}")
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
