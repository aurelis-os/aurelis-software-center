#!/usr/bin/env python3
"""Environment report for Aurelis Software Center.

Standalone script — not part of ./check.  Run on any machine to produce
a plain-text snapshot that can be diffed between environments.

Usage:
    python tools/env_report.py
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(*cmd: str) -> str:
    try:
        r = subprocess.run(list(cmd), capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or r.stderr.strip() or "(no output)"
    except FileNotFoundError:
        return "not found"
    except Exception as exc:
        return f"error: {exc}"


def _version_of(cmd: str) -> str:
    return _run(cmd, "--version").splitlines()[0] if shutil.which(cmd) else "not installed"


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------
section("Python")
print(f"python: {sys.version}")
print(f"executable: {sys.executable}")

# ---------------------------------------------------------------------------
# PyQt6 / Qt
# ---------------------------------------------------------------------------
section("PyQt6 / Qt")
try:
    from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

    print(f"PyQt6: {PYQT_VERSION_STR}")
    print(f"Qt: {QT_VERSION_STR}")
except ImportError as exc:
    print(f"PyQt6: IMPORT ERROR — {exc}")

try:
    from PyQt6.QtDBus import QDBusConnection  # noqa: F401

    print("QtDBus: importable")
except ImportError as exc:
    print(f"QtDBus: IMPORT ERROR — {exc}")

# ---------------------------------------------------------------------------
# Session bus
# ---------------------------------------------------------------------------
section("D-Bus session bus")
addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "(not set)")
print(f"DBUS_SESSION_BUS_ADDRESS: {addr}")

try:
    from PyQt6.QtCore import QCoreApplication

    _app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    from PyQt6.QtDBus import QDBusConnection

    bus = QDBusConnection.sessionBus()
    connected = bus.isConnected()
    print(f"QDBusConnection.sessionBus().isConnected(): {connected}")

    if connected:
        SERVICE = "io.github.appimage_launcher.Manager"
        iface = bus.interface()
        if iface and iface.isValid():
            reply = iface.isServiceRegistered(SERVICE)
            registered = reply.value() if reply.isValid() else False
        else:
            registered = False
        print(f"io.github.appimage_launcher.Manager on bus: {registered}")
        if registered:
            owner_reply = iface.serviceOwner(SERVICE) if iface and iface.isValid() else None
            owner = owner_reply.value() if (owner_reply and owner_reply.isValid()) else "unknown"
            print(f"  owner: {owner}")
except Exception as exc:
    print(f"D-Bus check error: {exc}")

# ---------------------------------------------------------------------------
# External tools
# ---------------------------------------------------------------------------
section("External tools")
for tool in ("appimage", "flatpak", "pkg"):
    if shutil.which(tool):
        ver = _version_of(tool)
        print(f"{tool}: {ver}")
    else:
        print(f"{tool}: not installed")

# ---------------------------------------------------------------------------
# ~/Applications filesystem
# ---------------------------------------------------------------------------
section("~/Applications")
apps_dir = Path.home() / "Applications"
print(f"path: {apps_dir}")
print(f"exists: {apps_dir.exists()}")

if apps_dir.exists():
    try:
        stat = os.statvfs(apps_dir)
        fs_type = _run("stat", "-f", "-c", "%T", str(apps_dir))
        print(f"filesystem type (stat -f): {fs_type}")
        print(f"free bytes: {stat.f_bavail * stat.f_frsize}")
    except Exception as exc:
        print(f"statvfs error: {exc}")

    # xattr test
    try:
        with tempfile.NamedTemporaryFile(dir=apps_dir, delete=False) as tf:
            tmp = Path(tf.name)
        try:
            os.setxattr(str(tmp), "user.aurelis_test", b"1")
            os.removexattr(str(tmp), "user.aurelis_test")
            print("xattrs: supported")
        except OSError as exc:
            print(f"xattrs: NOT supported — {exc}")
        finally:
            tmp.unlink(missing_ok=True)
    except Exception as exc:
        print(f"xattr test error: {exc}")
else:
    print("(directory does not exist; skipping fs/xattr checks)")

# ---------------------------------------------------------------------------
# inotify limits
# ---------------------------------------------------------------------------
section("inotify limits")
for key in (
    "fs.inotify.max_user_watches",
    "fs.inotify.max_user_instances",
    "fs.inotify.max_queued_events",
):
    val = _run("sysctl", "-n", key)
    print(f"{key}: {val}")

# ---------------------------------------------------------------------------
# Desktop session
# ---------------------------------------------------------------------------
section("Desktop session")
for var in ("XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP"):
    print(f"{var}: {os.environ.get(var, '(not set)')}")

print()
