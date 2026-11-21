#!/usr/bin/env python3
"""Render Phase 3 screenshots through the real MainWindow with FakeManager1.

Run with: QT_QPA_PLATFORM=offscreen python tools/screenshots_phase3.py

Screenshots captured (at 1100x720 and 800x600):
1. Detail page of an app, "Install" button, not yet clicked
2. Install in progress: download phase with determinate bar (e.g. 42%)
3. Install in progress: "integrating" phase (handoff)
4. Install success (button becomes "Open", app shows in Installed)
5. Conflict dialog (daemon returns ConflictPending / already installed)
6. Error state: NetworkError
7. Error state: ChecksumMismatch
8. Error state: DiskFull
9. Error state: DaemonUnavailable
10. Installed page with 3+ apps, one with update available, one unmanaged
11. Installed page empty state
12. Search/browse empty state ("no results")
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtDBus import QDBusConnection
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from aurelis_software.core.config import Config
from aurelis_software.core.models import App, InstalledApp, Source
from aurelis_software.core.paths import Paths
from aurelis_software.ui.conflict_dialog import ConflictDialog, ConflictInfo
from aurelis_software.ui.main_window import MainWindow
from tests.backends.fake_manager1 import FakeManager1

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots" / "phase3"
OUT.mkdir(parents=True, exist_ok=True)

TMP = Path(tempfile.mkdtemp(prefix="phase3-screenshots-"))

REAL_DB = Path("tests/fixtures/apps.db")
EDGE_DB = Path("tests/fixtures/apps.edge.db")
ICONS_TAR = Path("tests/fixtures/app-icons.tar.gz")


def _make_paths(catalog_db: Path | None = None) -> Paths:
    paths = Paths(
        config_dir=TMP / "cfg",
        cache_dir=TMP / "cache",
        state_dir=TMP / "state",
    )
    paths.catalog_dir.mkdir(parents=True, exist_ok=True)
    if catalog_db is not None:
        shutil.copy(catalog_db, paths.catalog_db)
    if ICONS_TAR.exists():
        paths.icons_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(ICONS_TAR, "r:gz") as tar:
            tar.extractall(paths.icons_dir)
    return paths


def _make_empty_catalog_paths() -> Paths:
    paths = Paths(
        config_dir=TMP / "cfg-empty",
        cache_dir=TMP / "cache-empty",
        state_dir=TMP / "state-empty",
    )
    paths.catalog_dir.mkdir(parents=True, exist_ok=True)
    empty_catalog = {"schema_version": 1, "apps": [], "generated_at": "2024-01-01T00:00:00Z"}
    paths.catalog_db.write_text(json.dumps(empty_catalog))
    if ICONS_TAR.exists():
        paths.icons_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(ICONS_TAR, "r:gz") as tar:
            tar.extractall(paths.icons_dir)
    return paths


def _app_kate() -> App:
    test_screenshot = (
        Path(__file__).resolve().parent.parent / "tests/fixtures/screenshots/test-screenshot.png"
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
        version="26.08.2-1",
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
            "urls": {"homepage": "https://kate-editor.org", "bugtracker": "https://bugs.kde.org"},
            "description": "A powerful text editor.\nSupports plugins and sessions.",
        },
    )


def _app_gimp() -> App:
    test_screenshot = (
        Path(__file__).resolve().parent.parent / "tests/fixtures/screenshots/test-screenshot.png"
    )
    screenshot_url = (
        test_screenshot.as_uri() if test_screenshot.exists() else "https://example.com/s.png"
    )
    return App(
        key="appimage:org.gimp.gimp",
        id="org.gimp.gimp",
        source=Source.APPIMAGE,
        name="GIMP",
        summary="GNU Image Manipulation Program",
        version="2.10.38-1",
        raw={
            "repo": "GNOME/gimp",
            "developer": "GIMP Team",
            "license": "GPL-3.0-or-later",
            "sha256": "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
            "size": 120000000,
            "icon": {"name": "org.gimp.gimp.png"},
            "screenshots": [
                {
                    "default": True,
                    "images": [
                        {"type": "source", "width": 1280, "height": 800, "url": screenshot_url}
                    ],
                }
            ],
            "urls": {"homepage": "https://www.gimp.org"},
            "description": "A free and open-source image editor.",
        },
    )


def _app_vlc() -> App:
    return App(
        key="appimage:org.videolan.vlc",
        id="org.videolan.vlc",
        source=Source.APPIMAGE,
        name="VLC",
        summary="Media player",
        version="3.0.20-1",
        raw={
            "repo": "videolan/vlc",
            "developer": "VideoLAN",
            "license": "GPL-2.0-only",
            "sha256": "c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
            "size": 80000000,
            "icon": {"name": "org.videolan.vlc.png"},
            "screenshots": [],
            "urls": {"homepage": "https://www.videolan.org/vlc/"},
            "description": "VLC media player plays most multimedia files.",
        },
    )


def _resize_and_wait(window: MainWindow, width: int, height: int) -> None:
    window.resize(width, height)
    QApplication.processEvents()
    QTest.qWait(300)


def _grab(window: MainWindow, name: str, wait_ms: int = 300) -> None:
    QApplication.processEvents()
    QTest.qWait(wait_ms)
    window.grab().save(str(OUT / name))
    print(f"  Saved {name}")


def _wait_for_signal(qapp: QApplication, timeout_ms: int = 5000) -> None:
    """Process events until timeout."""
    loop = QEventLoop()
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Aurelis Screenshots Phase 3")

    print("Setting up private D-Bus session...")
    import subprocess

    result = subprocess.run(
        ["dbus-daemon", "--session", "--print-address", "--fork"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"dbus-daemon failed: {result.stderr}"
    bus_address = result.stdout.strip()
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = bus_address

    bus = QDBusConnection.connectToBus(bus_address, "aurelis-screenshots")
    assert bus.isConnected(), f"Could not connect to private session bus: {bus_address}"

    FakeManager1(bus)

    print("Creating MainWindow with fake daemon...")
    paths = _make_paths(REAL_DB)
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})

    # We need to manually create the MainWindow without its auto D-Bus init
    # So we create a subclass that skips _init_dbus
    class ScreenshotMainWindow(MainWindow):
        def _init_dbus(self) -> None:
            pass

    window = ScreenshotMainWindow(paths, config)

    # Manually set up D-Bus with our fake
    from aurelis_software.backends.appimage import AppImageBackend
    from aurelis_software.services.qt_dbus import DbusClient
    from aurelis_software.ui.installed_page import InstalledPage

    window._dbus_client = DbusClient(bus)
    window._appimage_backend = AppImageBackend(window._dbus_client)
    window._appimage_available = True

    # Create and add InstalledPage (commented out in MainWindow)
    window._installed = InstalledPage(icons_dir=paths.icons_dir)
    window._stack.insertWidget(1, window._installed)  # After explore, before detail
    window._installed.selection_changed(window._on_installed_selection)

    # Skip signal subscription for screenshots (requires @pyqtSlot decorated method)
    # We'll manually call _refresh_installed_list when needed

    _resize_and_wait(window, 1100, 720)
    window.show()
    QTest.qWait(500)

    # Populate catalog apps
    window._catalog_apps = [_app_kate(), _app_gimp(), _app_vlc()]
    window._index = None  # Will be built by search
    window._catalog_loaded = True
    window._refresh_explore()

    print("\n=== 1. Detail page with Install button (NotInstalled state) ===")
    kate = _app_kate()
    window._detail.set_app(kate)
    window._stack.setCurrentWidget(window._detail)
    _grab(window, "01-detail-install-button-1100x720.png")

    _resize_and_wait(window, 800, 600)
    _grab(window, "01-detail-install-button-800x600.png")

    # --- 2. Install in progress: download phase at 42% ---
    print("\n=== 2. Install in progress: download phase (42%) ===")
    window._detail.set_app(kate)
    window._stack.setCurrentWidget(window._detail)
    window._detail.start_operation("dl-test", "install")
    # Simulate download progress at 42%

    event = type(
        "Event", (), {"step": "download", "fraction": 0.42, "message": "Downloading… 42%"}
    )()
    window._detail.update_operation_progress("dl-test", event)
    _grab(window, "02-install-download-42pct-1100x720.png")

    _resize_and_wait(window, 800, 600)
    _grab(window, "02-install-download-42pct-800x600.png")

    # --- 3. Install in progress: integrating phase (handoff) ---
    print("\n=== 3. Install in progress: integrating phase (handoff) ===")
    window._detail.start_operation("dl-test2", "install")
    event = type("Event", (), {"step": "handoff", "fraction": None, "message": "Integrating…"})()
    window._detail.update_operation_progress("dl-test2", event)
    _grab(window, "03-install-integrating-1100x720.png")

    _resize_and_wait(window, 800, 600)
    _grab(window, "03-install-integrating-800x600.png")

    # --- 4. Install success: button becomes Open, app in Installed ---
    print("\n=== 4. Install success: Open button, app in Installed ===")
    # Create installed app dict
    installed_kate = {
        "id": "org.kde.kate",
        "name": "Kate",
        "version": "26.08.2-1",
        "managed_name": "org.kde.kate",
        "path": "/home/user/Applications/kate.AppImage",
        "role": "primary",
        "sha256": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        "update_policy": "auto",
        "self_managed": False,
        "origin": {"catalog_id": "org.kde.kate", "source": "appimage"},
        "locked": False,
        "pending": None,
        "previous": (),
    }
    window._detail.set_app(kate, installed_kate)
    window._stack.setCurrentWidget(window._detail)
    _grab(window, "04-install-success-open-button-1100x720.png")

    _resize_and_wait(window, 800, 600)
    _grab(window, "04-install-success-open-button-800x600.png")

    # --- 5. Conflict dialog ---
    print("\n=== 5. Conflict dialog ===")
    conflicts = [
        ConflictInfo(
            app_id="org.kde.kate",
            name="Kate",
            version="26.08.1-1",
            relation="upgrade",
        )
    ]
    dlg = ConflictDialog("Kate", "26.08.2-1", conflicts, window)
    dlg.show()
    QTest.qWait(300)
    dlg.grab().save(str(OUT / "05-conflict-dialog-1100x720.png"))
    print("  Saved 05-conflict-dialog-1100x720.png")

    _resize_and_wait(dlg, 800, 600)
    dlg.grab().save(str(OUT / "05-conflict-dialog-800x600.png"))
    print("  Saved 05-conflict-dialog-800x600.png")
    dlg.close()

    # --- 6-9. Error states ---
    print("\n=== 6-9. Error states ===")
    from aurelis_software.core.errors import (
        ChecksumMismatch,
        DaemonUnavailable,
        DiskFull,
        NetworkError,
    )

    error_cases = [
        ("NetworkError", NetworkError("Connection timed out")),
        ("ChecksumMismatch", ChecksumMismatch("Expected abc, got def")),
        ("DiskFull", DiskFull("No space left on device")),
        ("DaemonUnavailable", DaemonUnavailable("Service not registered")),
    ]

    for i, (name, error) in enumerate(error_cases, start=6):
        window._detail.set_app(kate)
        window._stack.setCurrentWidget(window._detail)
        window._detail.operation_failed(
            str(error), error.details if hasattr(error, "details") else ""
        )
        _grab(window, f"{i:02d}-error-{name}-1100x720.png")

        _resize_and_wait(window, 800, 600)
        _grab(window, f"{i:02d}-error-{name}-800x600.png")

    # --- 10. Installed page with 3+ apps, one with update, one unmanaged ---
    print("\n=== 10. Installed page with 3+ apps (update + unmanaged) ===")
    # Create installed apps (InstalledPage uses InstalledApp objects)
    kate_inst = InstalledApp(
        id="org.kde.kate",
        source=Source.APPIMAGE,
        name="Kate",
        version="26.08.1-1",  # older than catalog 26.08.2-1
        managed_name="org.kde.kate",
        path="/home/user/Applications/kate.AppImage",
        role="primary",
        sha256="oldhash",
        update_policy="auto",
        self_managed=False,
        origin={"catalog_id": "org.kde.kate", "source": "appimage"},
        locked=False,
        pending=None,
        previous=(),
    )
    gimp_inst = InstalledApp(
        id="org.gimp.gimp",
        source=Source.APPIMAGE,
        name="GIMP",
        version="2.10.38-1",
        managed_name="org.gimp.gimp",
        path="/home/user/Applications/gimp.AppImage",
        role="primary",
        sha256="gimphash",
        update_policy="auto",
        self_managed=False,
        origin={"catalog_id": "org.gimp.gimp", "source": "appimage"},
        locked=False,
        pending=None,
        previous=(),
    )
    unmanaged_inst = InstalledApp(
        id="com.example.unmanaged",
        source=Source.APPIMAGE,
        name="Unmanaged App",
        version="1.0",
        managed_name="com.example.unmanaged",
        path="/home/user/Applications/unmanaged.AppImage",
        role="primary",
        sha256="unmanagedhash",
        update_policy="auto",
        self_managed=True,
        origin=None,  # Unmanaged
        locked=False,
        pending=None,
        previous=(),
    )
    installed_apps = [kate_inst, gimp_inst, unmanaged_inst]
    window._installed_apps = {app.id: app for app in installed_apps}
    window._installed_by_catalog_id = {
        "org.kde.kate": kate_inst,
        "org.gimp.gimp": gimp_inst,
    }
    window._stack.setCurrentWidget(window._installed)
    window._installed.set_apps(installed_apps)
    _grab(window, "10-installed-page-with-update-unmanaged-1100x720.png")

    _resize_and_wait(window, 800, 600)
    _grab(window, "10-installed-page-with-update-unmanaged-800x600.png")

    # --- 11. Installed page empty state ---
    print("\n=== 11. Installed page empty state ===")
    window._installed_apps = {}
    window._installed_by_catalog_id = {}
    window._installed.set_apps([])
    _grab(window, "11-installed-page-empty-1100x720.png")

    _resize_and_wait(window, 800, 600)
    _grab(window, "11-installed-page-empty-800x600.png")

    # --- 12. Search/browse empty state ("no results") ---
    print("\n=== 12. Search/browse empty state (no results) ===")
    window._stack.setCurrentWidget(window._explore)
    window._search.setText("zzznothingmatchxyz")
    QTest.qWait(200)  # debounce
    _grab(window, "12-search-no-results-1100x720.png")

    _resize_and_wait(window, 800, 600)
    _grab(window, "12-search-no-results-800x600.png")

    print(f"\nAll screenshots saved to {OUT}")
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
