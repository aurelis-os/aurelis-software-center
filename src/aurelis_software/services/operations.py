"""Operation queue and state machine (sections 3.4 and 7, Appendix A).

Pure Python: no Qt. One active mutating operation per backend source at a
time, FIFO per source; reads run in parallel (they are not queued here).
A failed operation never blocks the queue.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque

from aurelis_software.backends.base import Backend, Operation, OperationState

MUTATING_KINDS = frozenset({"install", "remove", "update", "revert"})


class OperationQueue:
    def __init__(self) -> None:
        self._pending: dict = defaultdict(deque)  # source -> deque[(operation, backend)]
        self._running: dict = {}  # source -> (operation, backend)
        self._by_id: dict[str, Operation] = {}
        self.logger = logging.getLogger("aurelis_software.services.operations")

    def enqueue(self, operation: Operation, backend: Backend) -> None:
        """Register an operation. Mutating ops run one at a time per source, FIFO."""
        self._by_id[operation.op_id] = operation
        if operation.kind not in MUTATING_KINDS:
            return  # read-style operations are not queued
        source = backend.source
        if source in self._running:
            self._pending[source].append((operation, backend))
        else:
            self._running[source] = (operation, backend)
            operation._on_terminal = lambda: self._free_source_if_terminal(operation, backend)
            self._execute(operation, backend)

    def cancel(self, op_id: str) -> bool:
        """Cancel a pending or running operation. Returns False for unknown ops."""
        operation = self._by_id.get(op_id)
        if operation is None:
            return False
        for source in list(self._pending):
            self._pending[source] = deque(
                (op, b) for op, b in self._pending[source] if op.op_id != op_id
            )
        if operation.state == OperationState.PENDING:
            return operation.cancel()
        if operation.state == OperationState.RUNNING and operation.cancellable:
            operation._cancel_requested = True
            return True
        return operation.cancel()

    def _execute(self, operation: Operation, backend: Backend) -> None:
        if operation.state != OperationState.PENDING:
            self._free_source_if_terminal(operation, backend)
            return
        try:
            operation.start()
            if operation._work is not None:
                operation._work(operation)
        except Exception as exc:  # a failed op never blocks the queue
            self.logger.exception("operation %s failed", operation.op_id)
            operation.fail(str(exc), "")
        self._free_source_if_terminal(operation, backend)

    def _free_source_if_terminal(self, operation: Operation, backend: Backend) -> None:
        if operation.state not in (
            OperationState.FINISHED,
            OperationState.FAILED,
            OperationState.CANCELLED,
        ):
            return  # e.g. a held operation keeps its source busy
        self._running.pop(backend.source, None)
        pending = self._pending.get(backend.source)
        if pending:
            next_operation, next_backend = pending.popleft()
            self._running[backend.source] = (next_operation, next_backend)
            self._execute(next_operation, next_backend)
