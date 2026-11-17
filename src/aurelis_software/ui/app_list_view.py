"""AppListView: icon-grid list view backed by AppModel and a proxy (section 10.2)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, QSize, QSortFilterProxyModel, Qt
from PyQt6.QtWidgets import QListView, QVBoxLayout, QWidget

from aurelis_software.ui.app_card_delegate import CARD_H, CARD_MIN_W, AppCardDelegate
from aurelis_software.ui.app_model import AppModel

_SPACING = 12


class AppListView(QWidget):
    """A widget containing a QListView in icon-grid mode with a proxy model."""

    def __init__(self, icons_dir: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._model = AppModel()
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterRole(AppModel.NameRole)

        self._view = QListView()
        self._view.setViewMode(QListView.ViewMode.IconMode)
        self._view.setFlow(QListView.Flow.LeftToRight)
        self._view.setWrapping(True)
        self._view.setSpacing(_SPACING)
        self._view.setModel(self._proxy)
        self._view.setItemDelegate(AppCardDelegate(icons_dir=icons_dir, parent=self._view))
        self._view.setUniformItemSizes(True)
        self._view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._view.setResizeMode(QListView.ResizeMode.Adjust)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setContentsMargins(0, 0, 0, 0)

        self._view.viewport().installEventFilter(self)
        self._view.setGridSize(QSize(CARD_MIN_W + _SPACING, CARD_H + _SPACING))

        layout.addWidget(self._view)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self._view.viewport() and event.type() == QEvent.Type.Resize:
            self._update_grid_size()
        return super().eventFilter(watched, event)

    def _update_grid_size(self) -> None:
        vp_w = self._view.viewport().width()
        if vp_w <= 0:
            return
        # How many columns fit? At least 1, prefer as many as possible ≥ CARD_MIN_W.
        cols = max(1, (vp_w + _SPACING) // (CARD_MIN_W + _SPACING))
        # Distribute the full viewport width evenly across columns.
        cell_w = (vp_w - (cols - 1) * _SPACING) // cols
        cell_w = max(cell_w, CARD_MIN_W)
        new_size = QSize(cell_w, CARD_H)
        if new_size != self._view.gridSize():
            self._view.setGridSize(new_size)
            self._view.doItemsLayout()

    def set_apps(self, apps) -> None:
        self._model.set_apps(apps)

    def set_filter(self, text: str) -> None:
        self._proxy.setFilterFixedString(text)

    def set_icons_dir(self, icons_dir: Path | None) -> None:
        delegate = self._view.itemDelegate()
        if delegate is not None:
            delegate.icons_dir = icons_dir

    def selection_changed(self, callback):
        self._view.selectionModel().selectionChanged.connect(callback)

    def current_app(self):
        idx = self._view.currentIndex()
        if not idx.isValid():
            return None
        source_idx = self._proxy.mapToSource(idx)
        return self._model.app_at(source_idx.row())

    def scroll_to_top(self) -> None:
        self._view.scrollToTop()
