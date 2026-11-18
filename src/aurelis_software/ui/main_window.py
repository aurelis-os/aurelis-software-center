"""MainWindow: full software center with Explore, Installed, Updates (P2-P3)."""

from __future__ import annotations

import platform
from pathlib import Path
from typing import override

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from aurelis_software.backends.appimage import AppImageBackend
from aurelis_software.core.catalog import CatalogSchemaTooNew, load_catalog
from aurelis_software.core.config import Config
from aurelis_software.core.errors import AurelisError
from aurelis_software.core.matching import MatchKind, build_origin, match_installed_to_catalog
from aurelis_software.core.models import App, InstalledApp, Source
from aurelis_software.core.paths import Paths
from aurelis_software.core.search import build_index, search
from aurelis_software.core.versions import update_available
from aurelis_software.services.db_updater import DbUpdater, url_fetch
from aurelis_software.services.downloader import Downloader
from aurelis_software.services.operations import OperationQueue
from aurelis_software.services.qt_dbus import DbusClient
from aurelis_software.services.qt_operations import QtOperationFactory
from aurelis_software.ui.app_list_view import AppListView
from aurelis_software.ui.banners import Banner
from aurelis_software.ui.conflict_dialog import ConflictDialog, UnverifiedDownloadDialog
from aurelis_software.ui.detail_page import DetailPage
from aurelis_software.ui.progress_widgets import show_toast
from aurelis_software.ui.settings_dialog import SettingsDialog
from aurelis_software.ui.sidebar import (
    SECTION_EXPLORE,
    SECTION_INSTALLED,
    SECTION_SETTINGS,
    SECTION_UPDATES,
    Sidebar,
)

SEARCH_DEBOUNCE_MS = 120

_TOOLBAR_H = 52
_TOOLBAR_BG = "#f5f5f7"
_TOOLBAR_BORDER = "#d1d1d6"
_SIDEBAR_BG = "#f0f0f2"
_SIDEBAR_BORDER = "#d1d1d6"
_CONTENT_BG = "#ffffff"

