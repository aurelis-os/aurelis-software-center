"""Deterministic in-memory backends for tests and dev (section P1.9).

Scripted backends: every operation is an ``Operation`` whose work is
replayed from a small script, so every UI state is testable without
touching the network, ``pacman``, ``flatpak`` or the daemon.
"""

from __future__ import annotations

import uuid

from aurelis_software.backends.base import Backend, Capabilities, Operation
from aurelis_software.core.models import App, InstalledApp, Source, UpdateInfo


class FakeBackend(Backend):
    def __init__(
        self,
        source: Source = Source.APPIMAGE,
        available: bool = True,
        installed: list[InstalledApp] | None = None,
        updates: list[UpdateInfo] | None = None,
        install_mode: str = "ok",
    ) -> None:
        self.source = source
        self.available = available
        self._installed = list(installed or [])
        self._updates = list(updates or [])
        self.install_mode = install_mode  # "ok" | "fail" | "hold"
        self.calls: list[tuple[str, tuple, dict]] = []

    def capabilities(self) -> Capabilities:
        return Capabilities(
            install=True,
            remove=True,
            update=True,
            revert=True,
            set_policy=True,
            set_origin=True,
            list_hash=True,
        )

    def list_installed(self) -> list[InstalledApp]:
        return list(self._installed)

    def list_updates(self) -> list[UpdateInfo]:
        return list(self._updates)

    def open(self, installed: InstalledApp) -> None:
        self.calls.append(("open", (installed,), {}))

    def _op_id(self) -> str:
        return f"fake-{uuid.uuid4().hex[:8]}"

    def install(self, app: App, **opts) -> Operation:
        self.calls.append(("install", (app,), opts))

        def work(op: Operation) -> None:
            if self.install_mode == "fail":
                op.fail("tool-failed", "simulated install failure")
                return
            op.progress("download", 0.5, "downloading")
            if self.install_mode == "hold":
                return  # stay RUNNING until released externally
            op.progress("handoff", None, "Finishing…")
            op.finish()

        return Operation(self._op_id(), app.key, "install", cancellable=True, work=work)

    def remove(self, installed: InstalledApp) -> Operation:
        self.calls.append(("remove", (installed,), {}))

        def work(op: Operation) -> None:
            op.progress("remove", None, "removing")
            op.finish()

        return Operation(self._op_id(), installed.id, "remove", cancellable=True, work=work)

    def update(self, app: App, installed: InstalledApp) -> Operation:
        self.calls.append(("update", (app, installed), {}))

        def work(op: Operation) -> None:
            op.progress("download", None, "updating")
            op.finish()

        return Operation(self._op_id(), app.key, "update", cancellable=True, work=work)

    def revert(self, installed: InstalledApp) -> Operation:
        self.calls.append(("revert", (installed,), {}))

        def work(op: Operation) -> None:
            op.finish()

        return Operation(self._op_id(), installed.id, "revert", cancellable=True, work=work)

    def set_policy(self, installed: InstalledApp, policy: str) -> None:
        self.calls.append(("set_policy", (installed, policy), {}))

    def set_origin(self, installed: InstalledApp, origin: dict | None) -> None:
        self.calls.append(("set_origin", (installed, origin), {}))
