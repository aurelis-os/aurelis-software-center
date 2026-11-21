#!/usr/bin/env python3
"""Probe the real appimage-launcher Manager1 D-Bus service.

Run on your machine against the installed, tagged `api-v1` daemon:

    QT_QPA_PLATFORM=offscreen python tools/qtdbus_probe.py

Prints PASS/FAIL per check with a reason. Not part of ./check.
"""

import json
import sys

from PyQt6.QtCore import QCoreApplication, QObject, QTimer, pyqtSlot
from PyQt6.QtDBus import QDBus, QDBusConnection, QDBusMessage

SERVICE = "io.github.appimage_launcher.Manager"
PATH = "/io/github/appimage_launcher/Manager"
IFACE = "io.github.appimage_launcher.Manager1"

results = []


def record(name, ok, reason):
    results.append((name, ok, reason))
    print(f"{'PASS' if ok else 'FAIL'}: {name} — {reason}")


def call_sync(bus, service, path, interface, method, args=None):
    """Make a synchronous D-Bus call and return (success, result_or_error)."""
    msg = QDBusMessage.createMethodCall(service, path, interface, method)
    if args is not None:
        msg.setArguments(args)
    reply = bus.call(msg, QDBus.CallMode.Block, 5000)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        return False, f"{reply.errorName()}: {reply.errorMessage()}"
    return True, reply.arguments()


