"""AppImage backend — D-Bus client for Manager1 (spec 9.1, P3.3).

All operations are asynchronous; results are delivered via Operation
events.  The backend never blocks the UI thread.

D-Bus constants are defined once here (spec 15.2 / decision log).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from aurelis_software.backends.base import Backend, Capabilities, Operation
from aurelis_software.core.errors import (
    AurelisError,
    ConflictPendingError,
    DaemonUnavailableError,
    DiskFullError,
    InvalidAppImageError,
    NetworkErrorError,
    NotFoundError,
    PermissionDeniedError,
)
from aurelis_software.core.models import App, InstalledApp, Source, UpdateInfo
from aurelis_software.services.qt_dbus import DbusClient

log = logging.getLogger(__name__)

# D-Bus coordinates — one constant each, never repeated (spec 15.2).
DBUS_SERVICE = "io.github.appimage_launcher.Manager"
DBUS_PATH = "/io/github/appimage_launcher/Manager"
DBUS_INTERFACE = "io.github.appimage_launcher.Manager1"

# Required capabilities (spec 8.1).
REQUIRED_CAPABILITIES = frozenset(
    {
        "inspect",
        "origin",
        "install-options-v1",
        "conflict-error",
        "remove-file-action",
        "list-hash",
    }
)


class AppsChanged(QObject):
    """Re-emits the Manager1 ``AppsChanged`` signal as a Qt signal."""

    signal = pyqtSignal(str, str, str)  # kind, app_id, source


class AppImageBackend(Backend):
    """AppImage backend over Manager1 D-Bus API.

    Parameters
    ----------
    client:
        Injected ``DbusClient`` (production: session bus; tests: private bus).
    """

    source = Source.APPIMAGE

    def __init__(self, client: DbusClient) -> None:
        self._client = client
        self._api_version: int | None = None
        self._caps: dict[str, bool] = {}
        self.available = False
        self._apps_changed = AppsChanged()

    # ------------------------------------------------------------------
    # Startup check
    # ------------------------------------------------------------------

    def check_availability(
        self,
        *,
        ok_cb: Callable[[int, dict], None],
        fail_cb: Callable[[AurelisError], None],
    ) -> None:
        """Async startup check: read APIVersion then Capabilities."""

        def _got_version(val: Any) -> None:
            try:
                ver = int(val) if val is not None else 0
            except (TypeError, ValueError):
                ver = 0
            self._api_version = ver
            if ver < 1:
                from aurelis_software.core.errors import ApiTooOld

                fail_cb(ApiTooOld())
                return
            self._client.get_property(
                "Capabilities",
                reply_cb=_got_caps,
                error_cb=fail_cb,
            )

        def _got_caps(val: Any) -> None:
            caps: dict[str, bool] = val if isinstance(val, dict) else {}
            self._caps = caps
            missing = REQUIRED_CAPABILITIES - set(caps.keys())
            if missing:
                from aurelis_software.core.errors import ApiTooOld

                fail_cb(ApiTooOld(f"Missing capabilities: {missing}"))
                return
            self.available = True
            ok_cb(self._api_version, caps)

        self._client.get_property(
            "APIVersion",
            reply_cb=_got_version,
            error_cb=fail_cb,
        )

    # ------------------------------------------------------------------
    # Backend ABC
    # ------------------------------------------------------------------

    def capabilities(self) -> Capabilities:
        return Capabilities(
            install=self.available,
            remove=self.available,
            update=self.available,
            revert=self.available,
            set_policy=self.available,
            set_origin=self.available,
            list_hash=bool(self._caps.get("list-hash")),
        )

    def list_installed(self) -> list[InstalledApp]:
        msg = "use list_installed_async"
        raise NotImplementedError(msg)

    def list_updates(self) -> list[UpdateInfo]:
        return []

    def install(self, app: App, **opts) -> Operation:
        msg = "use install_async"
        raise NotImplementedError(msg)

    def remove(self, installed: InstalledApp) -> Operation:
        msg = "use remove_async"
        raise NotImplementedError(msg)

    def update(self, app: App, installed: InstalledApp) -> Operation:
        msg = "use update_async"
        raise NotImplementedError(msg)

    def open(self, installed: InstalledApp) -> None:
        msg = "use QProcess.startDetached('appimage', ['run', name])"
        raise NotImplementedError(msg)

    # ------------------------------------------------------------------
    # Async operations
    # ------------------------------------------------------------------

    def list_installed_async(
        self,
        options: dict,
        *,
        reply_cb: Callable[[list], None],
        error_cb: Callable[[AurelisError], None],
    ) -> None:
        """Call ``List(options)`` asynchronously."""
        self._client.call(
            "List",
            [options],
            reply_cb=lambda args: reply_cb(args[0] if args else []),
            error_cb=error_cb,
        )

    def inspect_async(
        self,
        path: str,
        *,
        reply_cb: Callable[[dict], None],
        error_cb: Callable[[AurelisError], None],
    ) -> None:
        """Call ``Inspect(path)`` asynchronously."""
        self._client.call(
            "Inspect",
            [path],
            reply_cb=lambda args: reply_cb(args[0] if args else {}),
            error_cb=error_cb,
        )

    def install_async(
        self,
        path: str,
        options: dict,
        *,
        reply_cb: Callable[[dict], None],
        error_cb: Callable[[AurelisError], None],
    ) -> None:
        """Call ``Install(path, options)`` asynchronously."""
        self._client.call(
            "Install",
            [path, options],
            reply_cb=lambda args: self._handle_install_reply(
                args[0] if args else {}, reply_cb, error_cb
            ),
            error_cb=error_cb,
        )

    def _handle_install_reply(
        self,
        reply: dict,
        reply_cb: Callable[[dict], None],
        error_cb: Callable[[AurelisError], None],
    ) -> None:
        """Check for error sentinel in Install reply and dispatch accordingly."""
        if not isinstance(reply, dict):
            reply_cb(reply)
            return

        error_suffix = reply.get("__error__")
        if error_suffix:
            msg = reply.get("msg", "Unknown error")
            details = reply.get("details", "")
            error_map = {
                "NoSpace": DiskFullError,
                "NotFound": NotFoundError,
                "InvalidAppImage": InvalidAppImageError,
                "PermissionDenied": PermissionDeniedError,
                "DaemonUnavailable": DaemonUnavailableError,
                "NetworkError": NetworkErrorError,
            }
            if error_suffix == "ConflictPending":
                # ConflictPendingError expects a payload dict
                import json

                try:
                    payload = json.loads(details) if details else {"old": {}}
                except json.JSONDecodeError:
                    payload = {"old": {}}
                error_cb(ConflictPendingError(payload, msg))
            else:
                error_cls = error_map.get(error_suffix, AurelisError)
                error_cb(error_cls(msg))
            return

        reply_cb(reply)

    def remove_async(
        self,
        name: str,
        options: dict,
        *,
        reply_cb: Callable[[bool], None],
        error_cb: Callable[[AurelisError], None],
    ) -> None:
        """Call ``Remove(name, options)`` asynchronously."""
        self._client.call(
            "Remove",
            [name, options],
            reply_cb=lambda args: reply_cb(bool(args[0]) if args else False),
            error_cb=error_cb,
        )

    def revert_async(
        self,
        name: str,
        *,
        reply_cb: Callable[[bool], None],
        error_cb: Callable[[AurelisError], None],
    ) -> None:
        """Call ``Revert(name)`` asynchronously."""
        self._client.call(
            "Revert",
            [name],
            reply_cb=lambda args: reply_cb(bool(args[0]) if args else False),
            error_cb=error_cb,
        )

    def set_origin_async(
        self,
        name: str,
        origin: dict | None,
        *,
        reply_cb: Callable[[bool], None],
        error_cb: Callable[[AurelisError], None],
    ) -> None:
        """Call ``SetOrigin(name, json)`` asynchronously."""
        origin_json = json.dumps(origin) if origin else ""
        self._client.call(
            "SetOrigin",
            [name, origin_json],
            reply_cb=lambda args: reply_cb(bool(args[0]) if args else False),
            error_cb=error_cb,
        )

    def set_policy_async(
        self,
        name: str,
        policy: str,
        *,
        reply_cb: Callable[[bool], None],
        error_cb: Callable[[AurelisError], None],
    ) -> None:
        """Call ``SetPolicy(name, policy)`` asynchronously."""
        self._client.call(
            "SetPolicy",
            [name, policy],
            reply_cb=lambda args: reply_cb(bool(args[0]) if args else False),
            error_cb=error_cb,
        )

    def reindex_async(
        self,
        *,
        reply_cb: Callable[[bool], None],
        error_cb: Callable[[AurelisError], None],
    ) -> None:
        """Call ``Reindex()`` asynchronously."""
        self._client.call(
            "Reindex",
            [],
            reply_cb=lambda args: reply_cb(bool(args[0]) if args else False),
            error_cb=error_cb,
        )

    def subscribe_apps_changed(self, slot: Any) -> bool:
        """Subscribe to the ``AppsChanged`` signal."""
        return self._client.subscribe_signal("AppsChanged", slot)
