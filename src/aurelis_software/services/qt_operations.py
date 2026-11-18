"""Qt adapter for Operation state machine (P3.4).

Wraps the pure-Python Operation from backends/base.py and exposes
signals for UI consumption. Keeps Qt out of the core layer.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from aurelis_software.backends.base import (
    Operation,
    OperationEvent,
    OperationResult,
    OperationState,
)


class QtOperation(QObject):
    """Qt signal emitter that mirrors a core Operation's life cycle.

    Connect to ``event`` for progress/start/finish/fail, and ``finished``
    for the terminal result.  The core Operation is still driven by the
    backend / queue; this class only observes and re-emits.
    """

    # Emitted for every OperationEvent added to the core Operation
    event = pyqtSignal(OperationEvent)
    # Emitted once when the operation reaches a terminal state
    finished = pyqtSignal(OperationResult)

    def __init__(
        self,
        operation: Operation,
        *,
        progress_cb: Callable[[Operation], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._operation = operation
        self._progress_cb = progress_cb
        self._last_event_index = 0
        self._check_timer = None

        # If the operation already has events (e.g. started synchronously),
        # emit them immediately
        if operation.events:
            self._emit_new_events()

    @property
    def operation(self) -> Operation:
        return self._operation

    @property
    def op_id(self) -> str:
        return self._operation.op_id

    @property
    def app_key(self) -> str:
        return self._operation.app_key

    @property
    def kind(self) -> str:
        return self._operation.kind

    @property
    def state(self) -> OperationState:
        return self._operation.state

    @property
    def cancellable(self) -> bool:
        return self._operation.cancellable

    @property
    def cancel_requested(self) -> bool:
        return self._operation.cancel_requested

    def cancel(self) -> bool:
        """Request cancellation. Returns True if cancellation was accepted."""
        return self._operation.cancel()

    def poll(self) -> None:
        """Poll for new events from the core operation (call from a QTimer)."""
        self._emit_new_events()

    def _emit_new_events(self) -> None:
        events = self._operation.events
        for i in range(self._last_event_index, len(events)):
            self.event.emit(events[i])
        self._last_event_index = len(events)

        if (
            self._operation.state
            in (
                OperationState.FINISHED,
                OperationState.FAILED,
                OperationState.CANCELLED,
            )
            and self._operation.result is not None
        ):
            self.finished.emit(self._operation.result)
            # Stop polling if we were polling
            if self._check_timer is not None:
                self._check_timer.stop()
                self._check_timer = None


class QtOperationFactory:
    """Factory that wraps backend operations in QtOperation and manages polling."""

    def __init__(self, poll_interval_ms: int = 100) -> None:
        self._poll_interval_ms = poll_interval_ms
        self._active: dict[str, QtOperation] = {}

    def wrap(
        self,
        operation: Operation,
        progress_cb: Callable[[Operation], None] | None = None,
    ) -> QtOperation:
        qt_op = QtOperation(operation, progress_cb=progress_cb)
        self._active[operation.op_id] = qt_op

        # Start polling for new events
        from PyQt6.QtCore import QTimer

        timer = QTimer(qt_op)
        timer.setInterval(self._poll_interval_ms)
        timer.timeout.connect(qt_op.poll)
        timer.start()
        qt_op._check_timer = timer

        # Clean up when finished
        def _cleanup(result: OperationResult) -> None:
            self._active.pop(operation.op_id, None)
            if timer.isActive():
                timer.stop()

        qt_op.finished.connect(_cleanup)
        return qt_op

    def get(self, op_id: str) -> QtOperation | None:
        return self._active.get(op_id)

    def all(self) -> list[QtOperation]:
        return list(self._active.values())
