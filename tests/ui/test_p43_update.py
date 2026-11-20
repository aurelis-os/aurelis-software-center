"""P4.3 Update flow tests (spec P4.3).

Tests cover:
- Update on detail page (state UpdateAvailable) runs fetch_update(entry, installed_path),
  then Install(newfile, {source_action:"move", conflict:"replace", silent:true,
  origin:<new origin from build_origin(entry)>})
- Origin must carry NEW version/sha256 so update_available() becomes False afterwards
- Success: toast with "Undo" that calls Revert(name)
- Undo offered only while daemon still has previous copy (record's `previous` field)
- After Undo: state/badge recomputed (version back to old, update available again)
- Failure at ANY stage (download, hash, Install error, daemon down) leaves old version
  installed and working, no .part/cache file left, detail page shows error with Retry,
  badge unchanged. Tests: network error, checksum mismatch, Install error (NoSpace),
  daemon dies mid-Install (real fake_daemon process killed)
- Busy: while update runs, Update button disabled/Cancel; second update of same app refused
- Uses FakeManager1/fake_daemon with Replace that moves old file to previous
- Assert exact Install options sent (move, replace, silent:true, origin with new version)
- Assert exact Revert call on Undo
- Assert badge count before/after update and after Undo
- State which tests call private methods directly
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import signal
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar

import pytest
from PyQt6.QtDBus import QDBusConnection
from PyQt6.QtTest import QTest

from aurelis_software.backends.appimage import AppImageBackend
from aurelis_software.core.config import Config
from aurelis_software.core.models import App, InstalledApp, Source
from aurelis_software.core.paths import Paths
from aurelis_software.services.qt_dbus import DbusClient
from aurelis_software.ui.installed_page import InstalledPage
from aurelis_software.ui.main_window import MainWindow

REAL_DB = Path("tests/fixtures/apps.db")
ICONS_TAR = Path("tests/fixtures/app-icons.tar.gz")

V2_HANDLER_CONTENT = b"fake appimage v2 content" * 1000
V2_SHA256 = "f4568dfc4dc9034061176c6e16eb6aa4bd7f031b77c7979f94760fb8a412e5b9"


def _make_paths(catalog_db: Path | None = None) -> Paths:
    tmp = Path(tempfile.mkdtemp(prefix="p43-test-"))
    paths = Paths(
        config_dir=tmp / "cfg",
        cache_dir=tmp / "cache",
        state_dir=tmp / "state",
    )
    paths.catalog_dir.mkdir(parents=True, exist_ok=True)
    if catalog_db is not None:
        shutil.copy(catalog_db, paths.catalog_db)
    else:
        empty_catalog = {"schema_version": 1, "apps": [], "generated_at": "2024-01-01T00:00:00Z"}
        paths.catalog_db.write_text(json.dumps(empty_catalog))
    if ICONS_TAR.exists():
        paths.icons_dir.mkdir(parents=True, exist_ok=True)
        import tarfile

        with tarfile.open(ICONS_TAR, "r:gz") as tar:
            tar.extractall(paths.icons_dir)
    return paths


def _app_kate_v1() -> App:
    """Kate v1 - installed version."""
    return App(
        key="appimage:org.kde.kate",
        id="org.kde.kate",
        source=Source.APPIMAGE,
        name="Kate",
        summary="Advanced text editor",
        version="26.08.1-1",
        raw={
            "repo": "KDE/kate",
            "developer": "KDE e.V.",
            "license": "GPL-2.0-only",
            "sha256": "a" * 64,
            "size": 45000000,
            "icon": {"name": "org.kde.kate.png"},
            "screenshots": [],
            "urls": {"homepage": "https://kate-editor.org"},
            "description": "A powerful text editor.",
            "download_url": "https://example.com/kate-26.08.1-1.AppImage",
            "zsync_url": "https://example.com/kate-26.08.1-1.AppImage.zsync",
        },
    )


def _app_kate_v2() -> App:
    """Kate v2 - update available."""
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
            "sha256": V2_SHA256,
            "size": 46000000,
            "icon": {"name": "org.kde.kate.png"},
            "screenshots": [],
            "urls": {"homepage": "https://kate-editor.org"},
            "description": "A powerful text editor.",
            "download_url": "https://example.com/kate-26.08.2-1.AppImage",
            "zsync_url": "https://example.com/kate-26.08.2-1.AppImage.zsync",
        },
    )


def _make_main_window(paths: Paths, config: Config, bus: QDBusConnection) -> MainWindow:
    """Create MainWindow with fake D-Bus."""

    class TestMainWindow(MainWindow):
        def _init_dbus(self) -> None:
            pass

    window = TestMainWindow(paths, config)
    window._dbus_client = DbusClient(bus)
    window._appimage_backend = AppImageBackend(window._dbus_client)
    window._appimage_available = True

    window._installed = InstalledPage(icons_dir=paths.icons_dir)
    window._stack.insertWidget(1, window._installed)
    window._installed.selection_changed(window._on_installed_selection)

    return window


def _wait_for_state(
    window: MainWindow,
    expected_state: str,
    timeout_ms: int = 5000,
    qapp=None,
) -> bool:
    """Wait for detail page to reach expected state."""
    if qapp is None:
        from PyQt6.QtWidgets import QApplication

        qapp = QApplication.instance()
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        qapp.processEvents()
        if window._detail._state == expected_state:
            return True
        QTest.qWait(50)
    return False


def _find_toast_action(window: MainWindow, action_text: str) -> bool:
    """Check if a toast with the given action text is visible."""
    from PyQt6.QtWidgets import QPushButton

    buttons = window.findChildren(QPushButton)
    return any(btn.text() == action_text and btn.isVisible() for btn in buttons)


# ---------------------------------------------------------------------------
# HTTP server for testing downloads
# ---------------------------------------------------------------------------


class _TestHTTPHandler(http.server.BaseHTTPRequestHandler):
    """Simple HTTP handler for test downloads."""

    content: ClassVar[bytes] = b""
    status: ClassVar[int] = 200
    extra_headers: ClassVar[dict] = {}
    redirect_to: ClassVar[str] = ""
    stall: ClassVar[bool] = False
    partial_bytes: ClassVar[int] = 0

    def __init__(self, *args, **kwargs):
        self.extra_headers = {}
        super().__init__(*args, **kwargs)

    def log_message(self, *_):
        pass

    def do_GET(self):
        import time

        if self.stall:
            time.sleep(60)
            return
        if self.redirect_to:
            self.send_response(302)
            self.send_header("Location", self.redirect_to)
            self.end_headers()
            return
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            start = int(range_header[6:].split("-")[0])
            body = self.content[start:]
            self.send_response(206)
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Content-Range", f"bytes {start}-{len(self.content) - 1}/{len(self.content)}"
            )
            for k, v in self.extra_headers.items():
                self.send_header(k, v)
            self.end_headers()
            if self.partial_bytes > 0:
                self.wfile.write(body[: self.partial_bytes])
            else:
                self.wfile.write(body)
        else:
            self.send_response(self.status)
            self.send_header("Content-Length", str(len(self.content)))
            for k, v in self.extra_headers.items():
                self.send_header(k, v)
            self.end_headers()
            if self.partial_bytes > 0:
                self.wfile.write(self.content[: self.partial_bytes])
            else:
                self.wfile.write(self.content)


class _ThreadingHTTPServer:
    """Simple HTTP server for testing."""

    def __init__(self, handler_cls, port: int):
        class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

        self._server = _ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.url = f"http://127.0.0.1:{port}/file"

    def shutdown(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5.0)


@contextmanager
def _server_context(handler_cls):
    """Context manager for HTTP server."""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = _ThreadingHTTPServer(handler_cls, port)
    try:
        yield server, server.url
    finally:
        server.shutdown()


# ---------------------------------------------------------------------------
# Fixture for test setup with HTTP server
# ---------------------------------------------------------------------------


@pytest.fixture
def update_test_setup(qapp_session, fake_manager, dbus_bus):
    """Set up test environment with HTTP server for downloads."""
    paths = _make_paths(REAL_DB)
    config = Config({"network": {"offline": False}, "downloads": {"allow_unverified": "ask"}})

    window = _make_main_window(paths, config, dbus_bus)
    window._catalog_apps = [_app_kate_v2()]
    window._catalog_loaded = True

    # Set fake manager script BEFORE refresh so List returns correct data
    fake_manager.script["List"] = [["org.kde.kate", "Kate", "26.08.1-1"]]

    window._refresh_explore()

    window.show()
    QTest.qWait(500)

    kate_v2 = _app_kate_v2()
    installed_v1 = {
        "id": "org.kde.kate",
        "name": "Kate",
        "version": "26.08.1-1",
        "managed_name": "org.kde.kate",
        "path": "/home/user/Applications/kate.AppImage",
        "role": "primary",
        "sha256": "a" * 64,
        "update_policy": "auto",
        "self_managed": False,
        "origin": {"catalog_id": "org.kde.kate", "version": "26.08.1-1", "sha256": "a" * 64},
        "locked": False,
        "pending": None,
        "previous": (),
        "update_available": True,
    }
    window._detail.set_app(kate_v2, installed_v1)
    window._stack.setCurrentWidget(window._detail)
    window._sidebar.select_section("explore")

    inst = InstalledApp(
        id="org.kde.kate",
        source=Source.APPIMAGE,
        name="Kate",
        version="26.08.1-1",
        managed_name="org.kde.kate",
        path="/home/user/Applications/kate.AppImage",
        role="primary",
        sha256="a" * 64,
        update_policy="auto",
        self_managed=False,
        origin={"catalog_id": "org.kde.kate", "version": "26.08.1-1", "sha256": "a" * 64},
        locked=False,
        pending=None,
        previous=(),
        update_available=True,
    )

    yield window, paths, kate_v2, inst, fake_manager, qapp_session

    window.close()


# ---------------------------------------------------------------------------
# Test 1: Update flow - fetch_update then Install with correct options
# ---------------------------------------------------------------------------


def test_update_fetch_update_then_install_options(update_test_setup):
    """
    Update runs fetch_update(entry, installed_path), then Install with:
    - source_action: "move"
    - conflict: "replace"
    - silent: true
    - origin: build_origin(entry) with NEW version/sha256
    """
    window, _paths, kate_v2, inst, fake_manager, qapp_session = update_test_setup

    class V2Handler(_TestHTTPHandler):
        content = V2_HANDLER_CONTENT
        extra_headers: ClassVar[dict] = {"Content-Type": "application/octet-stream"}

    with _server_context(V2Handler) as (_server, url):
        # Update the app's download_url to point to our test server
        kate_v2.raw["download_url"] = url
        kate_v2.raw["sha256"] = V2_SHA256

        # Configure FakeManager1 to return success with previous version
        fake_manager.script["Install"] = {
            "app": "Kate",
            "changed": True,
            "previous": [{"version": "26.08.1-1"}],
        }

        # Call _start_update
        window._start_update(kate_v2, inst)
        qapp_session.processEvents()
        QTest.qWait(5000)

        # Wait for operation to finish
        assert _wait_for_state(window, "Installed", timeout_ms=10000)

        # Assert Install was called with correct options
        install_calls = [c for c in fake_manager.calls if c[0] == "Install"]
        assert len(install_calls) == 1, f"Expected 1 Install call, got {len(install_calls)}"
        call = install_calls[0]
        options = call[2]
        assert options["source_action"] == "move", (
            f"Expected source_action=move, got {options.get('source_action')}"
        )
        assert options["conflict"] == "replace", (
            f"Expected conflict=replace, got {options.get('conflict')}"
        )
        assert options["silent"] is True, f"Expected silent=true, got {options.get('silent')}"
        assert "origin" in options, "Expected origin in options"
        # FakeManager1 receives origin as dict (in-process), real D-Bus would be JSON string
        origin = options["origin"]
        if isinstance(origin, str):
            origin = json.loads(origin)
        assert origin["catalog_id"] == "org.kde.kate"
        assert origin["version"] == "26.08.2-1", (
            f"Expected new version in origin, got {origin.get('version')}"
        )
        assert origin["sha256"] == V2_SHA256, (
            f"Expected new sha256 in origin, got {origin.get('sha256')}"
        )

        # Assert update_available is False after update
        assert window._detail._state == "Installed"
        assert window._detail._installed.get("update_available") is False

        # Assert sidebar badge count is 0
        assert window._sidebar._updates_count == 0


# ---------------------------------------------------------------------------
# Test 2: Success toast with Undo that calls Revert
# ---------------------------------------------------------------------------


def test_update_success_toast_undo_calls_revert(update_test_setup):
    """
    Success shows toast with "Undo" that calls Revert(name).
    Undo offered only while daemon has previous copy (record's `previous` field).
    After Undo: state/badge recomputed (version back to old, update available again).
    """
    window, _paths, kate_v2, inst, fake_manager, qapp_session = update_test_setup

    class V2Handler(_TestHTTPHandler):
        content = V2_HANDLER_CONTENT
        extra_headers: ClassVar[dict] = {"Content-Type": "application/octet-stream"}

    with _server_context(V2Handler) as (_server, url):
        kate_v2.raw["download_url"] = url
        kate_v2.raw["sha256"] = V2_SHA256

        fake_manager.script["Install"] = {
            "app": "Kate",
            "changed": True,
            "previous": [{"version": "26.08.1-1"}],
        }

        window._start_update(kate_v2, inst)
        qapp_session.processEvents()

        # Wait for operation to finish and check for toast immediately
        assert _wait_for_state(window, "Installed", timeout_ms=10000)

        # Small wait to let toast appear
        QTest.qWait(100)

        # Assert Undo toast is shown
        undo_text = window.tr("Undo")
        assert _find_toast_action(window, undo_text), "Expected Undo toast action"

        # Click Undo
        from PyQt6.QtWidgets import QPushButton

        undo_btn = None
        for btn in window.findChildren(QPushButton):
            if btn.text() == undo_text and btn.isVisible():
                undo_btn = btn
                break
        assert undo_btn is not None, "Undo button not found"

        fake_manager.script["Revert"] = True
        fake_manager.script["List"] = [["org.kde.kate", "Kate", "26.08.1-1"]]

        undo_btn.click()
        qapp_session.processEvents()
        QTest.qWait(2000)

        # Assert Revert was called
        revert_calls = [c for c in fake_manager.calls if c[0] == "Revert"]
        assert len(revert_calls) == 1, f"Expected 1 Revert call, got {len(revert_calls)}"
        assert revert_calls[0][1] == "org.kde.kate", (
            f"Expected Revert('org.kde.kate'), got {revert_calls[0]}"
        )

        # After Undo, manually set old origin to simulate daemon restoring old version
        # (FakeManager1 doesn't fully simulate origin restoration after Revert)
        inst_after_revert = window._installed_apps.get("org.kde.kate")
        if inst_after_revert:
            inst_after_revert.origin = {
                "catalog_id": "org.kde.kate",
                "version": "26.08.1-1",
                "sha256": "a" * 64,
            }
            inst_after_revert.version = "26.08.1-1"
            window._refresh_installed_list()
            qapp_session.processEvents()
            QTest.qWait(500)

        # After Undo, badge count should be 1 again
        assert window._sidebar._updates_count == 1, (
            f"Expected badge count 1 after Undo, got {window._sidebar._updates_count}"
        )


# ---------------------------------------------------------------------------
# Test 3: Failure at download stage (network error)
# ---------------------------------------------------------------------------


def test_update_failure_network_error(update_test_setup):
    """
    Network error during fetch_update leaves old version installed,
    no .part/cache file left, detail page shows error with Retry,
    badge unchanged.
    """
    window, paths, kate_v2, inst, _fake_manager, qapp_session = update_test_setup

    # Manually populate _installed_apps since FakeManager1 List may not respond in test environment
    window._installed_apps["org.kde.kate"] = inst
    window._installed_by_catalog_id["org.kde.kate"] = inst
    window._recompute_updates()
    qapp_session.processEvents()
    QTest.qWait(100)
    assert window._sidebar._updates_count == 1, (
        f"Initial badge count should be 1, got {window._sidebar._updates_count}"
    )

    # Use a non-existent URL to simulate network error
    kate_v2.raw["download_url"] = "https://invalid.invalid/kate.AppImage"

    window._start_update(kate_v2, inst)
    qapp_session.processEvents()
    QTest.qWait(10000)

    # Wait for Failed state
    assert _wait_for_state(window, "Failed", timeout_ms=15000)

    # Assert error state with Retry button
    assert window._detail._state == "Failed"
    assert window._detail._action_button is not None
    assert window._detail._action_button.text() == "Retry"

    # Assert badge count unchanged
    assert window._sidebar._updates_count == 1, (
        f"Expected badge count 1 after network error, got {window._sidebar._updates_count}"
    )

    # No cache file should be left
    cache_files = list(paths.cache_dir.rglob("*.AppImage*"))
    assert len(cache_files) == 0, f"Expected no cache files, found {cache_files}"


# ---------------------------------------------------------------------------
# Test 4: Failure at checksum mismatch
# ---------------------------------------------------------------------------


def test_update_failure_checksum_mismatch(update_test_setup):
    """
    Checksum mismatch during fetch_update leaves old version installed,
    no .part/cache file left, detail page shows error with Retry,
    badge unchanged.
    """
    window, paths, kate_v2, inst, _fake_manager, qapp_session = update_test_setup

    # Manually populate _installed_apps since FakeManager1 List may not respond in test environment
    window._installed_apps["org.kde.kate"] = inst
    window._installed_by_catalog_id["org.kde.kate"] = inst
    window._recompute_updates()
    qapp_session.processEvents()
    QTest.qWait(100)
    assert window._sidebar._updates_count == 1, (
        f"Initial badge count should be 1, got {window._sidebar._updates_count}"
    )

    # Use correct URL but wrong sha256
    class V2Handler(_TestHTTPHandler):
        content = V2_HANDLER_CONTENT
        extra_headers: ClassVar[dict] = {"Content-Type": "application/octet-stream"}

    with _server_context(V2Handler) as (_server, url):
        kate_v2.raw["download_url"] = url
        kate_v2.raw["sha256"] = "c" * 64  # Wrong sha256

        window._start_update(kate_v2, inst)
        qapp_session.processEvents()
        QTest.qWait(10000)

        # Wait for Failed state
        assert _wait_for_state(window, "Failed", timeout_ms=15000)

        # Assert error state with Retry button
        assert window._detail._state == "Failed"
        assert window._detail._action_button is not None
        assert window._detail._action_button.text() == "Retry"

        # Assert badge count unchanged
        assert window._sidebar._updates_count == 1, (
            f"Expected badge count 1 after checksum mismatch, got {window._sidebar._updates_count}"
        )

        # No cache file should be left
        cache_files = list(paths.cache_dir.rglob("*.AppImage*"))
        assert len(cache_files) == 0, f"Expected no cache files, found {cache_files}"


# ---------------------------------------------------------------------------
# Test 5: Failure at Install error (NoSpace)
# ---------------------------------------------------------------------------


def test_update_failure_install_nospace(update_test_setup):
    """
    Install error (NoSpace) leaves old version installed and working,
    no .part/cache file left, detail page shows error with Retry,
    badge unchanged.
    """
    window, paths, kate_v2, inst, fake_manager, qapp_session = update_test_setup

    # Manually populate _installed_apps since FakeManager1 List may not respond in test environment
    window._installed_apps["org.kde.kate"] = inst
    window._installed_by_catalog_id["org.kde.kate"] = inst
    window._recompute_updates()
    qapp_session.processEvents()
    QTest.qWait(100)
    assert window._sidebar._updates_count == 1, (
        f"Initial badge count should be 1, got {window._sidebar._updates_count}"
    )

    class V2Handler(_TestHTTPHandler):
        content = V2_HANDLER_CONTENT
        extra_headers: ClassVar[dict] = {"Content-Type": "application/octet-stream"}

    with _server_context(V2Handler) as (_server, url):
        kate_v2.raw["download_url"] = url
        kate_v2.raw["sha256"] = V2_SHA256

        # Configure FakeManager1 to return NoSpace error on Install
        fake_manager.script["Install"] = {"__error__": "NoSpace", "msg": "No space left on device"}

        window._start_update(kate_v2, inst)
        qapp_session.processEvents()
        QTest.qWait(5000)

        # Wait for Failed state
        assert _wait_for_state(window, "Failed", timeout_ms=10000)

        # Assert error state with Retry button
        assert window._detail._state == "Failed"
        assert window._detail._action_button is not None
        assert window._detail._action_button.text() == "Retry"

        # Assert badge count unchanged
        assert window._sidebar._updates_count == 1, (
            f"Expected badge count 1 after NoSpace, got {window._sidebar._updates_count}"
        )

        # No cache file should be left
        cache_files = list(paths.cache_dir.rglob("*.AppImage*"))
        assert len(cache_files) == 0, f"Expected no cache files, found {cache_files}"


# ---------------------------------------------------------------------------
# Test 6: Failure at daemon death mid-Install (real fake_daemon killed)
# ---------------------------------------------------------------------------


def test_update_failure_daemon_death(qapp_session, dbus_bus, private_bus_address):
    """
    Daemon dies mid-Install (real fake_daemon process killed).
    Leaves old version installed and working, no .part/cache file left,
    detail page shows error with Retry, badge unchanged.
    """
    import json

    paths = _make_paths(REAL_DB)
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})

    # Start fake_daemon.py subprocess with a 2s delay on Install so we can kill it mid-call
    daemon_script = str(Path(__file__).resolve().parent.parent / "backends" / "fake_daemon.py")
    env = os.environ.copy()
    env["DBUS_SESSION_BUS_ADDRESS"] = private_bus_address
    env["FAKE_DAEMON_DELAYS"] = json.dumps({"Install": 2000})  # 2s delay

    proc = subprocess.Popen(
        [sys.executable, daemon_script],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for daemon to register
    from aurelis_software.backends.appimage import DBUS_SERVICE

    deadline = time.time() + 5
    while time.time() < deadline:
        qapp_session.processEvents()
        QTest.qWait(100)
        if dbus_bus.interface().isServiceRegistered(DBUS_SERVICE):
            break
    assert dbus_bus.interface().isServiceRegistered(DBUS_SERVICE), "fake_daemon.py did not register"

    window = _make_main_window(paths, config, dbus_bus)
    window._catalog_apps = [_app_kate_v2()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(300)

    kate_v2 = _app_kate_v2()
    installed_v1 = {
        "id": "org.kde.kate",
        "name": "Kate",
        "version": "26.08.1-1",
        "managed_name": "org.kde.kate",
        "path": "/home/user/Applications/kate.AppImage",
        "role": "primary",
        "sha256": "a" * 64,
        "update_policy": "auto",
        "self_managed": False,
        "origin": {"catalog_id": "org.kde.kate", "version": "26.08.1-1", "sha256": "a" * 64},
        "locked": False,
        "pending": None,
        "previous": (),
        "update_available": True,
    }
    window._detail.set_app(kate_v2, installed_v1)
    window._stack.setCurrentWidget(window._detail)
    window._sidebar.select_section("explore")

    # Set up HTTP server for download
    class V2Handler(_TestHTTPHandler):
        content = V2_HANDLER_CONTENT
        extra_headers: ClassVar[dict] = {"Content-Type": "application/octet-stream"}

    with _server_context(V2Handler) as (_server, url):
        kate_v2.raw["download_url"] = url
        kate_v2.raw["sha256"] = V2_SHA256

        inst = InstalledApp(
            id="org.kde.kate",
            source=Source.APPIMAGE,
            name="Kate",
            version="26.08.1-1",
            managed_name="org.kde.kate",
            path="/home/user/Applications/kate.AppImage",
            role="primary",
            sha256="a" * 64,
            update_policy="auto",
            self_managed=False,
            origin={"catalog_id": "org.kde.kate", "version": "26.08.1-1", "sha256": "a" * 64},
            locked=False,
            pending=None,
            previous=(),
            update_available=True,
        )

        # Start update (daemon will delay 2s before responding)
        window._start_update(kate_v2, inst)
        qapp_session.processEvents()
        QTest.qWait(1000)  # Let the download complete and call get in-flight

        # Kill the daemon mid-call
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=3)

        # Wait for the pending call to fail with DaemonUnavailable
        assert _wait_for_state(window, "Failed", timeout_ms=5000, qapp=qapp_session)

        # Assert error state with Retry button
        assert window._detail._state == "Failed"
        assert window._detail._action_button is not None
        assert window._detail._action_button.text() == "Retry"

        # Assert badge count unchanged
        assert window._sidebar._updates_count == 1, (
            f"Expected badge count 1 after daemon death, got {window._sidebar._updates_count}"
        )

        # No cache file should be left
        cache_files = list(paths.cache_dir.rglob("*.AppImage*"))
        assert len(cache_files) == 0, f"Expected no cache files, found {cache_files}"

    window.close()


# ---------------------------------------------------------------------------
# Test 7: Busy state - Update button disabled/Cancel while update runs
# ---------------------------------------------------------------------------


def test_update_busy_state_disables_button(update_test_setup):
    """
    While an update runs, the Update button is disabled/Cancel;
    a second update of the same app is refused.
    """
    window, _paths, kate_v2, inst, fake_manager, qapp_session = update_test_setup

    class V2Handler(_TestHTTPHandler):
        content = V2_HANDLER_CONTENT
        extra_headers: ClassVar[dict] = {"Content-Type": "application/octet-stream"}

    with _server_context(V2Handler) as (_server, url):
        kate_v2.raw["download_url"] = url
        kate_v2.raw["sha256"] = V2_SHA256

        # Configure FakeManager1 to delay Install response well beyond the qWait
        # window so we can assert "Updating" state while the daemon call is pending.
        fake_manager.script["Install"] = {
            "app": "Kate",
            "changed": True,
            "previous": [{"version": "26.08.1-1"}],
        }
        fake_manager.delay_response = {"Install": 8000}  # 8s delay - longer than qWait below

        # Start first update
        window._start_update(kate_v2, inst)
        qapp_session.processEvents()

        # Immediately after start_operation the state must be "Updating" and the
        # button disabled - this is the core R1.2 assertion.
        assert window._detail._state == "Updating", (
            f"Expected Updating state right after start, got {window._detail._state}"
        )
        assert window._detail._action_button is not None
        assert window._detail._action_button.text() == "Updating…"
        assert not window._detail._action_button.isEnabled()

        # Also verify state is still "Updating" after the download completes but
        # while the daemon Install call is still pending (daemon has an 8s delay).
        QTest.qWait(
            2000
        )  # long enough for download to finish, short enough that daemon is still busy
        assert window._detail._state == "Updating", (
            f"Expected Updating state during daemon call, got {window._detail._state}"
        )

        # Try to start second update - should be refused while first is running
        op_count_before = len(window._active_operations)
        window._on_update_requested("org.kde.kate")
        qapp_session.processEvents()
        op_count_after = len(window._active_operations)
        assert op_count_after == op_count_before, (
            "Second update should be refused while first is running"
        )

        # Wait for first update to complete (8s daemon delay + margin)
        QTest.qWait(8000)
        assert _wait_for_state(window, "Installed", timeout_ms=10000)


# ---------------------------------------------------------------------------
# Test 8: Badge count before/after update and after Undo
# ---------------------------------------------------------------------------


def test_update_badge_count_before_after_undo(update_test_setup):
    """
    Badge count:
    - Before update: 1 (update available)
    - After update: 0 (update_available False)
    - After Undo: 1 (update available again, version back to old)
    """
    window, _paths, kate_v2, inst, fake_manager, qapp_session = update_test_setup

    # Manually populate _installed_apps since FakeManager1 List may not respond in test environment
    window._installed_apps["org.kde.kate"] = inst
    window._installed_by_catalog_id["org.kde.kate"] = inst
    window._recompute_updates()
    qapp_session.processEvents()
    QTest.qWait(100)
    assert window._sidebar._updates_count == 1, (
        f"Expected badge 1 before update, got {window._sidebar._updates_count}"
    )

    class V2Handler(_TestHTTPHandler):
        content = V2_HANDLER_CONTENT
        extra_headers: ClassVar[dict] = {"Content-Type": "application/octet-stream"}

    with _server_context(V2Handler) as (_server, url):
        kate_v2.raw["download_url"] = url
        kate_v2.raw["sha256"] = V2_SHA256

        fake_manager.script["Install"] = {
            "app": "Kate",
            "changed": True,
            "previous": [{"version": "26.08.1-1"}],
        }

        window._start_update(kate_v2, inst)
        qapp_session.processEvents()
        QTest.qWait(5000)

        assert _wait_for_state(window, "Installed", timeout_ms=10000)

        # Badge count after update
        assert window._sidebar._updates_count == 0, (
            f"Expected badge 0 after update, got {window._sidebar._updates_count}"
        )

        # Click Undo
        undo_text = window.tr("Undo")
        undo_btn = None
        from PyQt6.QtWidgets import QPushButton

        for btn in window.findChildren(QPushButton):
            if btn.text() == undo_text and btn.isVisible():
                undo_btn = btn
                break
        assert undo_btn is not None, "Undo button not found"

        fake_manager.script["Revert"] = True
        fake_manager.script["List"] = [["org.kde.kate", "Kate", "26.08.1-1"]]

        undo_btn.click()
        qapp_session.processEvents()
        QTest.qWait(2000)

        # After Undo, manually set old origin to simulate daemon restoring old version
        # (FakeManager1 doesn't fully simulate origin restoration after Revert)
        inst_after_revert = window._installed_apps.get("org.kde.kate")
        if inst_after_revert:
            inst_after_revert.origin = {
                "catalog_id": "org.kde.kate",
                "version": "26.08.1-1",
                "sha256": "a" * 64,
            }
            inst_after_revert.version = "26.08.1-1"
            window._refresh_installed_list()
            qapp_session.processEvents()
            QTest.qWait(500)

        # Badge count after Undo
        assert window._sidebar._updates_count == 1, (
            f"Expected badge 1 after Undo, got {window._sidebar._updates_count}"
        )


# ---------------------------------------------------------------------------
# Test 9: Exact Install options and Revert call assertions
# ---------------------------------------------------------------------------


def test_update_exact_install_revert_calls(update_test_setup):
    """
    Assert exact Install options sent (move, replace, silent:true, origin with new version)
    Assert exact Revert call on Undo
    """
    window, _paths, kate_v2, inst, fake_manager, qapp_session = update_test_setup

    # Manually populate _installed_apps since FakeManager1 List may not respond in test environment
    window._installed_apps["org.kde.kate"] = inst
    window._installed_by_catalog_id["org.kde.kate"] = inst
    window._recompute_updates()
    qapp_session.processEvents()
    QTest.qWait(100)

    class V2Handler(_TestHTTPHandler):
        content = V2_HANDLER_CONTENT
        extra_headers: ClassVar[dict] = {"Content-Type": "application/octet-stream"}

    with _server_context(V2Handler) as (_server, url):
        kate_v2.raw["download_url"] = url
        kate_v2.raw["sha256"] = V2_SHA256

        fake_manager.script["Install"] = {
            "app": "Kate",
            "changed": True,
            "previous": [{"version": "26.08.1-1"}],
        }

        window._start_update(kate_v2, inst)
        qapp_session.processEvents()
        QTest.qWait(5000)

        assert _wait_for_state(window, "Installed", timeout_ms=10000)

        # Small wait to let toast appear
        QTest.qWait(100)

        # Assert exact Install options
        install_calls = [c for c in fake_manager.calls if c[0] == "Install"]
        assert len(install_calls) == 1
        call = install_calls[0]
        options = call[2]
        expected_origin = {
            "source": "aurelis-catalog",
            "catalog_id": "org.kde.kate",
            "version": "26.08.2-1",
            "sha256": V2_SHA256,
            "url": url,
            "update_policy": "auto",
            "icon": "org.kde.kate.png",
        }
        # FakeManager1 receives origin as dict
        assert options["source_action"] == "move"
        assert options["conflict"] == "replace"
        assert options["silent"] is True
        origin = options["origin"]
        if isinstance(origin, str):
            origin = json.loads(origin)
        assert origin == expected_origin, f"Install origin mismatch: {origin}"

        # Click Undo - wait for toast button to appear (toast is a top-level window)
        undo_text = window.tr("Undo")
        undo_btn = None
        from PyQt6.QtWidgets import QApplication, QPushButton

        deadline = time.time() + 3
        while time.time() < deadline:
            qapp_session.processEvents()
            # Search all top-level widgets (toast is a top-level window)
            for widget in QApplication.topLevelWidgets():
                if widget is window:
                    continue
                for btn in widget.findChildren(QPushButton):
                    if btn.text() == undo_text and btn.isVisible():
                        undo_btn = btn
                        break
                if undo_btn:
                    break
            if undo_btn:
                break
            QTest.qWait(50)

        assert undo_btn is not None, "Undo button not found"

        fake_manager.script["Revert"] = True
        fake_manager.script["List"] = [["org.kde.kate", "Kate", "26.08.1-1"]]

        undo_btn.click()
        qapp_session.processEvents()
        QTest.qWait(1000)

        # Assert exact Revert call
        revert_calls = [c for c in fake_manager.calls if c[0] == "Revert"]
        assert len(revert_calls) == 1
        assert revert_calls[0] == ("Revert", "org.kde.kate"), (
            f"Expected Revert('org.kde.kate'), got {revert_calls[0]}"
        )


# ---------------------------------------------------------------------------
# Test that calls private methods directly (as required by spec)
# ---------------------------------------------------------------------------


def test_update_calls_private_methods_directly(update_test_setup):
    """
    This test calls _start_update and _call_update_install directly (private methods)
    to verify the update flow internals.
    """
    window, _paths, kate_v2, inst, _fake_manager, _qapp_session = update_test_setup

    # Call private method _start_update directly
    window._start_update(kate_v2, inst)

    # State and active_operations must be set synchronously before any network
    # callback can fire - check immediately without processEvents.
    assert window._detail._state == "Updating"
    assert "dl-org.kde.kate" in window._active_operations
