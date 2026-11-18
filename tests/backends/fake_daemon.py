#!/usr/bin/env python3
"""Standalone FakeManager1 daemon for D-Bus activation testing.

This runs as a separate process and registers the Manager1 service
on a private session bus. Used for testing D-Bus activation and
daemon crash/restart scenarios.
"""

from __future__ import annotations

import json
import os
import signal
import sys
from typing import Any

from PyQt6.QtCore import QCoreApplication, QObject, QTimer, pyqtClassInfo, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusAbstractAdaptor, QDBusConnection

# D-Bus constants
DBUS_SERVICE = "io.github.appimage_launcher.Manager"
DBUS_PATH = "/io/github/appimage_launcher/Manager"
DBUS_INTERFACE = "io.github.appimage_launcher.Manager1"


@pyqtClassInfo("D-Bus Interface", DBUS_INTERFACE)
class Manager1Adaptor(QDBusAbstractAdaptor):
    AppsChanged = pyqtSignal(str, str, str)

    def __init__(self, parent: FakeDaemon) -> None:
        super().__init__(parent)
        self.setAutoRelaySignals(True)
        self._daemon = parent

    def _respond(self, method: str) -> Any:
        return self._daemon.script.get(method, self._daemon.defaults.get(method))

    def _delayed_respond(self, method: str) -> Any:
        delay_ms = self._daemon.delays.get(method, 0)
        if delay_ms > 0:
            # Create a local event loop for the delay
            from PyQt6.QtCore import QEventLoop

            delay_loop = QEventLoop()
            QTimer.singleShot(delay_ms, delay_loop.quit)
            delay_loop.exec()
        return self._respond(method)

    @pyqtSlot("QVariantMap", result="QVariantList")
    def List(self, options: dict) -> list:  # noqa: N802
        self._daemon.calls.append(("List", options))
        return self._delayed_respond("List")

    @pyqtSlot(str, result="QVariantMap")
    def Info(self, name: str) -> dict:  # noqa: N802
        self._daemon.calls.append(("Info", name))
        return self._respond("Info")

    @pyqtSlot(str, result="QVariantMap")
    def Inspect(self, path: str) -> dict:  # noqa: N802
        self._daemon.calls.append(("Inspect", path))
        return self._respond("Inspect")

    @pyqtSlot(str, "QVariantMap", result="QVariantMap")
    def Install(self, path: str, options: dict) -> dict:  # noqa: N802
        self._daemon.calls.append(("Install", path, options))
        return self._delayed_respond("Install")

    @pyqtSlot(str, "QVariantMap", result=bool)
    def Remove(self, name: str, options: dict) -> bool:  # noqa: N802
        self._daemon.calls.append(("Remove", name, options))
        return bool(self._delayed_respond("Remove"))

    @pyqtSlot(str, result=bool)
    def Revert(self, name: str) -> bool:  # noqa: N802
        self._daemon.calls.append(("Revert", name))
        return bool(self._delayed_respond("Revert"))

    @pyqtSlot(str, str, result=bool)
    def SetPolicy(self, name: str, policy: str) -> bool:  # noqa: N802
        self._daemon.calls.append(("SetPolicy", name, policy))
        return bool(self._respond("SetPolicy"))

    @pyqtSlot(str, str, result=bool)
    def SetOrigin(self, name: str, origin: str) -> bool:  # noqa: N802
        self._daemon.calls.append(("SetOrigin", name, origin))
        return bool(self._respond("SetOrigin"))

    @pyqtSlot(result=bool)
    def Reindex(self) -> bool:  # noqa: N802
        self._daemon.calls.append(("Reindex",))
        return bool(self._respond("Reindex"))


class FakeDaemon(QObject):
    def __init__(self, bus: QDBusConnection) -> None:
        super().__init__()
        self._bus = bus
        self.script: dict[str, Any] = {}
        self.calls: list[tuple] = []
        self.delays: dict[str, int] = {}
        self.defaults = {
            "List": [],
            "Info": {},
            "Inspect": {},
            "Install": {"app": "Kate", "changed": True, "previous": []},
            "Remove": True,
            "Revert": True,
            "SetPolicy": True,
            "SetOrigin": True,
            "Reindex": True,
        }
        self._adaptor = Manager1Adaptor(self)

    def register(self) -> bool:
        ok = self._bus.registerService(DBUS_SERVICE)
        if ok:
            self._bus.registerObject(DBUS_PATH, self, QDBusConnection.RegisterOption.ExportAdaptors)
            print(f"Registered service {DBUS_SERVICE}", flush=True)
        else:
            print(f"Failed to register service {DBUS_SERVICE}", flush=True)
        return ok

    def emit_apps_changed(self, kind: str, app_id: str, source: str) -> None:
        self._adaptor.AppsChanged.emit(kind, app_id, source)


def main() -> int:
    # Read config from environment
    bus_address = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    if not bus_address:
        print("DBUS_SESSION_BUS_ADDRESS not set", file=sys.stderr)
        return 1

    # Parse script from stdin if provided
    script_json = os.environ.get("FAKE_DAEMON_SCRIPT")
    delays_json = os.environ.get("FAKE_DAEMON_DELAYS")

    app = QCoreApplication(sys.argv)

    bus = QDBusConnection.connectToBus(bus_address, "fake-daemon")
    if not bus.isConnected():
        print(f"Failed to connect to bus: {bus_address}", file=sys.stderr)
        return 1

    daemon = FakeDaemon(bus)
    if script_json:
        daemon.script = json.loads(script_json)
    if delays_json:
        daemon.delays = json.loads(delays_json)

    if not daemon.register():
        return 1

    # Handle graceful shutdown
    def handle_sigterm() -> None:
        print("Received SIGTERM, shutting down", flush=True)
        app.quit()

    signal.signal(signal.SIGTERM, lambda *_: handle_sigterm())
    signal.signal(signal.SIGINT, lambda *_: handle_sigterm())

    # Auto-quit after 60 seconds as safety
    QTimer.singleShot(60_000, app.quit)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
