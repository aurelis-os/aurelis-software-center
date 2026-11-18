"""InstalledPage: unified installed apps view with live refresh (section 10.4, P3.7)."""

from __future__ import annotations

from pathlib import Path
from typing import override

from PyQt6.QtCore import QSortFilterProxyModel, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from aurelis_software.core.models import InstalledApp
from aurelis_software.ui.app_card_delegate import AppCardDelegate
from aurelis_software.ui.app_model import AppModel


class InstalledAppModel(AppModel):
    """Model for installed apps with additional roles."""

    PathRole = Qt.ItemDataRole.UserRole + 9
    RoleRole = Qt.ItemDataRole.UserRole + 10
    Sha256Role = Qt.ItemDataRole.UserRole + 11
    UpdatePolicyRole = Qt.ItemDataRole.UserRole + 12
    SelfManagedRole = Qt.ItemDataRole.UserRole + 13
    OriginRole = Qt.ItemDataRole.UserRole + 14
    LockedRole = Qt.ItemDataRole.UserRole + 15
    PendingRole = Qt.ItemDataRole.UserRole + 16
    PreviousRole = Qt.ItemDataRole.UserRole + 17
    UpdateAvailableRole = Qt.ItemDataRole.UserRole + 18
    UnmanagedRole = Qt.ItemDataRole.UserRole + 19

    def __init__(self, apps: list[InstalledApp] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._apps: list[InstalledApp] = list(apps or [])

    def rowCount(self, parent=...) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._apps)

    def data(self, index, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._apps):
            return None
        app = self._apps[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            role = self.NameRole
        raw_dict = {
            "path": app.path,
            "role": app.role,
            "sha256": app.sha256,
            "update_policy": app.update_policy,
            "self_managed": app.self_managed,
            "origin": app.origin,
            "locked": app.locked,
            "pending": app.pending,
            "previous": app.previous,
        }
        # Include dynamic attributes if present
        if hasattr(app, "update_available"):
            raw_dict["update_available"] = app.update_available
        if app.origin is None:
            raw_dict["unmanaged"] = True
        return {
            self.IdRole: app.id,
            self.KeyRole: f"{app.source.value}:{app.id}",
            self.NameRole: app.name,
            self.SummaryRole: app.version or "",
            self.VersionRole: app.version,
            self.SourceRole: app.source,
            self.StoreCategoriesRole: app.store_categories
            if hasattr(app, "store_categories")
            else (),
            self.RawRole: raw_dict,
            self.PathRole: app.path,
            self.RoleRole: app.role,
            self.Sha256Role: app.sha256,
            self.UpdatePolicyRole: app.update_policy,
            self.SelfManagedRole: app.self_managed,
            self.OriginRole: app.origin,
            self.LockedRole: app.locked,
            self.PendingRole: app.pending,
            self.PreviousRole: app.previous,
            self.UpdateAvailableRole: getattr(app, "update_available", False),
            self.UnmanagedRole: app.origin is None,
        }.get(role)

    @override
    def roleNames(self):
        base = super().roleNames()
        base.update(
            {
                self.PathRole: b"path",
                self.RoleRole: b"role",
                self.Sha256Role: b"sha256",
                self.UpdatePolicyRole: b"update_policy",
                self.SelfManagedRole: b"self_managed",
                self.OriginRole: b"origin",
                self.LockedRole: b"locked",
                self.PendingRole: b"pending",
                self.PreviousRole: b"previous",
                self.UpdateAvailableRole: b"update_available",
                self.UnmanagedRole: b"unmanaged",
            }
        )
        return base

    def set_apps(self, apps: list[InstalledApp]) -> None:
        self.beginResetModel()
        self._apps = list(apps)
        self.endResetModel()

    def app_at(self, row: int) -> InstalledApp | None:
        if 0 <= row < len(self._apps):
            return self._apps[row]
        return None

    def find_by_id(self, app_id: str) -> int | None:
        for row, app in enumerate(self._apps):
            if app.id == app_id:
                return row
        return None


class InstalledPage(QWidget):
    """Installed page showing all sources in one list (section 10.4)."""

    _selection_changed = pyqtSignal(str)  # app_id

    def selection_changed(self, callback):
        self._selection_changed.connect(callback)

    def __init__(self, icons_dir: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self.icons_dir = icons_dir
        self._filter_text = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Filter bar
        filter_bar = QWidget()
        filter_bar.setFixedHeight(52)
        filter_bar.setStyleSheet("background: #fafafa; border-bottom: 1px solid #d1d1d6;")
        f_layout = QHBoxLayout(filter_bar)
        f_layout.setContentsMargins(16, 0, 16, 0)
        f_layout.setSpacing(12)

        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("font-size: 13px; color: #1d1d1f;")
        f_layout.addWidget(filter_label)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter installed apps…")
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.setFixedHeight(32)
        self._filter_edit.setStyleSheet(
            "QLineEdit {"
            "  background: white;"
            "  border: 1px solid #d1d1d6;"
            "  border-radius: 8px;"
            "  padding: 0 10px;"
            "  font-size: 13px;"
            "  color: #1d1d1f;"
            "}"
            "QLineEdit:focus { border: 1.5px solid #0071e3; }"
        )
        self._filter_edit.textChanged.connect(self._on_filter_changed)
        f_layout.addWidget(self._filter_edit, stretch=1)

        # Rescan button
        self._rescan_btn = QPushButton("Rescan")
        self._rescan_btn.setFixedHeight(32)
        self._rescan_btn.setFixedWidth(100)
        self._rescan_btn.setStyleSheet(
            "QPushButton {"
            "  background: #0071e3; color: white; border: none;"
            "  border-radius: 8px; font-size: 13px; font-weight: 600;"
            "}"
            "QPushButton:hover { background: #0077ed; }"
        )
        self._rescan_btn.clicked.connect(self._on_rescan)
        f_layout.addWidget(self._rescan_btn)

        layout.addWidget(filter_bar)

        # List view
        self._model = InstalledAppModel()
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterRole(self._model.NameRole)

        self._view = QListView()
        self._view.setViewMode(QListView.ViewMode.IconMode)
        self._view.setFlow(QListView.Flow.LeftToRight)
        self._view.setWrapping(True)
        self._view.setSpacing(12)
        self._view.setModel(self._proxy)
        self._view.setItemDelegate(AppCardDelegate(icons_dir=icons_dir, parent=self._view))
        self._view.setUniformItemSizes(True)
        self._view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._view.setResizeMode(QListView.ResizeMode.Adjust)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setContentsMargins(16, 16, 16, 16)

        from PyQt6.QtCore import QSize

        from aurelis_software.ui.app_card_delegate import CARD_H, CARD_MIN_W

        self._view.setGridSize(QSize(CARD_MIN_W + 12, CARD_H + 12))

        layout.addWidget(self._view)

        # Selection
        self._view.selectionModel().selectionChanged.connect(self._on_selection_changed)

        # Empty state
        self._empty_label = QLabel(self.tr("No installed apps."))
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #86868b; font-size: 15px;")
        self._empty_label.hide()
        layout.addWidget(self._empty_label)

    def set_apps(self, apps: list[InstalledApp]) -> None:
        self._model.set_apps(apps)
        self._update_empty_state()

    def set_filter(self, text: str) -> None:
        self._filter_edit.setText(text)

    def _on_filter_changed(self, text: str) -> None:
        self._filter_text = text
        self._proxy.setFilterFixedString(text)
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        has_apps = self._proxy.rowCount() > 0
        self._view.setVisible(has_apps)
        self._empty_label.setVisible(not has_apps)

    def _on_selection_changed(self) -> None:
        idx = self._view.currentIndex()
        if not idx.isValid():
            return
        source_idx = self._proxy.mapToSource(idx)
        app = self._model.app_at(source_idx.row())
        if app:
            self._selection_changed.emit(app.id)

    def _on_rescan(self) -> None:
        # Emit a signal that the main window can connect to
        self.rescan_requested.emit()

    rescan_requested = pyqtSignal()