# D-Bus constants
DBUS_SERVICE = "io.github.appimage_launcher.Manager"
DBUS_PATH = "/io/github/appimage_launcher/Manager"
DBUS_INTERFACE = "io.github.appimage_launcher.Manager1"


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

        # Backends
        self._appimage_backend: AppImageBackend | None = None
        self._appimage_available = False
        self._dbus_client: DbusClient | None = None

        # Operations
        self._operation_queue = OperationQueue()
        self._qt_ops = QtOperationFactory()
        self._active_operations: dict[
            str, tuple[App, str, str]
        ] = {}  # op_id -> (app, kind, app_key)

        # Installed apps cache
        self._installed_apps: dict[str, InstalledApp] = {}
        self._installed_by_catalog_id: dict[str, InstalledApp] = {}

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
        self._toolbar = _Toolbar(self.tr("Explore"))
        self._search = self._toolbar.search_edit
        center_layout.addWidget(self._toolbar)

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
        # self._installed = InstalledPage(icons_dir=paths.icons_dir)
        self._detail = DetailPage(icons_dir=paths.icons_dir)
        self._updates_placeholder = self._make_placeholder(
            self.tr("Updates"), self.tr("Updates appear here after the first catalog refresh.")
        )
        self._stack.addWidget(self._explore)
        # self._stack.addWidget(self._installed)
        self._stack.addWidget(self._detail)
        self._stack.addWidget(self._updates_placeholder)
        center_layout.addWidget(self._stack, stretch=1)

        # Operations tray (initially hidden)
        # self._operations_tray = OperationsTray()
        # self._operations_tray.hide()
        # center_layout.addWidget(self._operations_tray)

        root.addWidget(self._center, stretch=1)

        # ── Wiring ─────────────────────────────────────────────────────────
        self._sidebar.item_selected.connect(self._on_section)
        self._search.textChanged.connect(self._on_search_text_changed)
        self._explore.selection_changed(self._on_selection_changed)
        # self._installed.selection_changed(self._on_installed_selection)
        self._detail.install_requested.connect(self._on_install_requested)
        self._detail.update_requested.connect(self._on_update_requested)
        self._detail.remove_requested.connect(self._on_remove_requested)
        self._detail.open_requested.connect(self._on_open_requested)
        self._detail.show_in_folder_requested.connect(self._on_show_in_folder)
        self._detail.revert_requested.connect(self._on_revert_requested)
        self._detail.set_policy_requested.connect(self._on_set_policy)
        self._detail.set_origin_requested.connect(self._on_set_origin)
        self._detail.link_to_catalog_requested.connect(self._on_link_to_catalog)
        self._detail.app_name_changed.connect(self._toolbar.set_title)
        self._detail.cancel_requested.connect(self._on_cancel_requested)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._run_search)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)

        # Initialize D-Bus client and AppImage backend
        self._init_dbus()

        self._load_catalog()

        if not bool(self.config.get("network.offline")):
            self._refresh_worker = CatalogRefreshWorker(self.paths, self.config, self)
            self._refresh_worker.finished.connect(self._on_refresh_finished)
            self._refresh_worker.start()

    @override
    def closeEvent(self, event) -> None:
        """Clean up resources on close."""
        # Stop timers
        if hasattr(self, "_search_timer") and self._search_timer.isActive():
            self._search_timer.stop()
        if hasattr(self, "_apps_changed_timer") and self._apps_changed_timer.isActive():
            self._apps_changed_timer.stop()

        # Stop refresh worker if running
        if hasattr(self, "_refresh_worker") and self._refresh_worker.isRunning():
            self._refresh_worker.quit()
            self._refresh_worker.wait(1000)

        # Clean up D-Bus client
        if hasattr(self, "_dbus_client") and self._dbus_client:
            self._dbus_client.cleanup()

        super().closeEvent(event)

    # ------------------------------------------------------------------ D-Bus / Backend init

    def _init_dbus(self) -> None:
        """Initialize D-Bus connection and AppImage backend."""
        from PyQt6.QtDBus import QDBusConnection

        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            self._show_banner(
                self.tr("D-Bus session bus not available. AppImage features disabled."),
                kind="error",
            )
            return

        self._dbus_client = DbusClient(bus)
        self._appimage_backend = AppImageBackend(self._dbus_client)

        # Check availability
        self._appimage_backend.check_availability(
            ok_cb=self._on_backend_available,
            fail_cb=self._on_backend_unavailable,
        )

    def _on_backend_available(self, version: int, caps: dict) -> None:
        self._appimage_available = True
        # Refresh installed list
        self._refresh_installed_list()
        # Subscribe to AppsChanged
        self._appimage_backend.subscribe_apps_changed(self._on_apps_changed)

    def _on_backend_unavailable(self, error: AurelisError) -> None:
        self._appimage_available = False
        self._show_banner(
            self.tr("AppImage service unavailable: {error}").format(error=error.message),
            kind="warning",
        )

    def _on_apps_changed(self, kind: str, app_id: str, source: str) -> None:
        """Handle AppsChanged signal from daemon (debounced)."""
        # Debounce: schedule a refresh
        if not hasattr(self, "_apps_changed_timer"):
            self._apps_changed_timer = QTimer(self)
            self._apps_changed_timer.setSingleShot(True)
            self._apps_changed_timer.setInterval(300)
            self._apps_changed_timer.timeout.connect(self._refresh_installed_list)
        self._apps_changed_timer.start()

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

        # If we have AppImage backend, do matching now
        if self._appimage_available:
            self._refresh_installed_list()

    def _refresh_explore(self) -> None:
        apps = self._filtered_apps(self._current_query())
        self._explore.set_apps(apps)
        if not apps and self._catalog_loaded and not getattr(self, "_catalog_load_failed", False):
            if self._current_query():
                self._show_banner(self.tr("No results."), kind="info")
            else:
                self._show_banner(self.tr("No apps in the catalog."), kind="info")

    def _filtered_apps(self, query: str) -> list[App]:
        if self._index is None:
            return []
        apps = list(self._catalog_apps) if not query else search(self._index, query)
        if self.config.get("ui.hide_incompatible"):
            host = _host_arch()
            apps = [app for app in apps if _arch_compatible(app, host)]
        return apps

    # ------------------------------------------------------------------ installed list

    _MIN_LIST_ENTRY_LEN = 3

    def _refresh_installed_list(self) -> None:
        """Fetch installed AppImages from daemon and match to catalog."""
        if not self._appimage_backend or not self._appimage_available:
            return

        def on_list(apps: list) -> None:
            self._process_installed_list(apps)

        def on_error(error: AurelisError) -> None:
            self._show_banner(
                self.tr("Failed to list installed apps: {error}").format(error=error.message),
                kind="error",
            )

        self._appimage_backend.list_installed_async(
            {"all": True},
            reply_cb=on_list,
            error_cb=on_error,
        )

    def _process_installed_list(self, apps: list) -> None:
        """Process the list of installed apps from daemon."""
        # Preserve existing origins before clearing
        existing_origins = {app_id: inst.origin for app_id, inst in self._installed_apps.items()}

        self._installed_apps.clear()
        self._installed_by_catalog_id.clear()

        for entry in apps:
            if isinstance(entry, (list, tuple)) and len(entry) >= self._MIN_LIST_ENTRY_LEN:
                app_id, name, version = entry[0], entry[1], entry[2]
                inst = InstalledApp(
                    id=app_id,
                    source=Source.APPIMAGE,
                    name=name,
                    version=version if version else None,
                    managed_name=app_id,
                    path=None,
                    role="primary",
                    sha256=None,
                    update_policy="auto",
                    self_managed=False,
                    origin=existing_origins.get(app_id),
                    locked=False,
                    pending=None,
                    previous=(),
                )
                self._installed_apps[app_id] = inst

        # Match installed to catalog entries using new API
        for inst in self._installed_apps.values():
            self._match_and_update_installed(inst)

        # Refresh installed page if it exists
        if hasattr(self, "_installed"):
            self._installed.set_apps(list(self._installed_apps.values()))
        # Refresh detail only if showing an installed app and not mid-operation
        current = self._detail._app
        if (
            current
            and current.id in self._installed_apps
            and self._detail._current_op_id is None
            and self._detail._state not in ("Installed", "Failed")
        ):
            self._detail.set_app(current, self._installed_apps[current.id].__dict__)

    def _match_and_update_installed(self, inst: InstalledApp) -> None:
        """Match an installed app to catalog and update its state."""
        file_sha256 = inst.sha256
        match = match_installed_to_catalog(inst, self._catalog_apps, file_sha256=file_sha256)

        if match.kind == MatchKind.ORIGIN:
            # Linked via origin - already has correct origin
            if match.catalog_app:
                inst.origin = {"catalog_id": match.catalog_app.id}
                inst.update_policy = "auto"
                if update_available(match.catalog_app, inst):
                    inst.update_available = True
                self._installed_by_catalog_id[match.catalog_app.id] = inst
        elif match.kind == MatchKind.SHA256:
            # Auto-link via sha256 match
            if match.catalog_app:
                origin = build_origin(match.catalog_app)
                inst.origin = origin
                self._appimage_backend.set_origin_async(
                    inst.id,
                    origin,
                    reply_cb=lambda ok: None,
                    error_cb=lambda e: None,
                )
                if update_available(match.catalog_app, inst):
                    inst.update_available = True
                self._installed_by_catalog_id[match.catalog_app.id] = inst
        elif match.kind == MatchKind.APP_ID:
            # Suggest link via app_id match
            if match.catalog_app:
                inst.suggest_link = build_origin(match.catalog_app)
                self._installed_by_catalog_id[match.catalog_app.id] = inst
        elif match.kind == MatchKind.AMBIGUOUS:
            # Ambiguous - no link, show as unmanaged
            pass
        else:  # UNMANAGED
            # No match - unmanaged
            pass

    # ------------------------------------------------------------------ search

    def _on_search_text_changed(self, text: str) -> None:
        self._hide_banner()
        self._search_timer.start()

    def _run_search(self) -> None:
        query = self._current_query()
        apps = self._filtered_apps(query)
        current_widget = self._stack.currentWidget()
        if current_widget == self._explore:
            self._explore.set_apps(apps)
            self._explore.scroll_to_top()
        elif current_widget == self._installed:
            self._installed.set_filter(query)
        if not apps and self._catalog_loaded:
            self._show_banner(self.tr("No results."), kind="info")

    def _current_query(self) -> str:
        return self._search.text().strip()

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
            # Re-match installed apps
            self._refresh_installed_list()

    # ------------------------------------------------------------------ navigation

    def _on_section(self, section: str) -> None:
        self._search.clear()
        self._hide_banner()
        if section == SECTION_EXPLORE:
            self._stack.setCurrentWidget(self._explore)
            self._toolbar.set_title(self.tr("Explore"))
            self._refresh_explore()
            self._sidebar.select_section(SECTION_EXPLORE)
        elif section == SECTION_INSTALLED:
            self._stack.setCurrentWidget(self._installed)
            self._toolbar.set_title(self.tr("Installed"))
            self._installed.set_apps(list(self._installed_apps.values()))
            self._sidebar.select_section(SECTION_INSTALLED)
        elif section == SECTION_UPDATES:
            self._stack.setCurrentWidget(self._updates_placeholder)
            self._toolbar.set_title(self.tr("Updates"))
            self._sidebar.select_section(SECTION_UPDATES)
        elif section == SECTION_SETTINGS:
            dlg = SettingsDialog(self.paths, self.config, self)
            if dlg.exec():
                from aurelis_software.core.config import load

                self.config = load(self.paths)
                self._refresh_explore()
            self._sidebar.select_section(SECTION_EXPLORE)
        else:
            self._stack.setCurrentWidget(self._explore)
            self._show_placeholder(
                section, self.tr("{section} is not available yet.").format(section=section)
            )
            self._sidebar.select_section(SECTION_EXPLORE)

    def _on_selection_changed(self) -> None:
        app = self._explore.current_app()
        if app is None:
            return
        installed = self._installed_apps.get(app.id)
        self._detail.set_app(app, installed.__dict__ if installed else None)
        self._stack.setCurrentWidget(self._detail)
        self._toolbar.set_title(app.name)
        self._hide_banner()
        self._sidebar.select_section(SECTION_EXPLORE)

    def _on_installed_selection(self, app_id: str) -> None:
        # Find the catalog app for this installed app
        inst = self._installed_apps.get(app_id)
        if inst:
            # Try to find matching catalog entry
            catalog_app = next((a for a in self._catalog_apps if a.id == app_id), None)
            if catalog_app:
                self._detail.set_app(catalog_app, inst.__dict__)
                self._stack.setCurrentWidget(self._detail)
                self._toolbar.set_title(catalog_app.name)
                self._hide_banner()
                self._sidebar.select_section(SECTION_INSTALLED)

    # ------------------------------------------------------------------ operation handlers

    def _on_install_requested(self, app_id: str) -> None:
        app = next((a for a in self._catalog_apps if a.id == app_id), None)
        if not app:
            return

        # Pre-checks (section 7.2)
        if not self._appimage_available:
            self._show_banner(self.tr("AppImage service not available"), kind="error")
            return

        # Check free space
        size = app.raw.get("size")
        if size:
            import shutil

            try:
                free = shutil.disk_usage(self.paths.cache_dir).free
            except OSError:
                free = shutil.disk_usage(Path.home()).free
            if free < size * 2:
                self._show_banner(
                    self.tr("Not enough free space. Need {need} MB, have {have} MB").format(
                        need=size * 2 // 1_000_000, have=free // 1_000_000
                    ),
                    kind="error",
                )
                return

        # Check for existing operation
        if any(
            op[1] == "install" and op[0].id == app_id for op in self._active_operations.values()
        ):
            return

        # Download
        self._start_download(app)

    def _start_download(self, app: App) -> None:
        """Download the AppImage to cache."""
        download_url = app.raw.get("download_url")
        sha256 = app.raw.get("sha256")
        size = app.raw.get("size")

        if not download_url:
            self._show_banner(
                self.tr("No download URL for {name}").format(name=app.name), kind="error"
            )
            return

        dest = self.paths.cache_dir / "downloads" / f"{app.id}-{app.version or 'latest'}.AppImage"

        # Check if we need to confirm unverified download
        if not sha256 and self.config.get("downloads.allow_unverified") == "ask":
            dlg = UnverifiedDownloadDialog(app.name, self)
            if dlg.exec() != dlg.Accepted:
                return
            if dlg.dont_ask_again:
                # Store in config
                run_without = self.config.get("wizard.run_without_asking", [])
                run_without.append({"app_id": app.id, "sha256": ""})
                self.config.set("wizard.run_without_asking", run_without)

        from PyQt6.QtNetwork import QNetworkAccessManager

        nam = QNetworkAccessManager()
        downloader = Downloader(nam)

        def on_progress(received: int, total: int) -> None:
            fraction = received / total if total > 0 else None
            self._detail.update_operation_progress(
                f"dl-{app.id}",
                type("Event", (), {"step": "download", "fraction": fraction, "message": ""})(),
            )

        def on_finished(path: Path) -> None:
            # Verify sha256 if present
            if sha256:
                self._detail.update_operation_progress(
                    f"dl-{app.id}",
                    type("Event", (), {"step": "verify", "fraction": None, "message": ""})(),
                )
                import hashlib

                with open(path, "rb") as f:
                    digest = hashlib.sha256(f.read()).hexdigest()
                if digest != sha256:
                    path.unlink(missing_ok=True)
                    self._detail.operation_failed(
                        "Checksum mismatch", f"Expected {sha256}, got {digest}"
                    )
                    show_toast(
                        self.tr("Checksum mismatch for {name}").format(name=app.name), "error", self
                    )
                    return

            # Handoff to daemon
            self._detail.update_operation_progress(
                f"dl-{app.id}",
                type("Event", (), {"step": "handoff", "fraction": None, "message": ""})(),
            )

            # Build origin
            origin = build_origin(app)

            # Call Install
            options = {
                "source_action": "move",
                "conflict": "error",
                "silent": True,
                "origin": origin,
            }
            self._call_install(app, dest, options)

        def on_failed(error: Exception) -> None:
            self._detail.operation_failed(str(error), getattr(error, "details", ""))

        downloader.progress.connect(on_progress)
        downloader.finished.connect(on_finished)
        downloader.failed.connect(on_failed)
        downloader.start(download_url, dest, sha256=sha256, expected_size=size)

    def _call_install(self, app: App, path: Path, options: dict) -> None:
        """Call Install on the daemon."""
        if not self._appimage_backend:
            return

        op_id = f"dl-{app.id}"
        self._detail.start_operation(op_id, "install")
        self._active_operations[op_id] = (app, "install", app.id)

        def on_reply(result: dict) -> None:
            # result contains: app, changed, previous
            self._active_operations.pop(f"dl-{app.id}", None)
            self._detail.operation_finished.emit(
                f"dl-{app.id}", type("Result", (), {"ok": True, "error": None})()
            )

            # After operation_finished sets state to Installed, refresh the installed list
            # but do NOT call set_app again (that would reset state via _update_state)
            def on_list(apps: list) -> None:
                self._process_installed_list(apps)

            def on_error(error: AurelisError) -> None:
                self._show_banner(
                    self.tr("Failed to list installed apps: {error}").format(error=error.message),
                    kind="error",
                )

            self._appimage_backend.list_installed_async(
                {"all": True},
                reply_cb=on_list,
                error_cb=on_error,
            )

        def on_error(error: AurelisError) -> None:
            # Handle ConflictPending
            if isinstance(error, self._get_error_class("ConflictPending")):
                self._handle_conflict(app, path, options, error)
            elif isinstance(error, self._get_error_class("Busy")):
                # Retry once after 1 second
                QTimer.singleShot(1000, lambda: self._call_install(app, path, options))
            else:
                # Clean up cache file
                path.unlink(missing_ok=True)
                error_type = type(error).__name__
                self._detail.operation_failed(str(error), "", error_type)
                self._active_operations.pop(f"dl-{app.id}", None)
                show_toast(
                    self.tr("Install failed: {error}").format(error=error.message), "error", self
                )

        self._appimage_backend.install_async(
            str(path), options, reply_cb=on_reply, error_cb=on_error
        )

    def _handle_conflict(self, app: App, path: Path, options: dict, error: AurelisError) -> None:
        """Show conflict dialog and retry with user's choice."""
        # Set state to Failed so the detail page shows Retry (not Installing)
        self._detail.operation_failed(str(error), getattr(error, "details", ""), "ConflictPending")
        self._active_operations.pop(f"dl-{app.id}", None)

        # Parse conflict payload from error
        payload = getattr(error, "payload", {})
        if isinstance(payload, str):
            import json

            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        old_meta = payload.get("old", {})
        relation = payload.get("relation", old_meta.get("relation", "same"))

        from aurelis_software.ui.conflict_dialog import ConflictInfo

        conflicts = [
            ConflictInfo(
                app_id=old_meta.get("app_id", app.id),
                name=old_meta.get("name", app.name),
                version=old_meta.get("version"),
                relation=relation,
            )
        ]

        dlg = ConflictDialog(app.name, app.version, conflicts, self)
        dlg.choice_made.connect(lambda choice: self._on_conflict_choice(choice, app, path, options))
        dlg.show()

    def _on_conflict_choice(self, choice: str, app: App, path: Path, options: dict) -> None:
        if choice == "cancel":
            path.unlink(missing_ok=True)
            # Reset to NotInstalled (app was not installed before the conflict)
            self._detail._state = "NotInstalled"
            self._detail._error_message = ""
            self._detail._error_details = ""
            self._detail._error_type = ""
            self._detail._rebuild()
            return

        new_options = dict(options)
        new_options["conflict"] = "replace" if choice == "replace" else "keep"
        self._call_install(app, path, new_options)

    def _get_error_class(self, name: str):
        """Get error class by name from core.errors."""
        from aurelis_software.core import errors

        return getattr(errors, name, Exception)

    def _on_update_requested(self, app_id: str) -> None:
        app = next((a for a in self._catalog_apps if a.id == app_id), None)
        inst = self._installed_apps.get(app_id)
        if not app or not inst:
            return

        # Similar to install but with zsync if available
        self._start_update(app, inst)

    def _start_update(self, app: App, inst: InstalledApp) -> None:
        """Start an update operation."""
        # Check for zsync
        zsync_url = app.raw.get("zsync_url")
        installed_path = inst.path

        if zsync_url and installed_path:
            # Try zsync delta update
            self._start_zsync_update(app, inst, zsync_url, installed_path)
        else:
            # Full download
            self._start_download(app)

    def _start_zsync_update(
        self, app: App, inst: InstalledApp, zsync_url: str, installed_path: str
    ) -> None:
        """Run zsync for delta update."""
        import subprocess

        dest = (
            self.paths.cache_dir / "downloads" / f"{app.id}-{app.version or 'latest'}.AppImage.part"
        )

        op_id = f"dl-{app.id}"
        self._detail.start_operation(op_id, "update")
        self._active_operations[op_id] = (app, "update", app.id)

        def run_zsync() -> None:
            try:
                result = subprocess.run(
                    ["zsync", "-i", installed_path, "-o", str(dest), zsync_url],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.returncode == 0 and dest.exists():
                    # Verify sha256
                    sha256 = app.raw.get("sha256")
                    if sha256:
                        import hashlib

                        with open(dest, "rb") as f:
                            digest = hashlib.sha256(f.read()).hexdigest()
                        if digest != sha256:
                            dest.unlink(missing_ok=True)
                            self._detail.operation_failed(
                                "Checksum mismatch", f"Expected {sha256}, got {digest}"
                            )
                            return
                    # Rename and install
                    final = dest.with_suffix("")
                    dest.rename(final)
                    options = {
                        "source_action": "move",
                        "conflict": "replace",
                        "silent": True,
                        "origin": build_origin(app),
                    }
                    self._call_install(app, final, options)
                else:
                    # Fallback to full download
                    self._start_download(app)
            except (subprocess.SubprocessError, OSError, TimeoutError) as e:
                self._detail.operation_failed(str(e), "")

        # Run in thread
        from PyQt6.QtCore import QThread

        worker = QThread()
        worker.run = run_zsync
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_remove_requested(self, app_id: str) -> None:
        inst = self._installed_apps.get(app_id)
        if not inst:
            return

        # Confirmation dialog
        reply = QMessageBox.question(
            self,
            self.tr("Remove {name}?").format(name=inst.name),
            self.tr(
                "This will remove {name} from your Applications. "
                "Your settings and data are kept. The program file is moved to the Trash."
            ).format(name=inst.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        op_id = f"rm-{app_id}"
        self._detail.start_operation(op_id, "remove")
        self._active_operations[op_id] = (inst, "remove", app_id)

        if self._appimage_backend:

            def on_reply(ok: bool) -> None:
                if ok:
                    show_toast(self.tr("{name} removed").format(name=inst.name), "success", self)
                else:
                    show_toast(self.tr("Remove failed"), "error", self)
                self._detail.operation_finished.emit(
                    f"rm-{app_id}", type("Result", (), {"ok": ok, "error": None})()
                )
                self._active_operations.pop(f"rm-{app_id}", None)
                self._refresh_installed_list()

            def on_error(error: AurelisError) -> None:
                self._detail.operation_failed(str(error), "")
                self._active_operations.pop(f"rm-{app_id}", None)

            self._appimage_backend.remove_async(
                inst.id,
                {"file_action": "trash", "silent": True},
                reply_cb=on_reply,
                error_cb=on_error,
            )

    def _on_open_requested(self, app_id: str) -> None:
        """Launch the app via appimage run."""
        import subprocess

        subprocess.Popen(["appimage", "run", app_id], start_new_session=True)

    def _on_show_in_folder(self, app_id: str) -> None:
        """Show the AppImage file in the file manager."""
        inst = self._installed_apps.get(app_id)
        if inst and inst.path:
            import subprocess

            subprocess.Popen(["xdg-open", str(Path(inst.path).parent)], start_new_session=True)

    def _on_revert_requested(self, app_id: str) -> None:
        inst = self._installed_apps.get(app_id)
        if not inst:
            return

        if self._appimage_backend:

            def on_reply(ok: bool) -> None:
                if ok:
                    show_toast(self.tr("Reverted {name}").format(name=inst.name), "success", self)
                self._refresh_installed_list()

            def on_error(error: AurelisError) -> None:
                show_toast(
                    self.tr("Revert failed: {error}").format(error=error.message), "error", self
                )

            self._appimage_backend.revert_async(inst.id, reply_cb=on_reply, error_cb=on_error)

    def _on_cancel_requested(self, op_id: str) -> None:
        # Find the active operation and cancel it
        if op_id in self._active_operations:
            _app, kind, _app_key = self._active_operations[op_id]
            # Cancel the downloader if it's a download operation
            if kind in ("install", "update") and hasattr(self, "_downloader") and self._downloader:
                self._downloader.cancel()
            # Mark operation as cancelled
            self._detail.operation_finished.emit(
                op_id, type("Result", (), {"ok": False, "error": "cancelled"})()
            )

    def _on_set_policy(self, app_id: str, policy: str) -> None:
        inst = self._installed_apps.get(app_id)
        if not inst or not self._appimage_backend:
            return

        def on_reply(ok: bool) -> None:
            if ok:
                inst.update_policy = policy
                show_toast(
                    self.tr("Update policy set to {policy}").format(policy=policy), "success", self
                )
                self._detail.set_app(self._detail._app, inst.__dict__)

            def on_error(error: AurelisError) -> None:
                show_toast(
                    self.tr("Failed to set policy: {error}").format(error=error.message),
                    "error",
                    self,
                )

            self._appimage_backend.set_policy_async(
                inst.id, policy, reply_cb=on_reply, error_cb=on_error
            )

    def _on_set_origin(self, app_id: str, origin: dict | None) -> None:
        inst = self._installed_apps.get(app_id)
        if not inst or not self._appimage_backend:
            return

        def on_reply(ok: bool) -> None:
            if ok:
                inst.origin = origin
                show_toast(self.tr("Catalog link updated"), "success", self)
                self._detail.set_app(self._detail._app, inst.__dict__)

        def on_error(error: AurelisError) -> None:
            show_toast(
                self.tr("Failed to link: {error}").format(error=error.message), "error", self
            )

        self._appimage_backend.set_origin_async(
            inst.id, origin, reply_cb=on_reply, error_cb=on_error
        )

    def _on_link_to_catalog(self, app_id: str) -> None:
        """Handle 'Link to catalog' button for suggested apps."""
        inst = self._installed_apps.get(app_id)
        if not inst or not inst.suggest_link:
            return
        self._on_set_origin(app_id, inst.suggest_link)

    # ------------------------------------------------------------------ banners

    def _show_banner(self, text: str, kind: str = "info") -> None:
        self._hide_banner()
        banner = Banner(text, kind=kind, parent=self._banner)
        self._banner_layout.addWidget(banner)
        self._current_banner = banner

    def _hide_banner(self) -> None:
        banner = getattr(self, "_current_banner", None)
        if banner is not None:
            self._banner_layout.removeWidget(banner)
            banner.deleteLater()
            self._current_banner = None

    def _show_placeholder(self, title: str, text: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)
        t = QLabel(title)
        t.setStyleSheet("font-size: 20px; font-weight: 600; color: #1d1d1f;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(t)
        m = QLabel(text)
        m.setStyleSheet("color: #86868b; font-size: 14px;")
        m.setAlignment(Qt.AlignmentFlag.AlignCenter)
        m.setWordWrap(True)
        layout.addWidget(m)
        return widget

    def _make_placeholder(self, title: str, text: str) -> QWidget:
        return self._show_placeholder(title, text)


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

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet(
            "font-size: 15px; font-weight: 600; color: #1d1d1f; background: transparent;"
        )
        layout.addWidget(self._title_label, stretch=0)

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

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)


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
        updater = DbUpdater(self.paths, self.config, url_fetch)
        result = updater.refresh(force=False)
        self.finished.emit(result)
