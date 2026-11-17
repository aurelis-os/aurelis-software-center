"""Backend interface (section 6).

Pure Python: no Qt here. Qt signal/slot adapters for ``Operation`` are
added in Phase 3 (services/qt_*.py), keeping the layering rule intact.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from aurelis_software.core.models import App, InstalledApp, Source, UpdateInfo


class OperationState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class OperationEvent:
    op_id: str
    app_key: str | None = None
    kind: str | None = None  # install | remove | update | revert
    step: str | None = None  # download | verify | handoff | install | remove | update
    fraction: float | None = None
    message: str = ""


@dataclass(slots=True)
class OperationResult:
    op_id: str
    ok: bool
    error: str | None = None
    details: str = ""


class Capabilities:
    def __init__(
        self,
        *,
        install: bool = False,
        remove: bool = False,
        update: bool = False,
        revert: bool = False,
        set_policy: bool = False,
        set_origin: bool = False,
        list_hash: bool = False,
    ) -> None:
        self.install = install
        self.remove = remove
        self.update = update
        self.revert = revert
        self.set_policy = set_policy
        self.set_origin = set_origin
        self.list_hash = list_hash


class Operation:
    """A single operation state machine.

    The backend drives the life cycle (``start``/``progress``/``finish``/
    ``fail``); the queue owns ordering and cancellation. Events are
    recorded so every UI state is testable without Qt.
    """

    def __init__(
        self,
        op_id: str,
        app_key: str,
        kind: str,
        *,
        cancellable: bool = True,
        work=None,
        on_terminal=None,
    ) -> None:
        self.op_id = op_id
        self.app_key = app_key
        self.kind = kind
        self.cancellable = cancellable
        self.state = OperationState.PENDING
        self.events: list[OperationEvent] = []
        self.result: OperationResult | None = None
        self._work = work
        self._on_terminal = on_terminal
        self._cancel_requested = False

    def start(self) -> None:
        self.state = OperationState.RUNNING
        self.events.append(
            OperationEvent(self.op_id, self.app_key, self.kind, "start", None, "started")
        )

    def progress(self, step: str, fraction: float | None = None, message: str = "") -> None:
        self.events.append(
            OperationEvent(self.op_id, self.app_key, self.kind, step, fraction, message)
        )

    def finish(self) -> None:
        self.state = OperationState.FINISHED
        self.result = OperationResult(self.op_id, True)
        self.events.append(
            OperationEvent(self.op_id, self.app_key, self.kind, "finish", 1.0, "finished")
        )
        self._fire_terminal()

    def fail(self, error: str, details: str = "") -> None:
        self.state = OperationState.FAILED
        self.result = OperationResult(self.op_id, False, error, details)
        self.events.append(OperationEvent(self.op_id, self.app_key, self.kind, "fail", None, error))
        self._fire_terminal()

    def _fire_terminal(self) -> None:
        if self._on_terminal is not None:
            self._on_terminal()

    def cancel(self) -> bool:
        if not self.cancellable:
            return False
        if self.state in (
            OperationState.FINISHED,
            OperationState.FAILED,
            OperationState.CANCELLED,
        ):
            return False
        self._cancel_requested = True
        if self.state == OperationState.PENDING:
            self.state = OperationState.CANCELLED
            self.result = OperationResult(self.op_id, False, "cancelled")
            self.events.append(
                OperationEvent(self.op_id, self.app_key, self.kind, "cancel", None, "cancelled")
            )
            self._fire_terminal()
        return True

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested


class Backend(ABC):
    source: Source
    available: bool = True

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abstractmethod
    def list_installed(self) -> list[InstalledApp]: ...

    @abstractmethod
    def list_updates(self) -> list[UpdateInfo]: ...

    @abstractmethod
    def install(self, app: App, **opts) -> Operation: ...

    @abstractmethod
    def remove(self, installed: InstalledApp) -> Operation: ...

    @abstractmethod
    def update(self, app: App, installed: InstalledApp) -> Operation: ...

    @abstractmethod
    def open(self, installed: InstalledApp) -> None: ...

    def revert(self, installed: InstalledApp) -> Operation:
        msg = f"{self.source} backend does not support revert"
        raise NotImplementedError(msg)

    def set_policy(self, installed: InstalledApp, policy: str) -> None:
        msg = f"{self.source} backend does not support set_policy"
        raise NotImplementedError(msg)

    def set_origin(self, installed: InstalledApp, origin: dict | None) -> None:
        msg = f"{self.source} backend does not support set_origin"
        raise NotImplementedError(msg)
