"""FakeManager1: in-process D-Bus fake for Manager1 (spec 13, P3.3).

Registered on a private session bus (``dbus-daemon --session --fork``).
Tests script the fake by setting ``fake.script`` before each call.

The fake implements every method and signal from ``manager1.xml`` with
the exact signatures.  The contract test (``tests/contract/``) parses
the XML and asserts this module implements all of them.

Error simulation
----------------
Set ``fake.script["<Method>"] = {"__error__": "ErrorSuffix", "msg": "..."}``
before calling.  The fake returns a sentinel dict; ``qt_dbus.py`` does NOT
convert sentinels — that is intentional: the sentinel tests the *caller*
(``backends/appimage.py``) handles the reply shape, while real D-Bus error
mapping is tested separately in ``test_qt_dbus.py``.

Signal emission
--------------
Call ``fake.emit_apps_changed(kind, app_id, source)`` from the test to
fire the ``AppsChanged`` signal on the bus.

Test helpers
-----------
Set ``fake.delay_response = {"MethodName": delay_ms}`` to delay a method's
response for testing race conditions.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QEventLoop, QObject, QTimer, pyqtClassInfo, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusAbstractAdaptor, QDBusConnection

from aurelis_software.backends.appimage import DBUS_INTERFACE, DBUS_PATH, DBUS_SERVICE

# Default scripted responses (method name -> return value).
_DEFAULTS: dict[str, Any] = {
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


@pyqtClassInfo("D-Bus Interface", DBUS_INTERFACE)
class _Manager1Adaptor(QDBusAbstractAdaptor):
    """PyQt6 D-Bus adaptor that exposes Manager1 on the private bus."""

    # Signal mirrors the XML: AppsChanged(kind: s, app_id: s, source: s)
    AppsChanged = pyqtSignal(str, str, str)

    def __init__(self, parent: FakeManager1) -> None:
        super().__init__(parent)
        self.setAutoRelaySignals(True)
        self._fake = parent

    def _respond(self, method: str) -> Any:
        return self._fake.script.get(method, _DEFAULTS.get(method))

    def clear_script(self):
        self._fake.script.clear()

    def _delayed_respond(self, method: str) -> Any:
        """Return response after delay if configured."""
        delay_ms = self._fake.delay_response.get(method, 0)
        if delay_ms > 0:
            loop = QEventLoop()
            QTimer.singleShot(delay_ms, loop.quit)
            loop.exec()
        return self._respond(method)

    # ------------------------------------------------------------------
    # Methods from manager1.xml
    # ------------------------------------------------------------------

    @pyqtSlot("QVariantMap", result="QVariantList")  # a{sv} -> a(sssv)
    def List(self, options: dict) -> list:  # noqa: N802
        self._fake.calls.append(("List", options))
        return self._delayed_respond("List")

    @pyqtSlot(str, result="QVariantMap")  # s -> a{sv}
    def Info(self, name: str) -> dict:  # noqa: N802
        self._fake.calls.append(("Info", name))
        return self._respond("Info")

    @pyqtSlot(str, result="QVariantMap")  # s -> a{sv}
    def Inspect(self, path: str) -> dict:  # noqa: N802
        self._fake.calls.append(("Inspect", path))
        return self._respond("Inspect")

    @pyqtSlot(str, "QVariantMap", result="QVariantMap")  # s, a{sv} -> a{sv}
    def Install(self, path: str, options: dict) -> dict:  # noqa: N802
        self._fake.calls.append(("Install", path, options))
        return self._delayed_respond("Install")

    @pyqtSlot(str, "QVariantMap", result=bool)  # s, a{sv} -> b
    def Remove(self, name: str, options: dict) -> bool:  # noqa: N802
        self._fake.calls.append(("Remove", name, options))
        return bool(self._respond("Remove"))

    @pyqtSlot(str, result=bool)  # s -> b
    def Revert(self, name: str) -> bool:  # noqa: N802
        self._fake.calls.append(("Revert", name))
        return bool(self._respond("Revert"))

    @pyqtSlot(str, str, result=bool)  # s, s -> b
    def SetPolicy(self, name: str, policy: str) -> bool:  # noqa: N802
        self._fake.calls.append(("SetPolicy", name, policy))
        return bool(self._respond("SetPolicy"))

    @pyqtSlot(str, str, result=bool)  # s, s -> b
    def SetOrigin(self, name: str, origin: str) -> bool:  # noqa: N802
        self._fake.calls.append(("SetOrigin", name, origin))
        return bool(self._respond("SetOrigin"))

    @pyqtSlot(result=bool)  # -> b
    def Reindex(self) -> bool:  # noqa: N802
        self._fake.calls.append(("Reindex",))
        return bool(self._respond("Reindex"))


class FakeManager1(QObject):
    """Root object registered on the private bus.

    Attributes
    ----------
    script:
        Dict mapping method name -> return value.  Unset methods use
        ``_DEFAULTS``.
    calls:
        List of ``(method, *args)`` tuples recorded in order.
    delay_response:
        Dict mapping method name -> delay in milliseconds. Used for testing
        race conditions where the daemon vanishes mid-call.
    """

    def __init__(self, bus: QDBusConnection) -> None:
        super().__init__()
        self.script: dict[str, Any] = {}
        self.calls: list[tuple] = []
        self.delay_response: dict[str, int] = {}
        self._adaptor = _Manager1Adaptor(self)
        self._bus = bus
        bus.registerService(DBUS_SERVICE)
        bus.registerObject(DBUS_PATH, self, QDBusConnection.RegisterOption.ExportAdaptors)

    def __setattr__(self, name, value):
        super().__setattr__(name, value)

    def emit_apps_changed(self, kind: str, app_id: str, source: str) -> None:
        """Emit ``AppsChanged`` on the bus (test helper)."""
        self._adaptor.AppsChanged.emit(kind, app_id, source)

    def reset(self) -> None:
        """Clear script and call log between tests."""
        self.script.clear()
        self.calls.clear()
