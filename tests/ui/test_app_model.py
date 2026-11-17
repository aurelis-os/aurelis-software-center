"""Tests for ui/app_model.py (P2.2): model roles, row count, lookup."""

from __future__ import annotations

from PyQt6.QtCore import Qt

from aurelis_software.core.models import App, Source
from aurelis_software.ui.app_model import AppModel


def _app(app_id: str, name: str, summary: str, version: str | None = "1.0") -> App:
    return App(
        key=f"appimage:{app_id}",
        id=app_id,
        source=Source.APPIMAGE,
        name=name,
        summary=summary,
        version=version,
        raw={},
    )


def test_model_roles(qtbot):
    model = AppModel()
    model.set_apps([_app("org.kde.kate", "Kate", "editor", "26.08.2-1")])
    assert model.rowCount() == 1
    index = model.index(0, 0)
    assert model.data(index, AppModel.NameRole) == "Kate"
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "Kate"
    assert model.data(index, AppModel.IdRole) == "org.kde.kate"
    assert model.data(index, AppModel.KeyRole) == "appimage:org.kde.kate"
    assert model.data(index, AppModel.SummaryRole) == "editor"
    assert model.data(index, AppModel.VersionRole) == "26.08.2-1"
    assert model.data(index, AppModel.SourceRole) == Source.APPIMAGE


def test_model_set_apps_replaces_contents(qtbot):
    model = AppModel()
    model.set_apps([_app("a", "A", "sum-a"), _app("b", "B", "sum-b")])
    assert model.rowCount() == 2
    model.set_apps([])
    assert model.rowCount() == 0


def test_model_app_at_and_find_by_id(qtbot):
    model = AppModel()
    model.set_apps(
        [_app("org.kde.kate", "Kate", "editor"), _app("org.gimp.gimp", "GIMP", "editor")]
    )
    assert model.app_at(0).id == "org.kde.kate"
    assert model.app_at(1).id == "org.gimp.gimp"
    assert model.app_at(5) is None
    assert model.find_by_id("org.gimp.gimp") == 1
    assert model.find_by_id("org.missing") is None
