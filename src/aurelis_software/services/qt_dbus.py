"""Async QtDBus wrapper for Manager1 (spec 3.4, 9.1, P3.2).

Design
------
- All calls are asynchronous via ``QDBusConnection.callWithCallback``.
  The UI thread is never blocked.
- A 30-second per-call timeout is enforced by a ``QTimer``.
- Signal subscriptions use ``QDBusConnection.connect``; a
  ``QDBusServiceWatcher`` re-subscribes automatically when the daemon
  restarts (service re-registers on the bus).
- D-Bus activation: calls are made regardless of current registration;
  QtDBus activates the service if a .service file exists.
- Errors (ServiceUnknown, NoReply, timeout) are delivered via the
  ``error_cb`` callback as ``DaemonUnavailable``.
- D-Bus error names ``io.github.appimage_launcher.Error.<X>`` are mapped
  to ``core/errors.py`` types by ``dbus_error_to_aurelis``.
- QDBusServiceWatcher with WatchForOwnerChange monitors both registration
  and unregistration. On unregistration: fail pending calls, mark down,
  emit signal. On registration: re-subscribe signals, emit "reconnected".

Usage
-----
    client = DbusClient(QDBusConnection.sessionBus())
    client.call("List", [options_dict],
                reply_cb=lambda args: ...,
                error_cb=lambda err: ...)
    client.subscribe_signal("AppsChanged", handler_slot)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import (
    QDBusConnection,
    QDBusError,
    QDBusMessage,
    QDBusServiceWatcher,
)

from aurelis_software.core.errors import (
    AurelisError,
    Busy,
    Cancelled,
    ConflictPending,
    DaemonUnavailable,
    Incompatible,
    Locked,
    NetworkError,
    PermissionDenied,
    ToolFailed,
)

log = logging.getLogger(__name__)

_CALL_TIMEOUT_MS = 30_000

# Map D-Bus error suffix -> AurelisError factory
# Errors not in this table fall back to DaemonUnavailable.
_DBUS_ERROR_MAP: dict[str, Callable[[str], AurelisError]] = {
    "NotFound": lambda m: ToolFailed(1, m, m),
    "Ambiguous": lambda m: ToolFailed(1, m, m),
    "NameCollision": lambda m: ToolFailed(1, m, m),
    "ConflictPending": lambda m: ConflictPending({}, m),
    "InvalidAppImage": lambda m: ToolFailed(1, m, m),
    "UnsupportedType": lambda m: ToolFailed(1, m, m),
    "InvalidArgument": lambda m: ToolFailed(1, m, m),
    "PolicyForbids": PermissionDenied,
    "Busy": Busy,
    "Io": NetworkError,
    "Aborted": Cancelled,
    "Incompatible": lambda m: Incompatible("unknown", m),
    "Locked": Locked,
    "ServiceUnknown": DaemonUnavailable,
    "NoReply": DaemonUnavailable,
}

_ERROR_PREFIX = "io.github.appimage_launcher.Error."


def dbus_error_to_aurelis(error_name: str, message: str) -> AurelisError:
    """Map a D-Bus error name to an ``AurelisError`` subclass instance.

    The ``error_name`` must be the full D-Bus error name, e.g.
    ``io.github.appimage_launcher.Error.NotFound``.
    """
    if error_name.startswith(_ERROR_PREFIX):
        suffix = error_name[len(_ERROR_PREFIX) :]
        factory = _DBUS_ERROR_MAP.get(suffix)
        if factory is not None:
            return factory(message)
    return DaemonUnavailable(f"{error_name}: {message}")


class _PendingCall(QObject):
    """Tracks one in-flight D-Bus call with a timeout."""

    def __init__(
        self,
        reply_cb: Callable[[list[Any]], None],
        error_cb: Callable[[AurelisError], None],
        parent: QObject,
    ) -> None:
        super().__init__(parent)
        self._reply_cb = reply_cb
        self._error_cb = error_cb
        self._done = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._timer.start(_CALL_TIMEOUT_MS)

    @pyqtSlot("QDBusMessage")
    def on_reply(self, msg: QDBusMessage) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self._reply_cb(msg.arguments())
        self.deleteLater()

    @pyqtSlot("QDBusError", "QDBusMessage")
    def on_error(self, err: QDBusError, _msg: QDBusMessage) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self._error_cb(dbus_error_to_aurelis(err.name(), err.message()))
        self.deleteLater()

    def _on_timeout(self) -> None:
        if self._done:
            return
        self._done = True
        self._error_cb(DaemonUnavailable("D-Bus call timed out after 30 s"))
        self.deleteLater()


class DbusClient(QObject):
    """Async D-Bus client for Manager1.

    Parameters
    ----------
    bus:
        The ``QDBusConnection`` to use (session bus in production;
        a private bus in tests).
    service, path, interface:
        D-Bus coordinates.  Defaults match the Manager1 constants.

    Signals
    -------
    service_unregistered(str)
        Emitted when the watched service is unregistered (daemon vanished).
    service_registered(str)
        Emitted when the watched service is registered (daemon started/restarted).
    """

    service_unregistered = pyqtSignal(str)
    service_registered = pyqtSignal(str)

    def __init__(
        self,
        bus: QDBusConnection,
        *,
        service: str = "io.github.appimage_launcher.Manager",
        path: str = "/io/github/appimage_launcher/Manager",
        interface: str = "io.github.appimage_launcher.Manager1",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._bus = bus
        self._service = service
        self._path = path
        self._interface = interface
        self._signal_handlers: list[tuple[str, Any]] = []
        self._pending_calls: list[_PendingCall] = []
        self._service_available = False

        # Watch for service owner changes (registration AND unregistration)
        self._watcher = QDBusServiceWatcher(
            service,
            bus,
            QDBusServiceWatcher.WatchModeFlag.WatchForOwnerChange,
            self,
        )
        self._watcher.serviceRegistered.connect(self._on_service_registered)
        self._watcher.serviceUnregistered.connect(self._on_service_unregistered)

        # Check initial service availability
        self._service_available = bus.interface().isServiceRegistered(service)

    def _track_pending_call(self, pending: _PendingCall) -> None:
        """Track a pending call for cleanup."""
        self._pending_calls.append(pending)

        # Remove from tracking when done
        def _cleanup() -> None:
            if pending in self._pending_calls:
                self._pending_calls.remove(pending)

        pending.destroyed.connect(_cleanup)

    def _fail_pending_calls(self, reason: str) -> None:
        """Fail all pending calls with DaemonUnavailable."""
        for pending in list(self._pending_calls):
            if not pending._done:
                pending._done = True
                pending._timer.stop()
                pending._error_cb(DaemonUnavailable(reason))
                pending.deleteLater()
        self._pending_calls.clear()

    def cleanup(self) -> None:
        """Cancel all pending calls and stop watcher."""
        # Stop watcher
        if hasattr(self, "_watcher") and self._watcher:
            self._watcher.deleteLater()

        # Cancel all pending calls
        self._fail_pending_calls("DbusClient cleaned up")

        # Disconnect signals
        if hasattr(self, "_signal_handlers"):
            self._signal_handlers.clear()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def call(
        self,
        method: str,
        args: list[Any],
        *,
        reply_cb: Callable[[list[Any]], None],
        error_cb: Callable[[AurelisError], None],
    ) -> None:
        """Make an async D-Bus call.  Never blocks.

        QtDBus handles D-Bus activation automatically. If the service is
        activatable, the call will start it. Errors like ServiceUnknown,
        NoReply, or timeout are mapped to DaemonUnavailable.
        """
        msg = QDBusMessage.createMethodCall(self._service, self._path, self._interface, method)
        msg.setArguments(args)
        pending = _PendingCall(reply_cb, error_cb, self)
        self._track_pending_call(pending)
        ok = self._bus.callWithCallback(msg, pending.on_reply, pending.on_error)
        if not ok:
            pending.deleteLater()
            error_cb(DaemonUnavailable(f"callWithCallback failed for {method}"))

    def get_property(
        self,
        prop: str,
        *,
        reply_cb: Callable[[Any], None],
        error_cb: Callable[[AurelisError], None],
    ) -> None:
        """Read a D-Bus property asynchronously."""

        def _unwrap(args: list[Any]) -> None:
            reply_cb(args[0] if args else None)

        self.call(
            "Get",
            [self._interface, prop],
            reply_cb=_unwrap,
            error_cb=error_cb,
        )

    def subscribe_signal(self, signal_name: str, slot: Any) -> bool:
        """Subscribe to a D-Bus signal.  Returns True on success.

        The subscription is remembered so it can be re-established after
        a daemon restart.
        """
        ok = bool(
            self._bus.connect(
                self._service,
                self._path,
                self._interface,
                signal_name,
                slot,
            )
        )
        if ok:
            self._signal_handlers.append((signal_name, slot))
            log.debug("subscribed to %s.%s", self._interface, signal_name)
        else:
            log.warning("failed to subscribe to %s.%s", self._interface, signal_name)
        return ok

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @pyqtSlot(str)
    def _on_service_unregistered(self, service: str) -> None:
        log.warning("service %s unregistered; failing pending calls", service)
        self._service_available = False
        self._fail_pending_calls(f"Service {service} unregistered")
        self.service_unregistered.emit(service)

    @pyqtSlot(str)
    def _on_service_registered(self, service: str) -> None:
        log.info("service %s registered; re-subscribing signals", service)
        self._service_available = True
        for signal_name, slot in self._signal_handlers:
            self._bus.connect(
                self._service,
                self._path,
                self._interface,
                signal_name,
                slot,
            )
        self.service_registered.emit(service)
