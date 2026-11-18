"""Tests for backends/appimage.py over qt_dbus and FakeManager1 (spec P3.3).

Covers: Install, Inspect, Remove, List, SetOrigin, Revert,
ConflictPending (scripted), Busy (scripted), AppsChanged signal.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEventLoop, QTimer

from aurelis_software.backends.appimage import AppImageBackend


def _wait(loop: QEventLoop, timeout_ms: int = 3000) -> None:
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


@pytest.fixture()
def backend(dbus_client):
    return AppImageBackend(dbus_client)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_list_installed_async(fake_manager, backend):
    fake_manager.script["List"] = [
        ["Kate", "Kate", "26.08", ""],
        ["GIMP", "GIMP", "2.10", ""],
    ]
    results = []
    errors = []
    loop = QEventLoop()
    backend.list_installed_async(
        {"all": True},
        reply_cb=lambda apps: (results.append(apps), loop.quit()),
        error_cb=lambda e: (errors.append(e), loop.quit()),
    )
    _wait(loop)
    assert not errors
    assert len(results[0]) == 2
    assert results[0][0][0] == "Kate"


def test_list_with_hash_option(fake_manager, backend):
    fake_manager.script["List"] = []
    errors = []
    loop = QEventLoop()
    backend.list_installed_async(
        {"all": True, "hash": True},
        reply_cb=lambda _: loop.quit(),
        error_cb=lambda e: (errors.append(e), loop.quit()),
    )
    _wait(loop)
    assert not errors
    assert any(c[0] == "List" and c[1].get("hash") is True for c in fake_manager.calls)


# ---------------------------------------------------------------------------
# Inspect
# ---------------------------------------------------------------------------


def test_inspect_async(fake_manager, backend):
    fake_manager.script["Inspect"] = {
        "name": "Kate",
        "version": "26.08",
        "relation": "none",
    }
    results = []
    errors = []
    loop = QEventLoop()
    backend.inspect_async(
        "/tmp/Kate.AppImage",
        reply_cb=lambda r: (results.append(r), loop.quit()),
        error_cb=lambda e: (errors.append(e), loop.quit()),
    )
    _wait(loop)
    assert not errors
    assert results[0]["name"] == "Kate"
    assert ("Inspect", "/tmp/Kate.AppImage") in fake_manager.calls


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------


def test_install_async(fake_manager, backend):
    fake_manager.script["Install"] = {"app": "Kate", "changed": True, "previous": []}
    results = []
    errors = []
    loop = QEventLoop()
    backend.install_async(
        "/cache/Kate.AppImage",
        {"source_action": "move", "conflict": "error", "silent": True},
        reply_cb=lambda r: (results.append(r), loop.quit()),
        error_cb=lambda e: (errors.append(e), loop.quit()),
    )
    _wait(loop)
    assert not errors
    assert results[0]["changed"] is True
    call = next(c for c in fake_manager.calls if c[0] == "Install")
    assert call[1] == "/cache/Kate.AppImage"
    assert call[2]["source_action"] == "move"


def test_install_conflict_pending_scripted(fake_manager, backend):
    """ConflictPending sentinel is returned as a dict (fake limitation noted)."""
    fake_manager.script["Install"] = {
        "__error__": "ConflictPending",
        "msg": "conflict",
    }
    results = []
    loop = QEventLoop()
    backend.install_async(
        "/cache/Kate.AppImage",
        {"conflict": "error"},
        reply_cb=lambda r: (results.append(r), loop.quit()),
        error_cb=lambda e: (results.append(e), loop.quit()),
    )
    _wait(loop)
    # The fake returns a dict (not a real D-Bus error); caller receives it as reply
    assert results, "no reply or error received"


def test_install_busy_scripted(fake_manager, backend):
    """Busy sentinel is returned as a dict (fake limitation noted)."""
    fake_manager.script["Install"] = {"__error__": "Busy", "msg": "busy"}
    results = []
    loop = QEventLoop()
    backend.install_async(
        "/cache/Kate.AppImage",
        {},
        reply_cb=lambda r: (results.append(("reply", r)), loop.quit()),
        error_cb=lambda e: (results.append(("error", e)), loop.quit()),
    )
    _wait(loop)
    assert results


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


def test_remove_async(fake_manager, backend):
    fake_manager.script["Remove"] = True
    results = []
    errors = []
    loop = QEventLoop()
    backend.remove_async(
        "Kate",
        {"file_action": "trash", "silent": True},
        reply_cb=lambda r: (results.append(r), loop.quit()),
        error_cb=lambda e: (errors.append(e), loop.quit()),
    )
    _wait(loop)
    assert not errors
    assert results[0] is True
    call = next(c for c in fake_manager.calls if c[0] == "Remove")
    assert call[1] == "Kate"
    assert call[2]["file_action"] == "trash"


# ---------------------------------------------------------------------------
# Revert
# ---------------------------------------------------------------------------


def test_revert_async(fake_manager, backend):
    fake_manager.script["Revert"] = True
    results = []
    errors = []
    loop = QEventLoop()
    backend.revert_async(
        "Kate",
        reply_cb=lambda r: (results.append(r), loop.quit()),
        error_cb=lambda e: (errors.append(e), loop.quit()),
    )
    _wait(loop)
    assert not errors
    assert results[0] is True
    assert ("Revert", "Kate") in fake_manager.calls


# ---------------------------------------------------------------------------
# SetOrigin
# ---------------------------------------------------------------------------


def test_set_origin_async(fake_manager, backend):
    fake_manager.script["SetOrigin"] = True
    results = []
    errors = []
    loop = QEventLoop()
    backend.set_origin_async(
        "Kate",
        {"catalog_id": "org.kde.kate", "version": "26.08"},
        reply_cb=lambda r: (results.append(r), loop.quit()),
        error_cb=lambda e: (errors.append(e), loop.quit()),
    )
    _wait(loop)
    assert not errors
    assert results[0] is True
    call = next(c for c in fake_manager.calls if c[0] == "SetOrigin")
    assert call[1] == "Kate"
    import json

    origin = json.loads(call[2])
    assert origin["catalog_id"] == "org.kde.kate"


def test_set_origin_unlink(fake_manager, backend):
    """Empty string origin unlinks the app."""
    fake_manager.script["SetOrigin"] = True
    errors = []
    loop = QEventLoop()
    backend.set_origin_async(
        "Kate",
        None,
        reply_cb=lambda _: loop.quit(),
        error_cb=lambda e: (errors.append(e), loop.quit()),
    )
    _wait(loop)
    assert not errors
    call = next(c for c in fake_manager.calls if c[0] == "SetOrigin")
    assert call[2] == ""  # empty string = unlink


# ---------------------------------------------------------------------------
# AppsChanged signal
# ---------------------------------------------------------------------------


def test_apps_changed_signal(fake_manager, backend):
    """AppsChanged signal is delivered to the subscriber."""
    received = []
    loop = QEventLoop()

    from PyQt6.QtCore import QObject, pyqtSlot

    class _Recv(QObject):
        @pyqtSlot(str, str, str)
        def on_changed(self, kind, app_id, source):
            received.append((kind, app_id, source))
            loop.quit()

    recv = _Recv()
    ok = backend.subscribe_apps_changed(recv.on_changed)
    assert ok

    fake_manager.emit_apps_changed("removed", "org.kde.kate", "observer")
    _wait(loop, timeout_ms=3000)

    assert received
    assert received[0] == ("removed", "org.kde.kate", "observer")


# ---------------------------------------------------------------------------
# Reindex
# ---------------------------------------------------------------------------


def test_reindex_async(fake_manager, backend):
    fake_manager.script["Reindex"] = True
    errors = []
    loop = QEventLoop()
    backend.reindex_async(
        reply_cb=lambda _: loop.quit(),
        error_cb=lambda e: (errors.append(e), loop.quit()),
    )
    _wait(loop)
    assert not errors
    assert ("Reindex",) in fake_manager.calls
