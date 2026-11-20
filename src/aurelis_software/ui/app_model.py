"""AppModel: a QAbstractListModel of catalog App entries (section 10.2).

Also contains FlathubModel, a paginated QAbstractListModel backed by
FlathubIndex FTS5 search (R9.1, R9.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    Qt,
)

from aurelis_software.core.models import App, Source

if TYPE_CHECKING:
    from aurelis_software.services.flathub_index import FlathubIndex
    from aurelis_software.services.pacman_index import PacmanIndex

_PAGE_SIZE = 48


class AppModel(QAbstractListModel):
    """A list of ``App`` objects exposed to views through roles.

    The model owns the current (filtered / sorted) set of apps. Call
    ``set_apps`` to replace the contents, e.g. after a search.
    """

    IdRole = Qt.ItemDataRole.UserRole + 1
    KeyRole = Qt.ItemDataRole.UserRole + 2
    NameRole = Qt.ItemDataRole.UserRole + 3
    SummaryRole = Qt.ItemDataRole.UserRole + 4
    VersionRole = Qt.ItemDataRole.UserRole + 5
    SourceRole = Qt.ItemDataRole.UserRole + 6
    StoreCategoriesRole = Qt.ItemDataRole.UserRole + 7
    RawRole = Qt.ItemDataRole.UserRole + 8

    def __init__(self, apps: list[App] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._apps: list[App] = list(apps or [])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._apps)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._apps):
            return None
        app = self._apps[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            role = self.NameRole
        return {
            self.NameRole: app.name,
            self.IdRole: app.id,
            self.KeyRole: app.key,
            self.SummaryRole: app.summary,
            self.VersionRole: app.version,
            self.SourceRole: app.source,
            self.StoreCategoriesRole: app.store_categories,
            self.RawRole: app.raw,
        }.get(role)

    def roleNames(self):  # noqa: N802
        return {
            self.IdRole: b"id",
            self.KeyRole: b"key",
            self.NameRole: b"name",
            self.SummaryRole: b"summary",
            self.VersionRole: b"version",
            self.SourceRole: b"source",
            self.StoreCategoriesRole: b"store_categories",
            self.RawRole: b"raw",
        }

    def set_apps(self, apps: list[App]) -> None:
        """Replace the model contents with ``apps``."""
        self.beginResetModel()
        self._apps = list(apps)
        self.endResetModel()

    def app_at(self, row: int) -> App | None:
        if 0 <= row < len(self._apps):
            return self._apps[row]
        return None

    def find_by_id(self, app_id: str) -> int | None:
        for row, app in enumerate(self._apps):
            if app.id == app_id:
                return row
        return None

    def apps(self) -> list[App]:
        return list(self._apps)


class FlathubModel(QAbstractListModel):
    """Paginated list model backed by :class:`~aurelis_software.services.flathub_index.FlathubIndex`.

    Implements Qt's ``canFetchMore`` / ``fetchMore`` protocol so that only
    one page of results (``_PAGE_SIZE`` rows) is in memory at a time.  The
    view calls ``fetchMore`` automatically as the user scrolls.

    Roles are identical to :class:`AppModel` so :class:`~aurelis_software.ui.app_card_delegate.AppCardDelegate`
    renders Flatpak cards without any changes (R9.1).

    Usage::

        model = FlathubModel(index)
        model.set_query("video editor")   # reset + first page
        view.setModel(model)              # view calls fetchMore as needed
    """

    # Same role constants as AppModel so AppCardDelegate needs no changes.
    IdRole = Qt.ItemDataRole.UserRole + 1
    KeyRole = Qt.ItemDataRole.UserRole + 2
    NameRole = Qt.ItemDataRole.UserRole + 3
    SummaryRole = Qt.ItemDataRole.UserRole + 4
    VersionRole = Qt.ItemDataRole.UserRole + 5
    SourceRole = Qt.ItemDataRole.UserRole + 6
    StoreCategoriesRole = Qt.ItemDataRole.UserRole + 7
    RawRole = Qt.ItemDataRole.UserRole + 8

    def __init__(self, index: FlathubIndex | None = None, parent=None) -> None:
        super().__init__(parent)
        self._index: FlathubIndex | None = index
        self._rows: list[dict] = []
        self._query: str = ""
        # True while we know more pages exist (last fetch returned a full page).
        self._has_more: bool = False

    # ------------------------------------------------------------------ Qt interface

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:  # noqa: N802
        return False if parent.isValid() else self._has_more

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:  # noqa: N802
        if parent.isValid() or not self._has_more or self._index is None:
            return
        offset = len(self._rows)
        new_rows = self._index.search(self._query, limit=_PAGE_SIZE, offset=offset)
        if not new_rows:
            self._has_more = False
            return
        first = offset
        last = offset + len(new_rows) - 1
        self.beginInsertRows(QModelIndex(), first, last)
        self._rows.extend(new_rows)
        self.endInsertRows()
        # If the returned page was full, more results may exist.
        self._has_more = len(new_rows) == _PAGE_SIZE

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        row = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            role = self.NameRole
        return {
            self.IdRole: row.get("id", ""),
            self.KeyRole: f"flatpak:{row.get('id', '')}",
            self.NameRole: row.get("name", ""),
            self.SummaryRole: row.get("summary", ""),
            self.VersionRole: row.get("version"),
            self.SourceRole: Source.FLATPAK,
            self.StoreCategoriesRole: tuple(row.get("categories", [])),
            self.RawRole: row.get("raw", row),
        }.get(role)

    def roleNames(self):  # noqa: N802
        return {
            self.IdRole: b"id",
            self.KeyRole: b"key",
            self.NameRole: b"name",
            self.SummaryRole: b"summary",
            self.VersionRole: b"version",
            self.SourceRole: b"source",
            self.StoreCategoriesRole: b"store_categories",
            self.RawRole: b"raw",
        }

    # ------------------------------------------------------------------ convenience

    def set_index(self, index: FlathubIndex | None) -> None:
        """Replace the backing index and clear the current results."""
        self._index = index
        self.set_query(self._query)

    def set_query(self, query: str) -> None:
        """Reset the model and load the first page for *query*.

        This is the primary control point wired to the search bar — it plays
        the same role as :meth:`~AppListView.set_filter` on the AppImage list
        view, so the main window can drive both views through the same search
        signal.
        """
        self.beginResetModel()
        self._rows = []
        self._query = query
        self._has_more = False
        self.endResetModel()

        if not query or self._index is None:
            return

        # Load the first page immediately after the reset so the view has
        # something to render without waiting for the first fetchMore call.
        first_page = self._index.search(query, limit=_PAGE_SIZE, offset=0)
        if not first_page:
            return
        self.beginInsertRows(QModelIndex(), 0, len(first_page) - 1)
        self._rows = list(first_page)
        self.endInsertRows()
        self._has_more = len(first_page) == _PAGE_SIZE

    def row_at(self, row: int) -> dict | None:
        """Return the raw dict for *row*, or ``None`` if out of range."""
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def find_by_id(self, app_id: str) -> int | None:
        """Return the row index for *app_id*, or ``None`` if not loaded."""
        for i, row in enumerate(self._rows):
            if row.get("id") == app_id:
                return i
        return None


class PacmanModel(QAbstractListModel):
    """Paginated list model backed by :class:`~aurelis_software.services.pacman_index.PacmanIndex`.

    Implements Qt's ``canFetchMore`` / ``fetchMore`` protocol so that only
    one page of results (``_PAGE_SIZE`` rows) is in memory at a time.  The
    view calls ``fetchMore`` automatically as the user scrolls.

    Roles are identical to :class:`AppModel` so :class:`~aurelis_software.ui.app_card_delegate.AppCardDelegate`
    renders Pacman cards without any changes.

    Usage::

        model = PacmanModel(index)
        model.set_query("firefox")   # reset + first page
        view.setModel(model)         # view calls fetchMore as needed
    """

    # Same role constants as AppModel so AppCardDelegate needs no changes.
    IdRole = Qt.ItemDataRole.UserRole + 1
    KeyRole = Qt.ItemDataRole.UserRole + 2
    NameRole = Qt.ItemDataRole.UserRole + 3
    SummaryRole = Qt.ItemDataRole.UserRole + 4
    VersionRole = Qt.ItemDataRole.UserRole + 5
    SourceRole = Qt.ItemDataRole.UserRole + 6
    StoreCategoriesRole = Qt.ItemDataRole.UserRole + 7
    RawRole = Qt.ItemDataRole.UserRole + 8

    def __init__(self, index: PacmanIndex | None = None, parent=None) -> None:
        super().__init__(parent)
        self._index: PacmanIndex | None = index
        self._rows: list[dict] = []
        self._query: str = ""
        # True while we know more pages exist (last fetch returned a full page).
        self._has_more: bool = False

    # ------------------------------------------------------------------ Qt interface

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:  # noqa: N802
        return False if parent.isValid() else self._has_more

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:  # noqa: N802
        if parent.isValid() or not self._has_more or self._index is None:
            return
        offset = len(self._rows)
        new_rows = self._index.search(self._query, limit=_PAGE_SIZE, offset=offset)
        if not new_rows:
            self._has_more = False
            return
        first = offset
        last = offset + len(new_rows) - 1
        self.beginInsertRows(QModelIndex(), first, last)
        self._rows.extend(new_rows)
        self.endInsertRows()
        # If the returned page was full, more results may exist.
        self._has_more = len(new_rows) == _PAGE_SIZE

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        row = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            role = self.NameRole
        return {
            self.IdRole: row.get("name", ""),
            self.KeyRole: f"pacman:{row.get('name', '')}",
            self.NameRole: row.get("name", ""),
            self.SummaryRole: row.get("description", ""),
            self.VersionRole: row.get("version"),
            self.SourceRole: Source.PACMAN,
            self.StoreCategoriesRole: tuple(),
            self.RawRole: row.get("raw", row),
        }.get(role)

    def roleNames(self):  # noqa: N802
        return {
            self.IdRole: b"id",
            self.KeyRole: b"key",
            self.NameRole: b"name",
            self.SummaryRole: b"summary",
            self.VersionRole: b"version",
            self.SourceRole: b"source",
            self.StoreCategoriesRole: b"store_categories",
            self.RawRole: b"raw",
        }

    # ------------------------------------------------------------------ convenience

    def set_index(self, index: PacmanIndex | None) -> None:
        """Replace the backing index and clear the current results."""
        self._index = index
        self.set_query(self._query)

    def set_query(self, query: str) -> None:
        """Reset the model and load the first page for *query*.

        This is the primary control point wired to the search bar — it plays
        the same role as :meth:`~AppListView.set_filter` on the AppImage list
        view, so the main window can drive both views through the same search
        signal.
        """
        self.beginResetModel()
        self._rows = []
        self._query = query
        self._has_more = False
        self.endResetModel()

        if not query or self._index is None:
            return

        # Load the first page immediately after the reset so the view has
        # something to render without waiting for the first fetchMore call.
        first_page = self._index.search(query, limit=_PAGE_SIZE, offset=0)
        if not first_page:
            return
        self.beginInsertRows(QModelIndex(), 0, len(first_page) - 1)
        self._rows = list(first_page)
        self.endInsertRows()
        self._has_more = len(first_page) == _PAGE_SIZE

    def row_at(self, row: int) -> dict | None:
        """Return the raw dict for *row*, or ``None`` if out of range."""
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def find_by_id(self, app_id: str) -> int | None:
        """Return the row index for *app_id*, or ``None`` if not loaded."""
        for i, row in enumerate(self._rows):
            if row.get("name") == app_id:
                return i
        return None
