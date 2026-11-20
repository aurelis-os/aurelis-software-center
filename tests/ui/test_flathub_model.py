"""Tests for FlathubModel (ui/app_model.py) — R9.1, R9.2.

Uses a fake FlathubIndex so the tests have no filesystem dependency and
run without a real AppStream database.  The Qt ``QAbstractListModel``
signals are exercised via pytest-qt's qtbot/qtmodeltester where needed.
"""

from __future__ import annotations

from PyQt6.QtCore import QModelIndex, Qt

from aurelis_software.core.models import Source
from aurelis_software.ui.app_model import _PAGE_SIZE, FlathubModel

# ---------------------------------------------------------------------------
# Fake FlathubIndex
# ---------------------------------------------------------------------------


def _make_row(i: int, categories: list[str] | None = None) -> dict:
    return {
        "id": f"org.app.App{i}",
        "name": f"App {i}",
        "summary": f"Summary of app {i}",
        "version": f"1.{i}.0",
        "icon_name": "",
        "categories": categories or ["Utility"],
        "keywords": [],
        "raw": {"extra": i},
    }


class FakeIndex:
    """Minimal FlathubIndex stand-in that serves a fixed list of rows."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def search(self, query: str, limit: int = _PAGE_SIZE, offset: int = 0) -> list[dict]:
        # Simple substring match on name so tests can filter by keyword.
        matched = [r for r in self._rows if query.lower() in r["name"].lower()] if query else []
        return matched[offset : offset + limit]


# ---------------------------------------------------------------------------
# Constructor & empty state
# ---------------------------------------------------------------------------


def test_flathub_model_empty_by_default(qtbot):
    model = FlathubModel()
    assert model.rowCount() == 0
    assert model.canFetchMore(QModelIndex()) is False


def test_flathub_model_no_index_set_query_noop(qtbot):
    model = FlathubModel(index=None)
    model.set_query("editor")
    assert model.rowCount() == 0
    assert model.canFetchMore(QModelIndex()) is False


# ---------------------------------------------------------------------------
# set_query — first page loaded immediately
# ---------------------------------------------------------------------------


def test_set_query_loads_first_page(qtbot):
    rows = [_make_row(i) for i in range(10)]
    index = FakeIndex(rows)
    model = FlathubModel(index)
    model.set_query("App")  # matches all 10
    assert model.rowCount() == 10


def test_set_query_no_match_empty(qtbot):
    rows = [_make_row(i) for i in range(5)]
    index = FakeIndex(rows)
    model = FlathubModel(index)
    model.set_query("ZZZnonexistent")
    assert model.rowCount() == 0


def test_set_query_resets_previous_results(qtbot):
    rows = [_make_row(i) for i in range(5)]
    index = FakeIndex(rows)
    model = FlathubModel(index)
    model.set_query("App")
    assert model.rowCount() == 5
    model.set_query("ZZZnonexistent")
    assert model.rowCount() == 0


# ---------------------------------------------------------------------------
# Pagination via canFetchMore / fetchMore
# ---------------------------------------------------------------------------


def test_can_fetch_more_true_when_full_page(qtbot):
    # Exactly PAGE_SIZE rows so the first fetch should leave has_more=True.
    rows = [_make_row(i) for i in range(_PAGE_SIZE)]
    index = FakeIndex(rows)
    model = FlathubModel(index)
    model.set_query("App")
    assert model.rowCount() == _PAGE_SIZE
    assert model.canFetchMore(QModelIndex()) is True


def test_can_fetch_more_false_when_partial_page(qtbot):
    rows = [_make_row(i) for i in range(10)]  # less than PAGE_SIZE
    index = FakeIndex(rows)
    model = FlathubModel(index)
    model.set_query("App")
    assert model.rowCount() == 10
    assert model.canFetchMore(QModelIndex()) is False


def test_fetch_more_appends_next_page(qtbot):
    # Build PAGE_SIZE + 5 rows so the first page is full and there are 5 more.
    rows = [_make_row(i) for i in range(_PAGE_SIZE + 5)]
    index = FakeIndex(rows)
    model = FlathubModel(index)
    model.set_query("App")
    assert model.rowCount() == _PAGE_SIZE
    assert model.canFetchMore(QModelIndex()) is True

    model.fetchMore(QModelIndex())

    assert model.rowCount() == _PAGE_SIZE + 5
    assert model.canFetchMore(QModelIndex()) is False


def test_fetch_more_no_op_when_no_more(qtbot):
    rows = [_make_row(i) for i in range(3)]
    index = FakeIndex(rows)
    model = FlathubModel(index)
    model.set_query("App")
    assert not model.canFetchMore(QModelIndex())
    model.fetchMore(QModelIndex())  # must not raise or corrupt state
    assert model.rowCount() == 3


def test_fetch_more_with_invalid_parent_is_noop(qtbot):
    rows = [_make_row(i) for i in range(_PAGE_SIZE + 1)]
    index = FakeIndex(rows)
    model = FlathubModel(index)
    model.set_query("App")
    before = model.rowCount()
    invalid = model.index(0, 0)  # a valid child index → invalid parent
    model.fetchMore(invalid)
    assert model.rowCount() == before


# ---------------------------------------------------------------------------
# Role data matches AppModel role constants
# ---------------------------------------------------------------------------


def test_roles_match_app_model_constants(qtbot):
    from aurelis_software.ui.app_model import AppModel

    for attr in (
        "IdRole",
        "KeyRole",
        "NameRole",
        "SummaryRole",
        "VersionRole",
        "SourceRole",
        "StoreCategoriesRole",
        "RawRole",
    ):
        assert getattr(FlathubModel, attr) == getattr(AppModel, attr), (
            f"FlathubModel.{attr} != AppModel.{attr}"
        )


def test_data_returns_correct_values(qtbot):
    row = _make_row(42, categories=["Audio", "Video"])
    index = FakeIndex([row])
    model = FlathubModel(index)
    model.set_query("App")
    assert model.rowCount() == 1

    mi = model.index(0, 0)
    assert model.data(mi, FlathubModel.IdRole) == "org.app.App42"
    assert model.data(mi, FlathubModel.KeyRole) == "flatpak:org.app.App42"
    assert model.data(mi, FlathubModel.NameRole) == "App 42"
    assert model.data(mi, FlathubModel.SummaryRole) == "Summary of app 42"
    assert model.data(mi, FlathubModel.VersionRole) == "1.42.0"
    assert model.data(mi, FlathubModel.SourceRole) == Source.FLATPAK
    assert model.data(mi, FlathubModel.StoreCategoriesRole) == ("Audio", "Video")
    # DisplayRole delegates to NameRole
    assert model.data(mi, Qt.ItemDataRole.DisplayRole) == "App 42"


def test_data_invalid_index_returns_none(qtbot):
    model = FlathubModel(FakeIndex([_make_row(0)]))
    model.set_query("App")
    invalid = QModelIndex()
    assert model.data(invalid, FlathubModel.NameRole) is None


def test_data_out_of_range_returns_none(qtbot):
    model = FlathubModel(FakeIndex([_make_row(0)]))
    model.set_query("App")
    mi = model.index(999, 0)
    assert model.data(mi, FlathubModel.NameRole) is None


# ---------------------------------------------------------------------------
# Source is always FLATPAK
# ---------------------------------------------------------------------------


def test_source_is_always_flatpak(qtbot):
    rows = [_make_row(i) for i in range(3)]
    model = FlathubModel(FakeIndex(rows))
    model.set_query("App")
    for i in range(model.rowCount()):
        mi = model.index(i, 0)
        assert model.data(mi, FlathubModel.SourceRole) == Source.FLATPAK


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def test_row_at_valid(qtbot):
    rows = [_make_row(7)]
    model = FlathubModel(FakeIndex(rows))
    model.set_query("App")
    assert model.row_at(0) is not None
    assert model.row_at(0)["id"] == "org.app.App7"


def test_row_at_out_of_range(qtbot):
    model = FlathubModel(FakeIndex([_make_row(0)]))
    model.set_query("App")
    assert model.row_at(999) is None
    assert model.row_at(-1) is None


def test_find_by_id_found(qtbot):
    rows = [_make_row(i) for i in range(5)]
    model = FlathubModel(FakeIndex(rows))
    model.set_query("App")
    assert model.find_by_id("org.app.App3") == 3


def test_find_by_id_not_found(qtbot):
    model = FlathubModel(FakeIndex([_make_row(0)]))
    model.set_query("App")
    assert model.find_by_id("org.missing.App") is None


# ---------------------------------------------------------------------------
# set_index swaps the backing store
# ---------------------------------------------------------------------------


def test_set_index_replaces_backing_index(qtbot):
    rows_a = [_make_row(i) for i in range(3)]
    rows_b = [_make_row(i) for i in range(10)]
    model = FlathubModel(FakeIndex(rows_a))
    model.set_query("App")
    assert model.rowCount() == 3

    model.set_index(FakeIndex(rows_b))
    # set_index re-runs the current query
    assert model.rowCount() == 10


# ---------------------------------------------------------------------------
# roleNames mirrors AppModel
# ---------------------------------------------------------------------------


def test_role_names(qtbot):
    model = FlathubModel()
    names = model.roleNames()
    assert names[FlathubModel.NameRole] == b"name"
    assert names[FlathubModel.IdRole] == b"id"
    assert names[FlathubModel.SourceRole] == b"source"
