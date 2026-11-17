"""Tests for backends/base.py (section 6): operation state machine."""

from __future__ import annotations

from aurelis_software.backends.base import Backend, Operation, OperationState
from aurelis_software.core.models import App, InstalledApp, Source, UpdateInfo


def _app(app_id: str = "org.example.app") -> App:
    return App(key=f"appimage:{app_id}", id=app_id, source=Source.APPIMAGE, name="App", summary="s")


def _installed(app_id: str = "org.example.app") -> InstalledApp:
    return InstalledApp(id=app_id, source=Source.APPIMAGE, name="App")


def test_operation_lifecycle():
    op = Operation("op-1", _app().key, "install")
    assert op.state == OperationState.PENDING
    assert op.result is None

    op.start()
    assert op.state == OperationState.RUNNING
    assert op.events[0].step == "start"
    assert op.events[0].op_id == "op-1"
    assert op.events[0].app_key == _app().key
    assert op.events[0].kind == "install"

    op.progress("download", 0.5, "halfway")
    assert op.events[1].step == "download"
    assert op.events[1].fraction == 0.5

    op.finish()
    assert op.state == OperationState.FINISHED
    assert op.result is not None
    assert op.result.ok is True
    assert op.events[-1].step == "finish"


def test_operation_fail():
    op = Operation("op-2", _app().key, "remove")
    op.fail("tool-failed", "simulated stderr tail")
    assert op.state == OperationState.FAILED
    assert op.result.ok is False
    assert op.result.error == "tool-failed"
    assert op.result.details == "simulated stderr tail"
    assert op.events[-1].step == "fail"


def test_operation_cancel_pending():
    op = Operation("op-3", _app().key, "install")
    assert op.cancel() is True
    assert op.state == OperationState.CANCELLED
    assert op.result.ok is False
    assert op.result.error == "cancelled"


def test_operation_cancel_after_finish_is_noop():
    op = Operation("op-4", _app().key, "install")
    op.finish()
    assert op.cancel() is False
    assert op.state == OperationState.FINISHED


def test_operation_cancel_after_fail_is_noop():
    op = Operation("op-5", _app().key, "install")
    op.fail("boom")
    assert op.cancel() is False


def test_operation_uncancellable():
    op = Operation("op-6", _app().key, "install", cancellable=False)
    assert op.cancel() is False
    assert op.state == OperationState.PENDING


def test_backend_is_abstract():
    try:
        Backend()  # type: ignore[abstract-class]
    except TypeError:
        return
    msg = "Backend should not be directly instantiable"
    raise AssertionError(msg)


def test_update_info_defaults():
    info = UpdateInfo(app_key="appimage:org.example.app")
    assert info.method == ""
    assert info.size is None
