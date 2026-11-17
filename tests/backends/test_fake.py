"""Tests for backends/fake.py (section P1.9): scripted in-memory backend."""

from __future__ import annotations

from aurelis_software.backends.base import OperationState
from aurelis_software.backends.fake import FakeBackend
from aurelis_software.core.models import App, InstalledApp, Source


def _app(app_id: str = "org.example.app") -> App:
    return App(key=f"appimage:{app_id}", id=app_id, source=Source.APPIMAGE, name="App", summary="s")


def _installed(app_id: str = "x") -> InstalledApp:
    return InstalledApp(id=app_id, source=Source.APPIMAGE, name="x")


def test_fake_capabilities():
    backend = FakeBackend()
    caps = backend.capabilities()
    assert caps.install and caps.remove and caps.update
    assert caps.revert and caps.set_policy and caps.set_origin and caps.list_hash


def test_fake_install_ok_runs_to_finish():
    backend = FakeBackend(install_mode="ok")
    op = backend.install(_app())
    assert op.state == OperationState.PENDING
    op.start()
    op._work(op)
    assert op.state == OperationState.FINISHED
    assert op.result.ok is True
    steps = [e.step for e in op.events]
    assert "download" in steps and "handoff" in steps and "finish" in steps


def test_fake_install_fail():
    backend = FakeBackend(install_mode="fail")
    op = backend.install(_app())
    op.start()
    op._work(op)
    assert op.state == OperationState.FAILED
    assert op.result.ok is False
    assert op.result.error == "tool-failed"


def test_fake_install_hold_stays_running():
    backend = FakeBackend(install_mode="hold")
    op = backend.install(_app())
    op.start()
    op._work(op)
    assert op.state == OperationState.RUNNING
    assert op.result is None


def test_fake_remove_update_revert_record_calls():
    backend = FakeBackend()
    backend.remove(_installed())
    backend.update(_app(), _installed())
    backend.revert(_installed())
    backend.set_policy(_installed(), "pinned")
    backend.set_origin(_installed(), {"catalog_id": "x"})
    kinds = [call[0] for call in backend.calls]
    assert "remove" in kinds and "update" in kinds and "revert" in kinds
    assert backend.calls[-2][0] == "set_policy"
    assert backend.calls[-1][0] == "set_origin"
