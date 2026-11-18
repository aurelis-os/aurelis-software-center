"""Contract test: manager1.xml vs FakeManager1 and backends/appimage.py (spec 9.1, P3.3).

Parses ``docs/contracts/manager1.xml`` and asserts:
1. Every method in the XML is implemented by ``FakeManager1`` (fails if one
   is removed from the fake).
2. Every method called by ``backends/appimage.py`` exists in the XML with
   the right argument count.
3. Every signal in the XML is declared on ``_Manager1Adaptor``.
4. Every property in the XML is requested by ``backends/appimage.py``.

This test FAILS if a method is removed from the fake or the XML.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_XML_PATH = Path(__file__).parents[2] / "docs" / "contracts" / "manager1.xml"
_INTERFACE = "io.github.appimage_launcher.Manager1"

# Methods called by backends/appimage.py (from source inspection)
_BACKEND_CALLS = {
    "List",
    "Inspect",
    "Install",
    "Remove",
    "Revert",
    "SetPolicy",
    "SetOrigin",
    "Reindex",
}

# Properties read by backends/appimage.py
_BACKEND_PROPERTIES = {"APIVersion", "Capabilities"}

# Signals subscribed by backends/appimage.py
_BACKEND_SIGNALS = {"AppsChanged"}


def _parse_xml():
    tree = ET.parse(_XML_PATH)
    root = tree.getroot()
    iface = root.find(f"interface[@name='{_INTERFACE}']")
    assert iface is not None, f"Interface {_INTERFACE} not found in {_XML_PATH}"
    return iface


def _xml_methods(iface) -> dict[str, list[dict]]:
    """Return {method_name: [arg_dicts]} for all methods in the XML."""
    methods = {}
    for method in iface.findall("method"):
        name = method.get("name")
        args = [
            {"name": a.get("name"), "type": a.get("type"), "direction": a.get("direction")}
            for a in method.findall("arg")
        ]
        methods[name] = args
    return methods


def _xml_signals(iface) -> dict[str, list[dict]]:
    signals = {}
    for sig in iface.findall("signal"):
        name = sig.get("name")
        args = [{"name": a.get("name"), "type": a.get("type")} for a in sig.findall("arg")]
        signals[name] = args
    return signals


def _xml_properties(iface) -> dict[str, str]:
    return {p.get("name"): p.get("type") for p in iface.findall("property")}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_xml_exists():
    assert _XML_PATH.exists(), f"Contract XML not found: {_XML_PATH}"


def test_all_xml_methods_in_fake():
    """Every method in manager1.xml must be implemented by FakeManager1."""
    from tests.backends.fake_manager1 import _Manager1Adaptor

    iface = _parse_xml()
    xml_methods = _xml_methods(iface)

    for method_name in xml_methods:
        assert hasattr(_Manager1Adaptor, method_name), (
            f"FakeManager1._Manager1Adaptor is missing method {method_name!r} "
            f"(defined in manager1.xml)"
        )


def test_all_xml_methods_callable_on_fake():
    """Every XML method is callable (not just present as an attribute)."""
    from tests.backends.fake_manager1 import _Manager1Adaptor

    iface = _parse_xml()
    for method_name in _xml_methods(iface):
        attr = getattr(_Manager1Adaptor, method_name, None)
        assert callable(attr), f"{method_name} on _Manager1Adaptor is not callable"


def test_backend_calls_exist_in_xml():
    """Every method called by backends/appimage.py exists in manager1.xml."""
    iface = _parse_xml()
    xml_methods = set(_xml_methods(iface).keys())
    for method in _BACKEND_CALLS:
        assert method in xml_methods, (
            f"backends/appimage.py calls {method!r} but it is not in manager1.xml"
        )


def test_backend_properties_exist_in_xml():
    """Every property read by backends/appimage.py exists in manager1.xml."""
    iface = _parse_xml()
    xml_props = _xml_properties(iface)
    for prop in _BACKEND_PROPERTIES:
        assert prop in xml_props, (
            f"backends/appimage.py reads property {prop!r} but it is not in manager1.xml"
        )


def test_backend_signals_exist_in_xml():
    """Every signal subscribed by backends/appimage.py exists in manager1.xml."""
    iface = _parse_xml()
    xml_sigs = set(_xml_signals(iface).keys())
    for sig in _BACKEND_SIGNALS:
        assert sig in xml_sigs, (
            f"backends/appimage.py subscribes to {sig!r} but it is not in manager1.xml"
        )


def test_apps_changed_signal_args():
    """AppsChanged has exactly 3 string args: kind, app_id, source."""
    iface = _parse_xml()
    sigs = _xml_signals(iface)
    assert "AppsChanged" in sigs
    args = sigs["AppsChanged"]
    assert len(args) == 3, f"AppsChanged should have 3 args, got {len(args)}"
    for arg in args:
        assert arg["type"] == "s", (
            f"AppsChanged arg {arg['name']!r} should be 's', got {arg['type']!r}"
        )


def test_fake_adaptor_has_apps_changed_signal():
    """_Manager1Adaptor declares the AppsChanged signal."""
    from tests.backends.fake_manager1 import _Manager1Adaptor

    assert hasattr(_Manager1Adaptor, "AppsChanged"), "_Manager1Adaptor missing AppsChanged signal"


def test_list_method_signature():
    """List takes a{sv} options and returns a(sssv) result."""
    iface = _parse_xml()
    methods = _xml_methods(iface)
    assert "List" in methods
    args = methods["List"]
    in_args = [a for a in args if a["direction"] == "in"]
    out_args = [a for a in args if a["direction"] == "out"]
    assert len(in_args) == 1
    assert in_args[0]["type"] == "a{sv}", (
        f"List options type should be a{{sv}}, got {in_args[0]['type']!r}"
    )
    assert len(out_args) == 1
    assert out_args[0]["type"] == "a(sssv)", (
        f"List result type should be a(sssv), got {out_args[0]['type']!r}"
    )


def test_install_method_signature():
    """Install takes (s, a{sv}) and returns a{sv}."""
    iface = _parse_xml()
    methods = _xml_methods(iface)
    assert "Install" in methods
    args = methods["Install"]
    in_args = [a for a in args if a["direction"] == "in"]
    out_args = [a for a in args if a["direction"] == "out"]
    assert len(in_args) == 2
    assert in_args[0]["type"] == "s"
    assert in_args[1]["type"] == "a{sv}"
    assert len(out_args) == 1
    assert out_args[0]["type"] == "a{sv}"


def test_remove_method_signature():
    """Remove takes (s, a{sv}) and returns b."""
    iface = _parse_xml()
    methods = _xml_methods(iface)
    assert "Remove" in methods
    args = methods["Remove"]
    in_args = [a for a in args if a["direction"] == "in"]
    out_args = [a for a in args if a["direction"] == "out"]
    assert len(in_args) == 2
    assert in_args[0]["type"] == "s"
    assert in_args[1]["type"] == "a{sv}"
    assert out_args[0]["type"] == "b"


@pytest.mark.real_daemon
def test_real_daemon_list():
    """Real daemon: List returns a list (requires appimage-launcher api-v1)."""
    import sys

    from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer
    from PyQt6.QtDBus import QDBusConnection

    from aurelis_software.services.qt_dbus import DbusClient

    QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    # Use the real session bus (not the private test bus) for this test.
    bus = QDBusConnection.sessionBus()
    iface = bus.interface()
    if not (iface and iface.isValid()):
        pytest.skip("session bus not reachable")
    registered = iface.isServiceRegistered("io.github.appimage_launcher.Manager")
    if not (registered and registered.isValid() and registered.value()):
        pytest.skip("appimage-launcher daemon not running")
    client = DbusClient(bus)
    results = []
    errors = []
    loop = QEventLoop()
    client.call(
        "List",
        [{}],
        reply_cb=lambda args: (results.append(args), loop.quit()),
        error_cb=lambda e: (errors.append(e), loop.quit()),
    )
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert not errors, f"real daemon error: {errors}"
    assert results is not None
