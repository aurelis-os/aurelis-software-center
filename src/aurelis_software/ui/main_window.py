"""MainWindow: shell and read-only Explore (sections 10.1-10.3, P2.1-P2.4)."""

from __future__ import annotations

import platform

from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from aurelis_software.core.catalog import CatalogSchemaTooNew, load_catalog
from aurelis_software.core.config import Config
from aurelis_software.core.models import App
from aurelis_software.core.paths import Paths
from aurelis_software.core.search import build_index, search
from aurelis_software.ui.app_list_view import AppListView
from aurelis_software.ui.detail_page import DetailPage
from aurelis_software.ui.settings_dialog import SettingsDialog
from aurelis_software.ui.sidebar import (
    SECTION_EXPLORE,
    SECTION_SETTINGS,
    SECTION_UPDATES,
    Sidebar,
)

SEARCH_DEBOUNCE_MS = 120

_TOOLBAR_H = 52
_TOOLBAR_BG = "#f5f5f7"  # macOS-like light grey toolbar
_TOOLBAR_BORDER = "#d1d1d6"
_SIDEBAR_BG = "#f0f0f2"
_SIDEBAR_BORDER = "#d1d1d6"
_CONTENT_BG = "#ffffff"


class MainWindow(QMainWindow):
    """The single software-center window."""

    def __init__(self, paths: Paths, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.paths = paths
        self.config = config
        self.setWindowTitle(self.tr("Aurelis Software"))
        self.resize(1200, 800)
        self.setMinimumSize(640, 480)

        self._catalog_apps: list[App] = []
        self._index = None
        self._catalog_loaded = False

        # ── Root layout ────────────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ────────────────────────────────────────────────────────
        self._sidebar = Sidebar()
        self._sidebar.setFixedWidth(200)
        self._sidebar.setStyleSheet(
            f"QWidget {{ background: {_SIDEBAR_BG}; }}"
            f"QListWidget {{ background: {_SIDEBAR_BG}; border: none; "
            f"  border-right: 1px solid {_SIDEBAR_BORDER}; }}"
            "QListWidget::item { padding: 6px 16px; border-radius: 6px; margin: 1px 6px; }"
            "QListWidget::item:selected { background: #0071e3; color: white; }"
            "QListWidget::item:hover:!selected { background: rgba(0,0,0,0.06); }"
        )
        root.addWidget(self._sidebar, stretch=0)

        # ── Centre column ──────────────────────────────────────────────────
        self._center = QWidget()
        self._center.setStyleSheet(f"QWidget {{ background: {_CONTENT_BG}; }}")
        center_layout = QVBoxLayout(self._center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        # Toolbar
        toolbar = _Toolbar(self.tr("Explore"))
        self._search = toolbar.search_edit
        center_layout.addWidget(toolbar)

        # Banner area
        self._banner = QWidget()
        self._banner.setStyleSheet(f"background: {_CONTENT_BG};")
        self._banner_layout = QVBoxLayout(self._banner)
        self._banner_layout.setContentsMargins(16, 4, 16, 4)
        self._banner_layout.setSpacing(4)
        center_layout.addWidget(self._banner)

        # Page stack
        self._stack = QStackedWidget()
        self._explore = AppListView(icons_dir=paths.icons_dir)
        self._detail = DetailPage(icons_dir=paths.icons_dir)
        self._stack.addWidget(self._explore)
        self._stack.addWidget(self._detail)
        center_layout.addWidget(self._stack, stretch=1)

        root.addWidget(self._center, stretch=1)

        # ── Wiring ─────────────────────────────────────────────────────────
        self._sidebar.item_selected.connect(self._on_section)
        self._search.textChanged.connect(self._on_search_text_changed)
        self._explore.selection_changed(self._on_selection_changed)
        self._detail.install_requested.connect(self._on_install_requested)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._run_search)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)

        self._load_catalog()

        if not bool(self.config.get("network.offline")):
            self._refresh_worker = CatalogRefreshWorker(self.paths, self.config, self)
            self._refresh_worker.finished.connect(self._on_refresh_finished)
            self._refresh_worker.start()

    # ------------------------------------------------------------------ catalog

    def _load_catalog(self) -> None:
        catalog_path = self.paths.catalog_db
        try:
            result = load_catalog(catalog_path)
        except FileNotFoundError:
            self._show_banner("no catalog cache; run `catalog refresh`", kind="error")
            self._catalog_apps = []
            self._index = None
            self._catalog_loaded = True
            self._catalog_load_failed = True
            self._refresh_explore()
            return
        except (
            OSError,
            ValueError,
            TypeError,
            CatalogSchemaTooNew,
        ) as exc:  # pragma: no cover
            self._show_banner(f"could not read catalog cache: {exc}", kind="error")
            self._catalog_apps = []
            self._index = None
            self._catalog_loaded = True
            self._catalog_load_failed = True
            self._refresh_explore()
            return

        self._catalog_apps = result.apps
        try:
            self._index = build_index(result.apps)
        except (TypeError, AttributeError):  # pragma: no cover
            self._index = None
        self._catalog_loaded = True
        self._catalog_load_failed = False
        self._refresh_explore()

    def _refresh_explore(self) -> None:
        apps = self._filtered_apps(self._current_query())
        self._explore.set_apps(apps)
        if not apps and self._catalog_loaded and not getattr(self, "_catalog_load_failed", False):
            if self._current_query():
                self._show_banner(self.tr("No results."), kind="info")
            else:
                self._show_banner(self.tr("No apps in the catalog."), kind="info")

    # ------------------------------------------------------------------ search

    def _on_search_text_changed(self, text: str) -> None:
        self._hide_banner()
        self._search_timer.start()

    def _run_search(self) -> None:
        query = self._current_query()
        apps = self._filtered_apps(query)
        self._explore.set_apps(apps)
        self._explore.scroll_to_top()
        if not apps and self._catalog_loaded:
            self._show_banner(self.tr("No results."), kind="info")

    def _current_query(self) -> str:
        return self._search.text().strip()

    def _filtered_apps(self, query: str) -> list[App]:
        if self._index is None:
            return []
        apps = list(self._catalog_apps) if not query else search(self._index, query)
        if self.config.get("ui.hide_incompatible"):
            host = _host_arch()
            apps = [app for app in apps if _arch_compatible(app, host)]
        return apps

    def _on_refresh_finished(self, result) -> None:
        if result.error is not None:
            self._show_banner(
                self.tr("Could not refresh the catalog. Showing the last saved version."),
                kind="warning",
            )
            return
        if result.changed and result.catalog is not None:
            self._catalog_apps = result.catalog.apps
            try:
                self._index = build_index(self._catalog_apps)
            except (TypeError, AttributeError):  # pragma: no cover
                self._index = None
            self._refresh_explore()

    # ------------------------------------------------------------------ navigation

    def _on_section(self, section: str) -> None:
        self._search.clear()
        self._hide_banner()
        if section == SECTION_EXPLORE:
            self._stack.setCurrentWidget(self._explore)
            self._refresh_explore()
        elif section == SECTION_UPDATES:
            self._show_placeholder(
                self.tr("Updates"), self.tr("Updates appear here after the first catalog refresh.")
            )
        elif section == SECTION_SETTINGS:
            dlg = SettingsDialog(self.paths, self.config, self)
            if dlg.exec():
                from aurelis_software.core.config import load

                self.config = load(self.paths)
                self._refresh_explore()
            self._sidebar.select_section(SECTION_EXPLORE)
        else:
            self._show_placeholder(
                section, self.tr("{section} is not available in Phase 2.").format(section=section)
            )

    def _on_selection_changed(self) -> None:
        app = self._explore.current_app()
        if app is None:
            return
        self._detail.set_app(app)
        self._stack.setCurrentWidget(self._detail)

    def _on_install_requested(self, app_id: str) -> None:
        pass

    def _show_placeholder(self, title: str, text: str) -> None:
        self._stack.setCurrentWidget(self._explore)
        self._explore.set_apps([])
        self._show_banner(f"{title}: {text}", kind="info")

    # ------------------------------------------------------------------ banners

    def _show_banner(self, text: str, kind: str = "info") -> None:
        self._hide_banner()
        from aurelis_software.ui.banners import Banner

        banner = Banner(text, kind=kind, parent=self._banner)
        self._banner_layout.addWidget(banner)
        self._current_banner = banner

    def _hide_banner(self) -> None:
        banner = getattr(self, "_current_banner", None)
        if banner is not None:
            self._banner_layout.removeWidget(banner)
            banner.deleteLater()
            self._current_banner = None


