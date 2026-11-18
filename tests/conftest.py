"""Shared fixtures for D-Bus tests (services/ and backends/).

Private session bus
-------------------
We start ``dbus-daemon --session --print-address --fork`` once per test
session and set ``DBUS_SESSION_BUS_ADDRESS`` so that
``QDBusConnection.sessionBus()`` connects to it instead of the
developer's real bus.  This satisfies spec rule 8 (tests never touch the
developer's session bus).

The ``dbus_bus`` fixture returns a connected ``QDBusConnection`` on the
private bus.  The ``fake_manager`` fixture registers ``FakeManager1`` on
that bus and tears it down after each test.
"""

from __future__ import annotations

import os
import subprocess

import pytest
from PyQt6.QtDBus import QDBusConnection

# ---------------------------------------------------------------------------
# Private session bus — session scope
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def private_bus_address():
    """Start a private dbus-daemon and return its address."""
    result = subprocess.run(
        ["dbus-daemon", "--session", "--print-address", "--fork"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"dbus-daemon failed: {result.stderr}"
    address = result.stdout.strip()
    assert address, "dbus-daemon printed no address"
    old = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = address
    yield address
    # Restore (the forked daemon will be reaped by the OS)
    if old is None:
        os.environ.pop("DBUS_SESSION_BUS_ADDRESS", None)
    else:
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = old


@pytest.fixture(scope="session")
def qapp_session(private_bus_address):
    """One QApplication for the whole test session (D-Bus + UI tests)."""
    import sys

    # Must be QApplication (not QCoreApplication) so that UI tests that run
    # after D-Bus tests can create QPixmap / QPainter without Qt aborting.
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


@pytest.fixture(scope="session")
def dbus_bus(qapp_session, private_bus_address):
    """A QDBusConnection connected to the private session bus."""
    bus = QDBusConnection.connectToBus(private_bus_address, "aurelis-test-bus")
    assert bus.isConnected(), "Could not connect to private session bus"
    return bus


# ---------------------------------------------------------------------------
# FakeManager1 — function scope (reset between tests)
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_manager(dbus_bus):
    """Register FakeManager1 on the private bus; unregister and reset after each test."""
    from aurelis_software.backends.appimage import DBUS_PATH, DBUS_SERVICE
    from tests.backends.fake_manager1 import FakeManager1

    fake = FakeManager1(dbus_bus)
    yield fake
    dbus_bus.unregisterObject(DBUS_PATH)
    dbus_bus.unregisterService(DBUS_SERVICE)
    fake.reset()


@pytest.fixture()
def dbus_client(dbus_bus):
    """A DbusClient connected to the private bus."""
    from aurelis_software.services.qt_dbus import DbusClient

    return DbusClient(dbus_bus)
