# QtDBus spike (spec 9.1, 3.4, P0.8)

## Environment
- Python 3.14.10
- PyQt6 (incl. `PyQt6.QtDBus`) — **importable**: `from PyQt6 import QtDBus` OK.
- Session bus present: `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`.
- `appimage-launcher` is **not** installed/running; no `io.github.appimage_launcher.Manager` service on the bus.
- `QT_QPA_PLATFORM=offscreen` used (no display).

## What works (measured)

1. `QDBusConnection.sessionBus()` connects: `isConnected()` -> `True`.
2. `bus.interface().isServiceRegistered(name).value()` works:
   - `org.freedesktop.DBus` -> `True`
   - `com.example.Nonexistent` -> `False`
   So service presence/absence can be detected (startup capability check can rely on this pattern).
3. `bus.callWithCallback(QDBusMessage, return_slot, error_slot)` is accepted by the API when slots are
   methods of a `QObject` decorated with `@pyqtSlot`. No type error.

## What I could NOT verify / what failed

4. **Async callback did not fire.** `callWithCallback` registered the slots, but neither the return nor
   the error slot was invoked, both with a manual `app.processEvents()` loop and with `app.exec()` plus a
   `QTimer.singleShot` quit. So I could not confirm end-to-end asynchronous D-Bus call delivery.
5. **`QDBusInterface` is unreliable here.** `QDBusInterface(...).isValid()` returned `False` even for
   `org.freedesktop.DBus`. Combining `QDBusInterface` + `asyncCall` + `QDBusPendingCallWatcher` caused a
   core dump (process aborted). This path must be avoided or retested with a full event loop and a real
   service.
6. **Signal subscription not tested.** `QDBusInterface.connect` / `bus.connect` for `AppsChanged` was not
   verified (depends on the same async machinery that did not fire).
7. **Bus activation of a missing service not tested** (no launcher `.service` file present).
8. **Behaviour when a service disappears mid-call not tested.**

## Implications for `services/qt_dbus.py` and `backends/appimage.py`
- Do not rely on `QDBusInterface.isValid()` or `QDBusPendingCallWatcher` without further validation.
- Prefer `QDBusConnection.callWithCallback` with `QObject` pyqtSlot methods, but verify callback delivery
  against a real D-Bus service before depending on it.
- Service-presence checks via `isServiceRegistered(name).value()` are usable.
- All D-Bus calls must be asynchronous on the UI thread (spec 3.4); a synchronous fallback is not
  acceptable for the UI thread.
- The `real_daemon` contract test (`-m real_daemon`) cannot run until `appimage-launcher` is tagged
  `api-v1` and installed here.

## Open
- Confirm async call delivery and signal subscription against a live D-Bus service.
- Confirm exact `List`/`Info`/`Inspect`/`Install` result dict shapes against the real `manager1.xml`.