# ── Toolbar widget ─────────────────────────────────────────────────────────────


class _Toolbar(QWidget):
    """macOS-style toolbar: title on the left, centred search field."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(_TOOLBAR_H)
        self.setStyleSheet(
            f"_Toolbar {{ background: {_TOOLBAR_BG}; border-bottom: 1px solid {_TOOLBAR_BORDER}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            "font-size: 15px; font-weight: 600; color: #1d1d1f; background: transparent;"
        )
        layout.addWidget(title_label, stretch=0)

        layout.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search apps…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedHeight(32)
        self.search_edit.setFixedWidth(260)
        self.search_edit.setStyleSheet(
            "QLineEdit {"
            "  background: rgba(0,0,0,0.07);"
            "  border: 1px solid rgba(0,0,0,0.12);"
            "  border-radius: 8px;"
            "  padding: 0 10px;"
            "  font-size: 13px;"
            "  color: #1d1d1f;"
            "}"
            "QLineEdit:focus {"
            "  background: white;"
            "  border: 1.5px solid #0071e3;"
            "}"
        )
        layout.addWidget(self.search_edit, stretch=0)

        layout.addStretch(1)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _host_arch() -> str:
    machine = platform.machine().lower()
    table = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
        "armv7l": "armv7l",
        "i686": "i686",
        "i386": "i686",
    }
    return table.get(machine, machine)


def _arch_compatible(app: App, host_arch: str) -> bool:
    arch = app.raw.get("arch")
    if arch is None:
        return True
    return str(arch) == host_arch


class CatalogRefreshWorker(QThread):
    finished = pyqtSignal(object)

    def __init__(self, paths: Paths, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.paths = paths
        self.config = config

    def run(self) -> None:
        from aurelis_software.services.db_updater import DbUpdater, url_fetch

        updater = DbUpdater(self.paths, self.config, url_fetch)
        result = updater.refresh(force=False)
        self.finished.emit(result)
