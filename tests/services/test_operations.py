"""Tests for services/operations.py (sections 3.4 and 7): queue, state machine,
FIFO ordering, failure isolation and cancel rules."""

from __future__ import annotations

from aurelis_software.backends.base import OperationState
from aurelis_software.backends.fake import FakeBackend
from aurelis_software.core.models import App, Source
from aurelis_software.services.operations import OperationQueue


def _app(app_id: str) -> App:
    return App(
        key=f"appimage:{app_id}", id=app_id, source=Source.APPIMAGE, name=app_id, summary="s"
    )


def test_queue_runs_install_fifo():
    backend = FakeBackend(install_mode="hold")
    queue = OperationQueue()

    held = backend.install(_app("held"))
    queue.enqueue(held, backend)
    assert held.state == OperationState.RUNNING
    assert held.events[0].step == "start"
    assert held.events[-1].step == "download"

    backend.install_mode = "ok"
    follower = backend.install(_app("follower"))
    queue.enqueue(follower, backend)
    assert follower.state == OperationState.PENDING
    assert len(queue._pending[backend.source]) == 1

    held.finish()
    assert follower.state == OperationState.FINISHED
    assert follower.events[0].step == "start"


def test_queue_failure_does_not_block():
    failing_backend = FakeBackend(install_mode="fail")
    ok_backend = FakeBackend()
    queue = OperationQueue()

    failing = failing_backend.install(_app("failing"))
    queue.enqueue(failing, failing_backend)
    assert failing.state == OperationState.FAILED
    assert failing.result.ok is False
    assert failing.result.error == "tool-failed"

    follower = ok_backend.install(_app("follower"))
    queue.enqueue(follower, ok_backend)
    assert follower.state == OperationState.FINISHED
    assert follower.result.ok is True


def test_queue_cancel_pending_operation():
    backend = FakeBackend(install_mode="hold")
    queue = OperationQueue()

    held = backend.install(_app("held"))
    queue.enqueue(held, backend)

    pending = backend.install(_app("pending"))
    queue.enqueue(pending, backend)
    assert pending.state == OperationState.PENDING

    assert queue.cancel(pending.op_id) is True
    assert pending.state == OperationState.CANCELLED
    assert pending.result.error == "cancelled"
    assert len(queue._pending[backend.source]) == 0
    assert held.state == OperationState.RUNNING  # still running


def test_queue_cancel_running_requests_cancellation():
    backend = FakeBackend(install_mode="hold")
    queue = OperationQueue()
    held = backend.install(_app("held"))
    queue.enqueue(held, backend)

    assert queue.cancel(held.op_id) is True
    assert held.cancel_requested is True
    assert held.state == OperationState.RUNNING  # work already running; request recorded


def test_queue_cancel_finished_operation_is_noop():
    backend = FakeBackend()
    queue = OperationQueue()
    op = backend.install(_app("done"))
    queue.enqueue(op, backend)
    assert op.state == OperationState.FINISHED
    assert queue.cancel(op.op_id) is False


def test_queue_cancel_unknown_operation_is_false():
    queue = OperationQueue()
    assert queue.cancel("no-such-op") is False
