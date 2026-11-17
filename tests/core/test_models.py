"""Tests for core/models.py (section 4.1)."""

from __future__ import annotations

from aurelis_software.core.models import App, InstalledApp, Source, UpdateInfo


def test_app_defaults_and_key():
    app = App(
        key="appimage:org.kde.kate",
        id="org.kde.kate",
        source=Source.APPIMAGE,
        name="Kate",
        summary="Text editor",
    )
    assert app.key == "appimage:org.kde.kate"
    assert app.source == Source.APPIMAGE
    assert app.version is None
    assert app.categories == ()
    assert app.store_categories == ()
    assert app.search_blob == ""
    assert app.raw == {}


def test_app_get_reads_raw():
    app = App(
        key="appimage:x",
        id="x",
        source=Source.APPIMAGE,
        name="X",
        summary="Y",
        raw={"sha256": "abc", "unknown_field": 1},
    )
    assert app.get("sha256") == "abc"
    assert app.get("unknown_field") == 1
    assert app.get("missing", "default") == "default"


def test_source_values():
    assert Source.APPIMAGE == "appimage"
    assert Source.FLATPAK == "flatpak"
    assert Source.PACMAN == "pacman"


def test_installed_app_defaults():
    inst = InstalledApp(id="kate", source=Source.APPIMAGE, name="Kate")
    assert inst.role == "primary"
    assert inst.self_managed is False
    assert inst.origin is None
    assert inst.locked is False
    assert inst.pending is None
    assert inst.previous == ()


def test_update_info_defaults():
    info = UpdateInfo(app_key="appimage:org.kde.kate")
    assert info.installed_version is None
    assert info.new_version is None
    assert info.size is None
    assert info.method == ""