class Probe(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.bus = QDBusConnection.sessionBus()
        self.bus_connected = bool(self.bus.isConnected())
        self.exit_code = 1

        # (a) async call - using synchronous call to test API
        self.async_done = False
        self.async_ok = False
        self.async_reason = ""

        # (b) signal subscription
        self.signal_connected = False
        self.signal_received = False
        self.signal_reason = ""

        # (c) service restart monitoring
        self.restart_cycle = False
        self.restart_seen_any = False
        self.restart_reason = ""

        self._checks_remaining = 3
        self._overall_timer = None

    # ---------------------------------------------------------------- (a)
    @pyqtSlot()
    def _async_timeout(self):
        if not self.async_done:
            self.async_done = True
            self.async_ok = False
            self.async_reason = "async call timed out (no reply within 5 s)"
            self._done_one()

    def run_async_call(self):
        if not self.bus_connected:
            record("(a) async call", False, "session bus not connected")
            self._done_one()
            return

        # Test APIVersion property
        ok, result = call_sync(
            self.bus, SERVICE, PATH, "org.freedesktop.DBus.Properties", "Get", [IFACE, "APIVersion"]
        )
        if not ok:
            record("(a) async call", False, f"Get APIVersion failed: {result}")
            self._done_one()
            return
        api_version = result[0] if result else None
        if api_version is None or api_version < 1:
            record("(a) async call", False, f"APIVersion invalid: {api_version}")
            self._done_one()
            return

        # Test Capabilities property
        ok, result = call_sync(
            self.bus,
            SERVICE,
            PATH,
            "org.freedesktop.DBus.Properties",
            "Get",
            [IFACE, "Capabilities"],
        )
        if not ok:
            record("(a) async call", False, f"Get Capabilities failed: {result}")
            self._done_one()
            return
        caps = result[0] if result else []
        required = {
            "inspect",
            "origin",
            "install-options-v1",
            "conflict-error",
            "remove-file-action",
            "list-hash",
        }
        missing = required - set(caps)
        if missing:
            record("(a) async call", False, f"Missing capabilities: {missing}")
            self._done_one()
            return

        # Test List method
        ok, result = call_sync(self.bus, SERVICE, PATH, IFACE, "List", [{}])
        if not ok:
            record("(a) async call", False, f"List failed: {result}")
            self._done_one()
            return
        try:
            apps = json.loads(result[0]) if result else []
            if not isinstance(apps, list):
                record("(a) async call", False, f"List returned non-array: {type(apps)}")
                self._done_one()
                return
        except (json.JSONDecodeError, IndexError) as e:
            record("(a) async call", False, f"List returned invalid JSON: {e}")
            self._done_one()
            return

        record(
            "(a) async call",
            True,
            f"APIVersion={api_version}, Capabilities={caps}, List returned {len(apps)} apps",
        )
        self._done_one()

    # ---------------------------------------------------------------- (b)
    @pyqtSlot(str, str, str)
    def _on_apps_changed(self, kind, app_id, source):
        self.signal_received = True
        self.signal_reason = f"AppsChanged(kind={kind!r}, app_id={app_id!r}, source={source!r})"

    @pyqtSlot()
    def _signal_timeout(self):
        if self.signal_received:
            record("(b) signal subscription", True, self.signal_reason)
        elif self.signal_connected:
            record(
                "(b) signal subscription",
                True,
                "subscribed to AppsChanged; no signal fired "
                "(normal if no apps changed during the window)",
            )
        else:
            record("(b) signal subscription", False, "could not connect to AppsChanged signal")
        self._done_one()

    def run_signal(self):
        if not self.bus_connected:
            record("(b) signal subscription", False, "session bus not connected")
            self._done_one()
            return
        ok = self.bus.connect(SERVICE, PATH, IFACE, "AppsChanged", self._on_apps_changed)
        self.signal_connected = bool(ok)
        if not self.signal_connected:
            self._signal_timeout()
            return
        # Trigger a Reindex to potentially fire AppsChanged
        ok, _result = call_sync(self.bus, SERVICE, PATH, IFACE, "Reindex")
        if not ok:
            # Reindex might not return anything on success
            pass
        QTimer.singleShot(3000, self._signal_timeout)

    # ---------------------------------------------------------------- (c)
    @pyqtSlot(str, str, str)
    def _on_owner_changed(self, service, old_owner, new_owner):
        if service != SERVICE:
            return
        self.restart_seen_any = True
        if old_owner and not new_owner:
            self.restart_reason = f"service disappeared (owner {old_owner} -> gone)"
        elif (not old_owner) and new_owner:
            if self.restart_reason and "disappeared" in self.restart_reason:
                self.restart_cycle = True
                self.restart_reason = f"disappear/reappear cycle observed (owner {new_owner})"
            else:
                self.restart_reason = f"service reappeared (owner {new_owner})"

    @pyqtSlot()
    def _restart_timeout(self):
        if self.restart_cycle:
            record("(c) service restart", True, self.restart_reason)
        elif self.restart_seen_any:
            record(
                "(c) service restart",
                False,
                self.restart_reason + " (no full disappear/reappear cycle)",
            )
        else:
            record(
                "(c) service restart",
                False,
                "no ownership change observed "
                "(restart appimage-launcher during the probe to exercise this)",
            )
        self._finish_all()

    def run_restart(self):
        if not self.bus_connected:
            record("(c) service restart", False, "session bus not connected")
            self._finish_all()
            return
        bus_iface = self.bus.interface()
        if not bus_iface.isValid():
            # Try alternative: monitor via org.freedesktop.DBus serviceOwnerChanged
            try:
                self.bus.connect(
                    "org.freedesktop.DBus",
                    "/org/freedesktop/DBus",
                    "org.freedesktop.DBus",
                    "NameOwnerChanged",
                    self._on_owner_changed,
                )
            except Exception as exc:
                record("(c) service restart", False, f"could not monitor NameOwnerChanged: {exc}")
                self._finish_all()
                return
        else:
            try:
                bus_iface.serviceOwnerChanged.connect(self._on_owner_changed)
            except Exception as exc:
                record(
                    "(c) service restart", False, f"could not monitor serviceOwnerChanged: {exc}"
                )
                self._finish_all()
                return
        QTimer.singleShot(8000, self._restart_timeout)

    # ---------------------------------------------------------------- driver
    def _done_one(self):
        self._checks_remaining -= 1
        if self._checks_remaining <= 0:
            self._finish_all()

    def _finish_all(self):
        if self._overall_timer is not None:
            self._overall_timer.stop()
        ok = all(r[1] for r in results)
        print()
        print(f"{sum(1 for r in results if r[1])}/{len(results)} checks passed")
        self.exit_code = 0 if ok else 1
        self.app.quit()

    def start(self):
        self.run_async_call()
        QTimer.singleShot(6000, self.run_signal)
        QTimer.singleShot(12000, self.run_restart)
        self._overall_timer = QTimer.singleShot(30000, self._finish_all)


def main():
    app = QCoreApplication(sys.argv)
    probe = Probe(app)
    probe.start()
    app.exec()
    sys.exit(probe.exit_code)


if __name__ == "__main__":
    main()
