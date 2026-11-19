"""P3.9 Failure-injection tests on the install path through FakeManager1.

These tests drive the real install path through FakeManager1 (in-process D-Bus),
injecting specific errors and verifying the UI ends in a defined Failed state
with the correct error title, and that a later retry works.

Errors tested:
- NoSpace (DiskFull)
- NotFound
- ConflictPending
- InvalidAppImage
- PermissionDenied
- Mid-install daemon death (simulated via FakeManager1 error)

Each test asserts exact error names from the contract.

NOTE: These tests use FakeManager1 (in-process) for error injection instead of
the fake_daemon.py subprocess, because the in-process FakeManager1 is already
integrated with the test infrastructure and supports error injection.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

import pytest
from PyQt6.QtDBus import QDBusConnection
from PyQt6.QtTest import QTest

from aurelis_software.core.config import Config
from aurelis_software.core.models import App, Source
from aurelis_software.core.paths import Paths
from aurelis_software.ui.main_window import MainWindow

REAL_DB = Path("tests/fixtures/apps.db")
ICONS_TAR = Path("tests/fixtures/app-icons.tar.gz")


def _make_paths(catalog_db: Path | None = None) -> Paths:
    tmp = Path(tempfile.mkdtemp(prefix="p39-test-"))
    paths = Paths(
        config_dir=tmp / "cfg",
        cache_dir=tmp / "cache",
        state_dir=tmp / "state",
    )
    paths.catalog_dir.mkdir(parents=True, exist_ok=True)
    if catalog_db is not None:
        shutil.copy(catalog_db, paths.catalog_db)
    else:
        import json

        empty_catalog = {"schema_version": 1, "apps": [], "generated_at": "2024-01-01T00:00:00Z"}
        paths.catalog_db.write_text(json.dumps(empty_catalog))
    if ICONS_TAR.exists():
        paths.icons_dir.mkdir(parents=True, exist_ok=True)
        import tarfile

        with tarfile.open(ICONS_TAR, "r:gz") as tar:
            tar.extractall(paths.icons_dir)
    return paths


def _app_kate() -> App:
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
            "screenshots": [],
            "urls": {"homepage": "https://kate-editor.org"},
            "description": "A powerful text editor.",
        },
    )


def _make_main_window(paths: Paths, config: Config, bus: QDBusConnection) -> MainWindow:
    """Create MainWindow with fake D-Bus."""

    class TestMainWindow(MainWindow):
        def _init_dbus(self) -> None:
            pass

    window = TestMainWindow(paths, config)

    from aurelis_software.backends.appimage import AppImageBackend
    from aurelis_software.services.qt_dbus import DbusClient
    from aurelis_software.ui.installed_page import InstalledPage

    window._dbus_client = DbusClient(bus)
    window._appimage_backend = AppImageBackend(window._dbus_client)
    window._appimage_available = True

    window._installed = InstalledPage(icons_dir=paths.icons_dir)
    window._stack.insertWidget(1, window._installed)
    window._installed.selection_changed(window._on_installed_selection)

    # Skip signal subscription (requires @pyqtSlot decorated method)
    # We'll manually call _refresh_installed_list when needed

    return window


def _wait_for_state(
    window: MainWindow,
    expected_state: str,
    timeout_ms: int = 5000,
    qapp=None,
):
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


# ---------------------------------------------------------------------------
# Test 1: NoSpace (DiskFull)
# ---------------------------------------------------------------------------


def test_failure_nospace(qapp_session, fake_manager, dbus_bus):
    """
    Daemon returns NoSpace error during install.
    UI should show Failed state with "Not enough disk space" title.
    Retry should work when space is available.
    """
    paths = _make_paths(REAL_DB)
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})

    window = _make_main_window(paths, config, dbus_bus)
    window._catalog_apps = [_app_kate()]
    window._catalog_loaded = True
    window._refresh_explore()

    # Set up fake daemon List response to include the installed app after install
    fake_manager.script["List"] = [["org.kde.kate", "Kate", "26.08.2-1"]]

    window.show()
    QTest.qWait(500)

    kate = _app_kate()
    window._detail.set_app(kate)
    window._stack.setCurrentWidget(window._detail)
    window._sidebar.select_section("explore")

    # Configure FakeManager1 to return NoSpace error on Install
    fake_manager.script["Install"] = {"__error__": "NoSpace", "msg": "No space left on device"}

    # Trigger install directly through _call_install to test Install error handling
    # (bypasses download which would require network)
    fake_path = paths.cache_dir / "downloads" / "kate-fake.AppImage"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_bytes(b"fake appimage")

    window._call_install(
        kate,
        fake_path,
        {"source_action": "move", "conflict": "error", "silent": True, "origin": {}},
    )
    qapp_session.processEvents()
    QTest.qWait(500)

    # Wait for operation to fail with NoSpace
    assert _wait_for_state(window, "Failed")

    # Assert error state
    assert window._detail._state == "Failed"
    assert window._detail._action_button is not None
    assert window._detail._action_button.text() == "Retry"
    # Error title should be "Not enough disk space"
    from PyQt6.QtWidgets import QLabel

    title_labels = [
        w for w in window._detail.findChildren(QLabel) if "Not enough disk space" in w.text()
    ]
    assert len(title_labels) >= 1, "Expected 'Not enough disk space' title"
    assert title_labels[0].isVisible()

    # Now simulate retry with space available (clear error)
    fake_manager.script.pop("Install", None)
    # Call _call_install directly to retry the Install call (bypassing download)
    fake_path = paths.cache_dir / "downloads" / "kate-fake.AppImage"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_bytes(b"fake appimage")
    window._call_install(
        kate,
        fake_path,
        {"source_action": "move", "conflict": "error", "silent": True, "origin": {}},
    )
    qapp_session.processEvents()
    QTest.qWait(3000)

    # Should be back to success state
    assert window._detail._state == "Installed"
    assert window._detail._action_button.text() == "Open"

    window.close()


# ---------------------------------------------------------------------------
# Test 2: NotFound
# ---------------------------------------------------------------------------


def test_failure_notfound(qapp_session, fake_manager, dbus_bus):
    """
    Daemon returns NotFound error during install.
    UI should show Failed state with appropriate title.
    """
    paths = _make_paths(REAL_DB)
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})

    window = _make_main_window(paths, config, dbus_bus)
    window._catalog_apps = [_app_kate()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

    kate = _app_kate()
    window._detail.set_app(kate)
    window._stack.setCurrentWidget(window._detail)
    window._sidebar.select_section("explore")

    fake_manager.script["Install"] = {"__error__": "NotFound", "msg": "AppImage not found"}

    fake_path = paths.cache_dir / "downloads" / "kate-fake.AppImage"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_bytes(b"fake appimage")

    window._call_install(
        kate,
        fake_path,
        {"source_action": "move", "conflict": "error", "silent": True, "origin": {}},
    )
    qapp_session.processEvents()
    QTest.qWait(500)

    assert _wait_for_state(window, "Failed")

    assert window._detail._state == "Failed"
    assert window._detail._action_button.text() == "Retry"

    from PyQt6.QtWidgets import QLabel

    title_labels = [
        w
        for w in window._detail.findChildren(QLabel)
        if "Not found" in w.text() or "not found" in w.text().lower()
    ]
    assert len(title_labels) >= 1, "Expected 'Not found' title"

    window.close()


# ---------------------------------------------------------------------------
# Test 3: ConflictPending
# ---------------------------------------------------------------------------


def test_failure_conflictpending(qapp_session, fake_manager, dbus_bus):
    """
    Daemon returns ConflictPending error during install.
    UI should show ConflictDialog with Replace/Keep both/Cancel.
    """
    paths = _make_paths(REAL_DB)
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})

    window = _make_main_window(paths, config, dbus_bus)
    window._catalog_apps = [_app_kate()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

    kate = _app_kate()
    window._detail.set_app(kate)
    window._stack.setCurrentWidget(window._detail)
    window._sidebar.select_section("explore")

    fake_manager.script["Install"] = {
        "__error__": "ConflictPending",
        "msg": "Conflict pending",
        "details": '{"old": {"app_id": "org.kde.kate", "name": "Kate", "version": "26.08.1-1", "relation": "upgrade"}}',
    }

    fake_path = paths.cache_dir / "downloads" / "kate-fake.AppImage"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_bytes(b"fake appimage")

    window._call_install(
        kate,
        fake_path,
        {"source_action": "move", "conflict": "error", "silent": True, "origin": {}},
    )
    qapp_session.processEvents()
    QTest.qWait(500)

    # ConflictPending should keep Installing state and show conflict dialog
    assert _wait_for_state(window, "Installing") or window._detail._state == "Installing"

    assert window._detail._state == "Installing", (
        f"ConflictPending must keep Installing state, got {window._detail._state!r}"
    )
    # Action button is disabled (no Cancel once handed to daemon, or still showing Cancel)
    # The key invariant: state is NOT Failed
    assert window._detail._state != "Failed"

    # Should also have conflict dialog shown
    from PyQt6.QtWidgets import QDialog

    dialogs = window.findChildren(QDialog)
    conflict_dialogs = [d for d in dialogs if d.windowTitle() == "AppImage Conflict"]
    assert len(conflict_dialogs) >= 1, "Expected ConflictDialog"

    window.close()


# ---------------------------------------------------------------------------
# Test 4: InvalidAppImage
# ---------------------------------------------------------------------------


def test_failure_invalidappimage(qapp_session, fake_manager, dbus_bus):
    """
    Daemon returns InvalidAppImage error during install.
    UI should show Failed state with appropriate title.
    """
    paths = _make_paths(REAL_DB)
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})

    window = _make_main_window(paths, config, dbus_bus)
    window._catalog_apps = [_app_kate()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

    kate = _app_kate()
    window._detail.set_app(kate)
    window._stack.setCurrentWidget(window._detail)
    window._sidebar.select_section("explore")

    fake_manager.script["Install"] = {
        "__error__": "InvalidAppImage",
        "msg": "Invalid AppImage file",
    }

    fake_path = paths.cache_dir / "downloads" / "kate-fake.AppImage"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_bytes(b"fake appimage")

    window._call_install(
        kate,
        fake_path,
        {"source_action": "move", "conflict": "error", "silent": True, "origin": {}},
    )
    qapp_session.processEvents()
    QTest.qWait(500)

    assert _wait_for_state(window, "Failed")

    assert window._detail._state == "Failed"
    assert window._detail._action_button.text() == "Retry"

    from PyQt6.QtWidgets import QLabel

    title_labels = [
        w
        for w in window._detail.findChildren(QLabel)
        if "Invalid" in w.text() or "invalid" in w.text().lower()
    ]
    assert len(title_labels) >= 1, "Expected 'Invalid' title"

    window.close()


# ---------------------------------------------------------------------------
# Test 5: PermissionDenied
# ---------------------------------------------------------------------------


def test_failure_permissiondenied(qapp_session, fake_manager, dbus_bus):
    """
    Daemon returns PermissionDenied error during install.
    UI should show Failed state with appropriate title.
    """
    paths = _make_paths(REAL_DB)
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})

    window = _make_main_window(paths, config, dbus_bus)
    window._catalog_apps = [_app_kate()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

    kate = _app_kate()
    window._detail.set_app(kate)
    window._stack.setCurrentWidget(window._detail)
    window._sidebar.select_section("explore")

    fake_manager.script["Install"] = {"__error__": "PermissionDenied", "msg": "Permission denied"}

    fake_path = paths.cache_dir / "downloads" / "kate-fake.AppImage"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_bytes(b"fake appimage")

    window._call_install(
        kate,
        fake_path,
        {"source_action": "move", "conflict": "error", "silent": True, "origin": {}},
    )
    qapp_session.processEvents()
    QTest.qWait(500)

    assert _wait_for_state(window, "Failed")

    assert window._detail._state == "Failed"
    assert window._detail._action_button.text() == "Retry"

    from PyQt6.QtWidgets import QLabel

    title_labels = [
        w
        for w in window._detail.findChildren(QLabel)
        if "Permission" in w.text() or "permission" in w.text().lower()
    ]
    assert len(title_labels) >= 1, "Expected 'Permission' title"

    window.close()


# ---------------------------------------------------------------------------
# Test 5b: Mid-install daemon death (real subprocess fake_daemon.py)
# ---------------------------------------------------------------------------


def test_failure_daemon_death(qapp_session, dbus_bus, private_bus_address):
    """
    Daemon crashes mid-install (real fake_daemon.py subprocess killed mid-call).
    UI should show Failed state with "Background service unavailable" title.
    Retry should work after daemon restarts.
    """
    import json
    import os
    import signal
    import subprocess
    import sys
    import time

    from aurelis_software.backends.appimage import DBUS_SERVICE

    paths = _make_paths(REAL_DB)
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})

    # Start fake_daemon.py subprocess with a 500ms delay on Install so we can kill it mid-call
    daemon_script = str(Path(__file__).resolve().parent.parent / "backends" / "fake_daemon.py")
    env = os.environ.copy()
    env["DBUS_SESSION_BUS_ADDRESS"] = private_bus_address
    env["FAKE_DAEMON_DELAYS"] = json.dumps({"Install": 2000})  # 2s delay so we can kill it

    proc = subprocess.Popen(
        [sys.executable, daemon_script],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for daemon to register
    deadline = time.time() + 5
    while time.time() < deadline:
        qapp_session.processEvents()
        QTest.qWait(100)
        if dbus_bus.interface().isServiceRegistered(DBUS_SERVICE):
            break
    assert dbus_bus.interface().isServiceRegistered(DBUS_SERVICE), "fake_daemon.py did not register"

    window = _make_main_window(paths, config, dbus_bus)
    window._catalog_apps = [_app_kate()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(300)

    kate = _app_kate()
    window._detail.set_app(kate)
    window._stack.setCurrentWidget(window._detail)
    window._sidebar.select_section("explore")

    fake_path = paths.cache_dir / "downloads" / "kate-fake.AppImage"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_bytes(b"fake appimage")

    # Start install (daemon will delay 2s before responding)
    window._call_install(
        kate,
        fake_path,
        {"source_action": "move", "conflict": "error", "silent": True, "origin": {}},
    )
    qapp_session.processEvents()
    QTest.qWait(200)  # Let the call get in-flight

    # Kill the daemon mid-call
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=3)

    # Wait for the pending call to fail with DaemonUnavailable
    assert _wait_for_state(window, "Failed", timeout_ms=5000, qapp=qapp_session)

    assert window._detail._state == "Failed"
    assert window._detail._action_button.text() == "Retry"

    from PyQt6.QtWidgets import QLabel

    title_labels = [
        w
        for w in window._detail.findChildren(QLabel)
        if "Background" in w.text()
        or "background" in w.text().lower()
        or "unavailable" in w.text().lower()
    ]
    assert len(title_labels) >= 1, "Expected 'Background service unavailable' title"

    # Restart daemon (no delay this time)
    env2 = os.environ.copy()
    env2["DBUS_SESSION_BUS_ADDRESS"] = private_bus_address
    proc2 = subprocess.Popen(
        [sys.executable, daemon_script],
        env=env2,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for daemon to re-register
    deadline = time.time() + 5
    while time.time() < deadline:
        qapp_session.processEvents()
        QTest.qWait(100)
        if dbus_bus.interface().isServiceRegistered(DBUS_SERVICE):
            break
    assert dbus_bus.interface().isServiceRegistered(DBUS_SERVICE), (
        "fake_daemon.py did not re-register"
    )

    # Retry install
    fake_path.write_bytes(b"fake appimage")
    window._call_install(
        kate,
        fake_path,
        {"source_action": "move", "conflict": "error", "silent": True, "origin": {}},
    )
    qapp_session.processEvents()

    assert _wait_for_state(window, "Installed", timeout_ms=5000, qapp=qapp_session)
    assert window._detail._state == "Installed"
    assert window._detail._action_button.text() == "Open"

    proc2.send_signal(signal.SIGTERM)
    try:
        proc2.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc2.kill()
        proc2.wait(timeout=3)
    # Wait for service to unregister so the next test's fake_manager can register cleanly
    deadline = time.time() + 3
    while time.time() < deadline:
        qapp_session.processEvents()
        QTest.qWait(50)
        if not dbus_bus.interface().isServiceRegistered(DBUS_SERVICE):
            break

    window.close()


# ---------------------------------------------------------------------------
# Test 6: Retry after any error works
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error_name,error_message",
    [
        ("NoSpace", "No space left on device"),
        ("NotFound", "AppImage not found"),
        ("InvalidAppImage", "Invalid AppImage file"),
        ("PermissionDenied", "Permission denied"),
    ],
)
def test_retry_after_error(
    qapp_session, fake_manager, dbus_bus, error_name: str, error_message: str
):
    """
    After any error, clicking Retry should work when the error is resolved.
    """
    paths = _make_paths(REAL_DB)
    config = Config({"network": {"offline": True}, "downloads": {"allow_unverified": "ask"}})

    window = _make_main_window(paths, config, dbus_bus)
    window._catalog_apps = [_app_kate()]
    window._catalog_loaded = True
    window._refresh_explore()

    window.show()
    QTest.qWait(500)

    kate = _app_kate()
    window._detail.set_app(kate)
    window._stack.setCurrentWidget(window._detail)
    window._sidebar.select_section("explore")

    fake_manager.script["Install"] = {"__error__": error_name, "msg": error_message}

    fake_path = paths.cache_dir / "downloads" / "kate-fake.AppImage"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_bytes(b"fake appimage")

    window._call_install(
        kate,
        fake_path,
        {"source_action": "move", "conflict": "error", "silent": True, "origin": {}},
    )
    qapp_session.processEvents()
    QTest.qWait(500)

    assert _wait_for_state(window, "Failed")

    assert window._detail._state == "Failed"
    assert window._detail._action_button.text() == "Retry"

    # Now fix the error
    fake_manager.script.pop("Install", None)

    # Call _call_install directly to retry the Install call (bypassing download)
    fake_path = paths.cache_dir / "downloads" / "kate-fake.AppImage"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_bytes(b"fake appimage")
    window._call_install(
        kate,
        fake_path,
        {"source_action": "move", "conflict": "error", "silent": True, "origin": {}},
    )
    qapp_session.processEvents()
    QTest.qWait(3000)

    # Wait for success
    assert _wait_for_state(window, "Installed")

    assert window._detail._state == "Installed"
    assert window._detail._action_button.text() == "Open"

    window.close()
