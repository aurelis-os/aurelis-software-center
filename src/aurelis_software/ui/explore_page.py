"""ExplorePage: layout with "Recently updated", per-category rows, and "All apps" grid (Phase 8, Task 5.1)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLabel,
    QListView,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from aurelis_software.core.models import App
from aurelis_software.ui.app_card_delegate import CARD_H, AppCardDelegate
from aurelis_software.ui.app_list_view import AppListView
from aurelis_software.ui.app_model import AppModel

_SPACING = 12
_ROW_SCROLL_HEIGHT = CARD_H + _SPACING + 10


class _HorizontalCardScroll(QWidget):
    """A horizontal scrolling row of cards."""

    selection_changed = pyqtSignal(object)

    def __init__(self, icons_dir: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self._icons_dir = icons_dir

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._model = AppModel()
        self._view = QListView()
        self._view.setViewMode(QListView.ViewMode.IconMode)
        self._view.setFlow(QListView.Flow.LeftToRight)
        self._view.setWrapping(False)
        self._view.setSpacing(_SPACING)
        self._view.setModel(self._model)
        self._view.setItemDelegate(AppCardDelegate(icons_dir=icons_dir, parent=self._view))
        self._view.setUniformItemSizes(True)
        self._view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._view.setResizeMode(QListView.ResizeMode.Adjust)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setMinimumHeight(_ROW_SCROLL_HEIGHT)
        self._view.setMaximumHeight(_ROW_SCROLL_HEIGHT)
        self._view.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._view)

        self._view.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def set_apps(self, apps: list[App]) -> None:
        self._model.set_apps(apps)

    def _on_selection_changed(self, selected, deselected) -> None:
        idx = self._view.currentIndex()
        if not idx.isValid():
            return
        app = self._model.app_at(idx.row())
        if app:
            self.selection_changed.emit(app)

    def current_app(self) -> App | None:
        idx = self._view.currentIndex()
        if not idx.isValid():
            return None
        return self._model.app_at(idx.row())


class ExplorePage(QWidget):
    """Explore page with "Recently updated", per-category rows, and "All apps" grid."""

    selection_changed = pyqtSignal(object)

    def __init__(self, icons_dir: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self._icons_dir = icons_dir
        self._apps: list[App] = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # Scrollable container for the entire page
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_container = QWidget()
        scroll_layout = QVBoxLayout(scroll_container)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(24)

        # "Recently updated" section
        self._recently_label = QLabel(self.tr("Recently updated"))
        self._recently_label.setStyleSheet("font-size: 18pt; font-weight: 600;")
        scroll_layout.addWidget(self._recently_label)

        self._recently_scroll = _HorizontalCardScroll(icons_dir=icons_dir)
        self._recently_scroll.selection_changed.connect(self._on_card_selected)
        scroll_layout.addWidget(self._recently_scroll)

        # Category sections container
        self._category_container = QWidget()
        self._category_layout = QVBoxLayout(self._category_container)
        self._category_layout.setContentsMargins(0, 0, 0, 0)
        self._category_layout.setSpacing(24)
        scroll_layout.addWidget(self._category_container)

        # "All apps" section
        self._all_apps_label = QLabel(self.tr("All apps"))
        self._all_apps_label.setStyleSheet("font-size: 18pt; font-weight: 600;")
        scroll_layout.addWidget(self._all_apps_label)

        self._all_apps_view = AppListView(icons_dir=icons_dir)
        self._all_apps_view.selection_changed(self._on_grid_selected)
        scroll_layout.addWidget(self._all_apps_view, stretch=1)

        scroll_area.setWidget(scroll_container)
        main_layout.addWidget(scroll_area)

        self._category_sections: list[tuple[QLabel, _HorizontalCardScroll]] = []

    def set_apps(self, apps: list[App]) -> None:
        """Set the apps to display in all three sections."""
        self._apps = apps

        # Section 1: "Recently updated" — top 6 by version_changed_at
        recently_apps = sorted(
            [a for a in apps if a.raw.get("version_changed_at")],
            key=lambda a: a.raw.get("version_changed_at", ""),
            reverse=True,
        )[:6]
        self._recently_scroll.set_apps(recently_apps)

        # Section 2: Per-category rows
        # Clear existing category sections
        for label, scroll in self._category_sections:
            label.deleteLater()
            scroll.deleteLater()
        self._category_sections.clear()

        # Build category map
        category_map: dict[str, list[App]] = {}
        for app in apps:
            for cat in app.categories:
                if cat not in category_map:
                    category_map[cat] = []
                category_map[cat].append(app)

        # Create category sections (only if >= 1 app)
        for category_name in sorted(category_map.keys()):
            category_apps = category_map[category_name]
            if len(category_apps) == 0:
                continue

            cat_label = QLabel(category_name)
            cat_label.setStyleSheet("font-size: 14pt; font-weight: 600;")
            self._category_layout.addWidget(cat_label)

            cat_scroll = _HorizontalCardScroll(icons_dir=self._icons_dir)
            cat_scroll.selection_changed.connect(self._on_card_selected)
            cat_scroll.set_apps(category_apps)
            self._category_layout.addWidget(cat_scroll)

            self._category_sections.append((cat_label, cat_scroll))

        # Section 3: "All apps" grid
        self._all_apps_view.set_apps(apps)

    def _on_card_selected(self, app: App) -> None:
        """Emit selection_changed when a card is selected in any horizontal scroll."""
        self.selection_changed.emit(app)

    def _on_grid_selected(self) -> None:
        """Emit selection_changed when a card is selected in the All apps grid."""
        app = self._all_apps_view.current_app()
        if app:
            self.selection_changed.emit(app)

    @property
    def _model(self):
        """Expose the underlying model for backward compatibility with tests."""
        return self._all_apps_view._model

    @property
    def _view(self):
        """Expose the underlying view for backward compatibility with tests."""
        return self._all_apps_view._view

    def _update_grid_size(self) -> None:
        """Update grid size - delegates to all_apps_view."""
        self._all_apps_view._update_grid_size()

    def scroll_to_top(self) -> None:
        """Scroll to the top of the page."""
        # Find the scroll area and scroll to top
        for child in self.children():
            if isinstance(child, QScrollArea):
                child.verticalScrollBar().setValue(0)
                break
