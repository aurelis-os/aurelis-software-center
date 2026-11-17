"""AppModel: a QAbstractListModel of catalog App entries (section 10.2)."""

from __future__ import annotations

from PyQt6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    Qt,
)

from aurelis_software.core.models import App


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
