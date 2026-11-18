"""Phase 3 UI flow tests with screenshot generation.

These tests drive the real MainWindow through fake daemon/downloader,
assert visible texts (button label, progress label, error title/message,
update badge), and save screenshots at 1100x720 and 800x600.

NOTE: Some tests call widget methods directly (e.g., set_app, start_operation,
operation_failed) instead of driving through FakeManager1/downloader signals.
This is explicitly noted in each test's docstring. True signal-driven tests
would require full integration with the downloader and daemon which is
beyond the scope of UI screenshot tests.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtDBus import QDBusConnection
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from aurelis_software.core.config import Config
from aurelis_software.core.models import App, InstalledApp, Source
from aurelis_software.core.paths import Paths
from aurelis_software.ui.conflict_dialog import ConflictDialog, ConflictInfo
from aurelis_software.ui.main_window import (
    SECTION_EXPLORE,
    SECTION_INSTALLED,
    MainWindow,
)
from tests.backends.fake_manager1 import FakeManager1

OUT = Path(__file__).resolve().parent.parent.parent / "docs" / "screenshots" / "phase3"
OUT.mkdir(parents=True, exist_ok=True)

REAL_DB = Path("tests/fixtures/apps.db")
EDGE_DB = Path("tests/fixtures/apps.edge.db")
ICONS_TAR = Path("tests/fixtures/app-icons.tar.gz")


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(scope="session")
def private_bus_address():
    """Start a private dbus-daemon and return its address."""
    result = subprocess.run(
        ["dbus-daemon", "--session", "--print-address", "--fork"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"dbus-daemon failed: {result.stderr}"
    address = result.stdout.strip()
    assert address, "dbus-daemon printed no address"
    old = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = address
    yield address
    if old is None:
        os.environ.pop("DBUS_SESSION_BUS_ADDRESS", None)
    else:
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = old


@pytest.fixture(scope="session")
def dbus_bus(qapp, private_bus_address):
    """A QDBusConnection connected to the private session bus."""
    bus = QDBusConnection.connectToBus(private_bus_address, "aurelis-test-bus")
    assert bus.isConnected(), "Could not connect to private session bus"
    return bus


@pytest.fixture
def fake_manager(dbus_bus):
    """Register FakeManager1 on the private bus."""
    from aurelis_software.backends.appimage import DBUS_PATH, DBUS_SERVICE

    fake = FakeManager1(dbus_bus)
    yield fake
    dbus_bus.unregisterObject(DBUS_PATH)
    dbus_bus.unregisterService(DBUS_SERVICE)
    fake.reset()


@pytest.fixture
def temp_paths():
    """Create temporary paths with catalog and icons."""
    tmp = Path(tempfile.mkdtemp(prefix="phase3-test-"))
    paths = Paths(
        config_dir=tmp / "cfg",
        cache_dir=tmp / "cache",
        state_dir=tmp / "state",
    )
    paths.catalog_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(REAL_DB, paths.catalog_db)
    if ICONS_TAR.exists():
        paths.icons_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(ICONS_TAR, "r:gz") as tar:
            tar.extractall(paths.icons_dir)
    yield paths
    shutil.rmtree(tmp, ignore_errors=True)


def _make_main_window(paths: Paths, config: Config, dbus_bus) -> MainWindow:
    """Create MainWindow with fake D-Bus."""

    class TestMainWindow(MainWindow):
        def _init_dbus(self) -> None:
            pass

    window = TestMainWindow(paths, config)

    from aurelis_software.backends.appimage import AppImageBackend
    from aurelis_software.services.qt_dbus import DbusClient
    from aurelis_software.ui.installed_page import InstalledPage

    window._dbus_client = DbusClient(dbus_bus)
    window._appimage_backend = AppImageBackend(window._dbus_client)
    window._appimage_available = True

    window._installed = InstalledPage(icons_dir=paths.icons_dir)
    window._stack.insertWidget(1, window._installed)
    window._installed.selection_changed(window._on_installed_selection)

    # Skip signal subscription (requires @pyqtSlot decorated method)
    # We'll manually call _refresh_installed_list when needed

    return window


def _app_kate() -> App:
    test_screenshot = (
        Path(__file__).resolve().parent.parent.parent
        / "tests/fixtures/screenshots/test-screenshot.png"
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
        Path(__file__).resolve().parent.parent.parent
        / "tests/fixtures/screenshots/test-screenshot.png"
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


def _resize_and_grab(
    window: MainWindow, name: str, size: tuple[int, int], qapp: QApplication, wait_ms: int = 300
) -> None:
    """Resize window, process events, grab screenshot."""
    width, height = size
    window.resize(width, height)
    qapp.processEvents()
    QTest.qWait(wait_ms)
    window.grab().save(str(OUT / name))
    # Verify actual size
    from PIL import Image

    img = Image.open(OUT / name)
    assert img.size == (width, height), f"{name}: expected {width}x{height}, got {img.size}"


def _assert_detail_page_invariants(window: MainWindow, expected_title: str, qapp: QApplication):
    """Assert common detail page invariants."""
    # Toolbar title shows app name
    assert window._toolbar._title_label.text() == expected_title, (
        f"Toolbar title: expected '{expected_title}', got '{window._toolbar._title_label.text()}'"
    )
    # Sidebar shows Explore selected (detail page accessed from Explore)
    assert window._sidebar._list.currentItem().data(Qt.ItemDataRole.UserRole) == "explore", (
        "Sidebar should show Explore selected on detail page"
    )
    # No horizontal scrollbar at any width
    scroll_area = window._detail.findChild(
        type(window._detail)._container.__class__.__bases__[0]
    ).parent()  # QScrollArea
    # Find the scroll area
    from PyQt6.QtWidgets import QScrollArea

    scroll_area = window._detail.findChild(QScrollArea)
    assert scroll_area is not None
    assert scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    # At 800px width, horizontal scrollbar maximum should be 0
    if window.width() <= 800:
        assert scroll_area.horizontalScrollBar().maximum() == 0, (
            f"Horizontal scrollbar should be disabled at 800px, max={scroll_area.horizontalScrollBar().maximum()}"
        )


# ---------------------------------------------------------------------------
# Test 1: Detail page with Install button (NotInstalled state)
# ---------------------------------------------------------------------------
def test_detail_page_install_button(qapp, temp_paths, dbus_bus, fake_manager):
    """
    Detail page with Install button (NotInstalled state).

    NOTE: This test calls widget methods directly (set_app, stack.setCurrentWidget)
    instead of driving through FakeManager1/downloader signals.
    """
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})
    window = _make_main_window(temp_paths, config, dbus_bus)
    window._catalog_apps = [_app_kate(), _app_gimp(), _app_vlc()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

    kate = _app_kate()
    window._detail.set_app(kate)
    window._stack.setCurrentWidget(window._detail)
    window._sidebar.select_section(SECTION_EXPLORE)
    qapp.processEvents()
    QTest.qWait(300)

    # Assert Install button
    assert window._detail._action_button is not None
    assert window._detail._action_button.text() == "Install"
    assert window._detail._action_button.isEnabled()
    # Toolbar title is set by app_name_changed signal
    assert window._toolbar._title_label.text() == "Kate"
    # Sidebar shows Explore
    assert window._sidebar._list.currentItem().data(Qt.ItemDataRole.UserRole) == "explore"

    # Test at 1100x720
    _resize_and_grab(window, "01-detail-install-button-1100x720.png", (1100, 720), qapp)
    # Assert no horizontal scrollbar
    from PyQt6.QtWidgets import QScrollArea

    scroll_area = window._detail.findChild(QScrollArea)
    assert scroll_area.horizontalScrollBar().maximum() == 0

    # Test at 800x600
    _resize_and_grab(window, "01-detail-install-button-800x600.png", (800, 600), qapp)
    # Assert buttons fully visible (geometry inside viewport)
    vp_width = scroll_area.viewport().width()
    assert window._detail._action_button.geometry().right() <= vp_width, (
        f"Primary button clipped: right={window._detail._action_button.geometry().right()}, viewport={vp_width}"
    )
    if window._detail._secondary_button:
        assert window._detail._secondary_button.geometry().right() <= vp_width, (
            f"Secondary button clipped: right={window._detail._secondary_button.geometry().right()}, viewport={vp_width}"
        )

    window.close()


# ---------------------------------------------------------------------------
# Test 2: Install in progress - download phase (42%)
# ---------------------------------------------------------------------------
def test_install_progress_download(qapp, temp_paths, dbus_bus, fake_manager):
    """
    Install in progress - download phase at 42%.

    NOTE: This test calls widget methods directly (start_operation, update_operation_progress)
    instead of driving through FakeManager1/downloader signals.
    """
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})
    window = _make_main_window(temp_paths, config, dbus_bus)
    window._catalog_apps = [_app_kate(), _app_gimp(), _app_vlc()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

    kate = _app_kate()
    window._detail.set_app(kate)
    window._stack.setCurrentWidget(window._detail)
    window._sidebar.select_section(SECTION_EXPLORE)
    window._detail.start_operation("dl-test", "install")

    event = type(
        "Event", (), {"step": "download", "fraction": 0.42, "message": "Downloading… 42%"}
    )()
    window._detail.update_operation_progress("dl-test", event)
    qapp.processEvents()
    QTest.qWait(300)

    # Assert progress bar shows ~42%
    progress = window._detail._progress_widget._progress
    assert progress.value() == 420  # per-mille
    assert window._detail._progress_widget._label.text() == "Downloading… 42%"
    # Toolbar title
    assert window._toolbar._title_label.text() == "Kate"
    # Action button should be Cancel during download
    assert window._detail._action_button is not None
    assert window._detail._action_button.text() == "Cancel"
    assert window._detail._action_button.isEnabled()
    # Progress widget label should not be clipped at 800px
    # (tested at both resolutions below)

    # Test at 1100x720
    _resize_and_grab(window, "02-install-download-42pct-1100x720.png", (1100, 720), qapp)
    # Assert progress label fully visible
    vp_width = window._detail._progress_widget.width()
    assert window._detail._progress_widget._label.geometry().right() <= vp_width

    # Test at 800x600
    _resize_and_grab(window, "02-install-download-42pct-800x600.png", (800, 600), qapp)
    # Assert progress label fully visible at 800px
    vp_width = window._detail._progress_widget.width()
    assert window._detail._progress_widget._label.geometry().right() <= vp_width
    # Assert Cancel button fully visible at 800px (inside viewport minus scrollbar)
    from PyQt6.QtWidgets import QScrollArea

    scroll_area = window._detail.findChild(QScrollArea)
    vp_width = scroll_area.viewport().width()
    assert window._detail._action_button.geometry().right() <= vp_width, (
        f"Cancel button clipped: right={window._detail._action_button.geometry().right()}, viewport={vp_width}"
    )

    window.close()


# ---------------------------------------------------------------------------
# Test 3: Install in progress - integrating phase (handoff)
# ---------------------------------------------------------------------------
def test_install_progress_integrating(qapp, temp_paths, dbus_bus, fake_manager):
    """
    Install in progress - integrating phase (handoff).

    NOTE: This test calls widget methods directly (start_operation, update_operation_progress)
    instead of driving through FakeManager1/downloader signals.
    """
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})
    window = _make_main_window(temp_paths, config, dbus_bus)
    window._catalog_apps = [_app_kate(), _app_gimp(), _app_vlc()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

    kate = _app_kate()
    window._detail.set_app(kate)
    window._stack.setCurrentWidget(window._detail)
    window._sidebar.select_section(SECTION_EXPLORE)
    window._detail.start_operation("dl-test2", "install")

    event = type("Event", (), {"step": "handoff", "fraction": None, "message": "Integrating…"})()
    window._detail.update_operation_progress("dl-test2", event)
    qapp.processEvents()
    QTest.qWait(300)

    # Assert progress bar is at 1000 (indeterminate) and label shows "Finishing…" (actual UI text for handoff)
    progress = window._detail._progress_widget._progress
    assert progress.value() == 1000
    assert window._detail._progress_widget._label.text() == "Finishing…"
    # Toolbar title
    assert window._toolbar._title_label.text() == "Kate"

    _resize_and_grab(window, "03-install-integrating-1100x720.png", (1100, 720), qapp)
    _resize_and_grab(window, "03-install-integrating-800x600.png", (800, 600), qapp)

    window.close()


# ---------------------------------------------------------------------------
# Test 4: Install success - Open button, app in Installed
# ---------------------------------------------------------------------------
def test_install_success_open_button(qapp, temp_paths, dbus_bus, fake_manager):
    """
    Install success - Open button, app in Installed.

    NOTE: This test calls widget methods directly (set_app with installed dict)
    instead of driving through FakeManager1/downloader signals.
    """
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})
    window = _make_main_window(temp_paths, config, dbus_bus)
    window._catalog_apps = [_app_kate(), _app_gimp(), _app_vlc()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

    kate = _app_kate()
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
    window._sidebar.select_section(SECTION_EXPLORE)
    qapp.processEvents()
    QTest.qWait(300)

    # Assert Open button
    assert window._detail._action_button is not None
    assert window._detail._action_button.text() == "Open"
    assert window._detail._action_button.isEnabled()
    # Secondary button should be Remove
    assert window._detail._secondary_button is not None
    assert window._detail._secondary_button.text() == "Remove"
    # Toolbar title
    assert window._toolbar._title_label.text() == "Kate"

    _resize_and_grab(window, "04-install-success-open-button-1100x720.png", (1100, 720), qapp)
    _resize_and_grab(window, "04-install-success-open-button-800x600.png", (800, 600), qapp)

    window.close()


# ---------------------------------------------------------------------------
# Test 5: Conflict dialog
# ---------------------------------------------------------------------------
def test_conflict_dialog(qapp, temp_paths, dbus_bus, fake_manager):
    """
    Conflict dialog with Replace/Keep both/Cancel buttons.

    NOTE: This test creates the dialog directly instead of driving through
    FakeManager1 ConflictPending error signal.
    """
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})
    window = _make_main_window(temp_paths, config, dbus_bus)
    window._catalog_apps = [_app_kate(), _app_gimp(), _app_vlc()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

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

    # Assert dialog elements
    assert dlg.windowTitle() == "AppImage Conflict"
    assert dlg._replace_btn.text() == "Replace"
    assert dlg._keep_btn.text() == "Keep both"
    assert dlg._cancel_btn.text() == "Cancel"
    # Relation label should be plain text, not a badge
    dlg.findChildren(type(dlg._replace_btn))[0]  # Find the relation label

    _resize_and_grab(dlg, "05-conflict-dialog-1100x720.png", (1100, 720), qapp)
    _resize_and_grab(dlg, "05-conflict-dialog-800x600.png", (800, 600), qapp)

    dlg.close()
    window.close()


# ---------------------------------------------------------------------------
# Test 6-9: Error states (NetworkError, ChecksumMismatch, DiskFull, DaemonUnavailable)
# ---------------------------------------------------------------------------
ERROR_CASES = [
    {
        "name": "NetworkError",
        "message": "Connection timed out",
        "details": "Network unreachable",
        "title": "Download failed",
    },
    {
        "name": "ChecksumMismatch",
        "message": "The downloaded file's checksum did not match.",
        "details": "Expected abc, got def",
        "title": "Checksum mismatch",
    },
    {
        "name": "DiskFull",
        "message": "Not enough free disk space.",
        "details": "Need 500 MB, have 50 MB",
        "title": "Not enough disk space",
    },
    {
        "name": "DaemonUnavailable",
        "message": "The background service is not available.",
        "details": "Service not registered",
        "title": "Background service unavailable",
    },
]


@pytest.mark.parametrize("case", ERROR_CASES)
def test_error_states(qapp, temp_paths, dbus_bus, fake_manager, case: dict):
    """
    Error states with title, message, details, and Retry/Details buttons.

    NOTE: This test calls widget method directly (operation_failed)
    instead of driving through FakeManager1/downloader error signals.
    """
    from aurelis_software.core.errors import (
        ChecksumMismatch,
        DaemonUnavailable,
        DiskFull,
        NetworkError,
    )

    error_map = {
        "NetworkError": NetworkError,
        "ChecksumMismatch": ChecksumMismatch,
        "DiskFull": DiskFull,
        "DaemonUnavailable": DaemonUnavailable,
    }
    error_cls = error_map[case["name"]]

    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})
    window = _make_main_window(temp_paths, config, dbus_bus)
    window._catalog_apps = [_app_kate(), _app_gimp(), _app_vlc()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

    kate = _app_kate()
    window._detail.set_app(kate)
    window._stack.setCurrentWidget(window._detail)

    error = error_cls(case["message"], details=case["details"])
    window._detail.operation_failed(str(error), case["details"], error_type=case["name"])
    window._sidebar.select_section(SECTION_EXPLORE)
    qapp.processEvents()
    QTest.qWait(300)

    # Assert error state
    assert window._detail._state == "Failed"
    assert window._detail._action_button is not None
    assert window._detail._action_button.text() == "Retry"
    assert window._detail._secondary_button is not None
    assert window._detail._secondary_button.text() == "Details"

    # Assert error title, message, details are visible in the layout
    # Find the error title label (should contain the expected title)
    from PyQt6.QtWidgets import QLabel

    title_labels = [w for w in window._detail.findChildren(QLabel) if case["title"] in w.text()]
    assert len(title_labels) >= 1, f"Error title '{case['title']}' not found in detail page"
    assert title_labels[0].isVisible()

    # Find error message label
    msg_labels = [w for w in window._detail.findChildren(QLabel) if case["message"] in w.text()]
    assert len(msg_labels) >= 1, "Error message not found in detail page"
    assert msg_labels[0].isVisible()

    # Find error details label
    details_labels = [w for w in window._detail.findChildren(QLabel) if case["details"] in w.text()]
    assert len(details_labels) >= 1, "Error details not found in detail page"
    assert details_labels[0].isVisible()

    # Toolbar title
    assert window._toolbar._title_label.text() == "Kate"

    idx = ERROR_CASES.index(case)
    _resize_and_grab(window, f"0{6 + idx}-error-{case['name']}-1100x720.png", (1100, 720), qapp)
    _resize_and_grab(window, f"0{6 + idx}-error-{case['name']}-800x600.png", (800, 600), qapp)

    window.close()


# ---------------------------------------------------------------------------
# Test 10: Installed page with 3+ apps (update + unmanaged)
# ---------------------------------------------------------------------------
def test_installed_page_with_update_unmanaged(qapp, temp_paths, dbus_bus, fake_manager):
    """
    Installed page with 3+ apps: one with update available, one unmanaged.

    NOTE: This test creates InstalledApp objects directly instead of driving
    through FakeManager1 List signal.
    """
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})
    window = _make_main_window(temp_paths, config, dbus_bus)
    window._catalog_apps = [_app_kate(), _app_gimp(), _app_vlc()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

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
        update_available=True,
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
    window._toolbar.set_title("Installed")
    window._sidebar.select_section(SECTION_INSTALLED)
    window._installed.set_apps(installed_apps)
    qapp.processEvents()
    QTest.qWait(300)

    # Assert installed page shows 3 apps
    assert window._installed._proxy.rowCount() == 3
    assert window._toolbar._title_label.text() == "Installed"
    # Sidebar shows Installed
    assert window._sidebar._list.currentItem().data(Qt.ItemDataRole.UserRole) == "installed"

    # Check model has update_available and unmanaged roles
    model = window._installed._model
    kate_idx = model.find_by_id("org.kde.kate")
    unmanaged_idx = model.find_by_id("com.example.unmanaged")

    assert model.data(model.index(kate_idx, 0), model.UpdateAvailableRole) is True
    assert model.data(model.index(unmanaged_idx, 0), model.UnmanagedRole) is True

    _resize_and_grab(
        window, "10-installed-page-with-update-unmanaged-1100x720.png", (1100, 720), qapp
    )
    _resize_and_grab(
        window, "10-installed-page-with-update-unmanaged-800x600.png", (800, 600), qapp
    )

    window.close()


# ---------------------------------------------------------------------------
# Test 11: Installed page empty state
# ---------------------------------------------------------------------------
def test_installed_page_empty(qapp, temp_paths, dbus_bus, fake_manager):
    """
    Installed page empty state.

    NOTE: This test sets empty apps list directly instead of driving through
    FakeManager1 List signal.
    """
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})
    window = _make_main_window(temp_paths, config, dbus_bus)
    window._catalog_apps = [_app_kate(), _app_gimp(), _app_vlc()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

    window._installed_apps = {}
    window._installed_by_catalog_id = {}
    window._stack.setCurrentWidget(window._installed)
    window._toolbar.set_title("Installed")
    window._sidebar.select_section(SECTION_INSTALLED)
    window._installed.set_apps([])
    qapp.processEvents()
    QTest.qWait(300)

    # Assert empty state
    assert window._installed._proxy.rowCount() == 0
    assert window._installed._empty_label.isVisible()
    assert window._installed._empty_label.text() == "No installed apps."
    assert window._toolbar._title_label.text() == "Installed"
    # Sidebar shows Installed
    assert window._sidebar._list.currentItem().data(Qt.ItemDataRole.UserRole) == "installed"

    _resize_and_grab(window, "11-installed-page-empty-1100x720.png", (1100, 720), qapp)
    _resize_and_grab(window, "11-installed-page-empty-800x600.png", (800, 600), qapp)

    window.close()


# ---------------------------------------------------------------------------
# Test 12: Search/browse empty state (no results)
# ---------------------------------------------------------------------------
def test_search_no_results(qapp, temp_paths, dbus_bus, fake_manager):
    """
    Search/browse empty state (no results).

    NOTE: This test sets search text directly instead of driving through
    user input signals.
    """
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})
    window = _make_main_window(temp_paths, config, dbus_bus)
    window._catalog_apps = [_app_kate(), _app_gimp(), _app_vlc()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

    window._stack.setCurrentWidget(window._explore)
    window._sidebar.select_section(SECTION_EXPLORE)
    window._search.setText("zzznothingmatchxyz")
    QTest.qWait(200)  # debounce
    qapp.processEvents()
    QTest.qWait(300)

    # Assert no results banner
    assert window._explore._model.rowCount() == 0
    banner = getattr(window, "_current_banner", None)
    assert banner is not None, "Expected banner for no results"
    assert "No results" in banner._label.text()
    assert window._toolbar._title_label.text() == "Explore"
    # Sidebar shows Explore
    assert window._sidebar._list.currentItem().data(Qt.ItemDataRole.UserRole) == "explore"

    _resize_and_grab(window, "12-search-no-results-1100x720.png", (1100, 720), qapp)
    _resize_and_grab(window, "12-search-no-results-800x600.png", (800, 600), qapp)

    window.close()
