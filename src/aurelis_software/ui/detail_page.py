"""DetailPage: app detail view with full state machine (sections 7.1, 10.3, P3.4-P3.6)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from aurelis_software.core.models import App, Source
from aurelis_software.ui.progress_widgets import InlineProgressWidget, show_toast
from aurelis_software.ui.screenshot_carousel import ScreenshotCarousel
from aurelis_software.ui.theme import _CHIP_TEXT_LIGHTNESS, badge_color


def _paragraphs(text: str):
    return [p for p in text.split("\n") if p.strip()]


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: rgba(0,0,0,0.08);")
    line.setFixedHeight(1)
    return line


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    f = QFont(lbl.font())
    f.setPointSizeF(f.pointSizeF() + 1)
    f.setWeight(QFont.Weight.DemiBold)
    lbl.setFont(f)
    lbl.setStyleSheet("color: #1d1d1f;")
    return lbl


class DetailPage(QWidget):
    """Detail page with full button state machine (section 7.1)."""

    # Operation signals
    install_requested = pyqtSignal(str)  # app_id
    update_requested = pyqtSignal(str)  # app_id
    remove_requested = pyqtSignal(str)  # app_id
    open_requested = pyqtSignal(str)  # app_id
    show_in_folder_requested = pyqtSignal(str)  # app_id
    revert_requested = pyqtSignal(str)  # app_id
    set_policy_requested = pyqtSignal(str, str)  # app_id, policy
    set_origin_requested = pyqtSignal(str, dict)  # app_id, origin
    link_to_catalog_requested = pyqtSignal(str)  # app_id

    # Progress signals
    operation_progress = pyqtSignal(str, object)  # op_id, OperationEvent
    operation_finished = pyqtSignal(str, object)  # op_id, OperationResult

    # Operation control
    cancel_requested = pyqtSignal(str)  # op_id

    # UI signals
    app_name_changed = pyqtSignal(str)  # app name for toolbar title

    def __init__(self, icons_dir: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self.icons_dir = icons_dir
        self._app: App | None = None
        self._installed: dict | None = None  # InstalledApp-like dict
        self._flathub_record: dict | None = None  # FlathubIndex record if available
        self._state: str = "NotInstalled"  # matches section 7.1 states
        self._current_op_id: str | None = None
        self._current_op_kind: str | None = None
        self._action_button: QPushButton | None = None
        self._secondary_button: QPushButton | None = None
        self._policy_combo: QComboBox | None = None
        self._revert_button: QPushButton | None = None
        self._show_folder_button: QPushButton | None = None
        self._link_button: QPushButton | None = None
        self._error_message: str = ""
        self._error_details: str = ""
        self._error_type: str = ""

        # Create progress widget once (no explicit parent)
        self._progress_widget = InlineProgressWidget(
            kind="install",
            cancellable=True,
        )
        self._progress_widget.hide()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: white; }")

        # Connect operation_finished signal to update_operation_finished handler
        self.operation_finished.connect(self.update_operation_finished)

        self._container = QWidget()
        self._container.setStyleSheet("background: white;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(32, 28, 32, 28)
        self._layout.setSpacing(0)

        scroll.setWidget(self._container)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    # ------------------------------------------------------------------ public API

    def set_installed(self, record) -> None:
        """Set the installed record (InstalledApp or None) without rebuilding.

        Call before emitting operation_finished so the state machine sees the
        correct installed data when it recomputes on the finished signal.
        """
        self._installed = record.__dict__ if record is not None else None

    @property
    def current_app(self) -> App | None:
        """The app currently shown in the detail page."""
        return self._app

    @property
    def current_op_id(self) -> str | None:
        """The op_id of the currently running operation, or None."""
        return self._current_op_id

    def set_app(
        self, app: App | None, installed: dict | None = None, flathub_record: dict | None = None
    ) -> None:
        """Set the app and optionally its installed state.

        Args:
            app: Catalog App entry
            installed: Dict with keys like id, version, managed_name, path,
                      update_policy, self_managed, origin, previous, locked, pending
            flathub_record: FlathubIndex record dict if the same app id is on Flathub
        """
        self._app = app
        self._installed = installed
        self._flathub_record = flathub_record
        # Clear Failed state so _update_state recomputes from installed dict
        if self._state == "Failed" and self._current_op_id is None:
            self._state = "NotInstalled"
            self._error_message = ""
            self._error_details = ""
            self._error_type = ""
        self._update_state()
        self._rebuild()
        if app is not None:
            self.app_name_changed.emit(app.name)

    def clear(self) -> None:
        self._app = None
        self._installed = None
        self._rebuild()

    def update_operation_progress(self, op_id: str, event) -> None:
        """Update progress from a QtOperation event."""
        if op_id != self._current_op_id:
            return
        if self._progress_widget:
            self._progress_widget.update_event(event)

    def update_operation_finished(self, op_id: str, result) -> None:
        """Handle operation completion."""
        if op_id != self._current_op_id and self._state != "Failed":
            return
        if self._progress_widget:
            if result.ok:
                self._progress_widget.update_event(
                    type("Event", (), {"step": "finish", "fraction": 1.0, "message": ""})()
                )
                if self._app:
                    action = self._state
                    if action == "Installing":
                        show_toast(
                            self.tr("{name} installed.").format(name=self._app.name),
                            "success",
                            self,
                        )
                        # Mark as installed so _installed_state() returns "Installed"
                        if self._installed is None:
                            self._installed = {
                                "id": self._app.id,
                                "origin": {"catalog_id": self._app.id},
                            }
                    elif action == "Updating":
                        show_toast(
                            self.tr("{name} updated.").format(name=self._app.name), "success", self
                        )
                        if self._installed is None:
                            self._installed = {
                                "id": self._app.id,
                                "origin": {"catalog_id": self._app.id},
                            }
                    elif action == "Removing":
                        show_toast(
                            self.tr("{name} removed.").format(name=self._app.name), "success", self
                        )
                        self._installed = None
            else:
                self._progress_widget.update_event(
                    type(
                        "Event",
                        (),
                        {"step": "fail", "fraction": 1.0, "message": result.error or "Failed"},
                    )()
                )
                show_toast(
                    self.tr("Operation failed: {error}").format(error=result.error), "error", self
                )
                self._error_message = result.error or "Failed"
                self._error_details = ""
                self._error_type = ""
                self._state = "Failed"
            # Clear current operation tracking
            self._current_op_id = None
            self._current_op_kind = None
            from PyQt6.QtCore import QTimer

            QTimer.singleShot(1500, self._clear_progress)
        self._update_state()
        self._rebuild()

    def _clear_progress(self) -> None:
        if self._progress_widget:
            self._progress_widget.hide()

    # ------------------------------------------------------------------ state machine

    def _update_state(self) -> None:
        """Determine button state per section 7.1."""
        if self._app is None:
            self._state = "NotInstalled"
            return

        # Check for active operation first
        if self._current_op_id is not None:
            self._state = self._operation_state()
            return

        # Failed state is preserved until set_app resets it
        if self._state == "Failed":
            return

        self._state = self._installed_state()

    def _operation_state(self) -> str:
        """Return state for active operation."""
        return {
            "install": "Installing",
            "update": "Updating",
            "remove": "Removing",
        }.get(self._current_op_kind, "NotInstalled")

    def _installed_state(self) -> str:
        """Return state based on installed status."""
        if self._installed is None:
            return self._not_installed_state()

        if self._installed.get("locked"):
            return "Locked"
        if self._installed.get("pending"):
            return f"Pending{self._installed['pending'].capitalize()}"
        if self._installed.get("update_available"):
            return "UpdateAvailable"
        if self._installed.get("origin") is None:
            return "Unmanaged"
        return "Installed"

    def _not_installed_state(self) -> str:
        """Return state when app is not installed."""
        arch = self._app.raw.get("arch")
        host = self._host_arch()
        if arch is not None and str(arch) != host:
            return "Incompatible"
        return "NotInstalled"

    def _host_arch(self) -> str:
        import platform

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

    # ------------------------------------------------------------------ building

    def _rebuild(self) -> None:
        self._clear_layout()
        app = self._app
        if app is None:
            empty = QLabel(self.tr("Select an app to see its details."))
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #86868b; font-size: 15px;")
            self._layout.addWidget(empty)
            self._layout.addStretch()
            return

        # Show error state if failed
        if self._state == "Failed":
            self._show_error_state()
            self._layout.addSpacing(20)

        self._header(app)
        self._layout.addSpacing(20)
        self._trust_line(app)
        self._screenshot_carousel(app)
        self._description(app)
        self._links(app)
        self._also_available_as(app)

        # Installed-only sections
        if self._installed:
            self._layout.addSpacing(20)
            self._installed_actions(app)
            if self._installed.get("previous"):
                self._layout.addSpacing(16)
                self._previous_versions(app)

        self._layout.addStretch()

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Skip the progress widget - it's reused across rebuilds
                if widget is not self._progress_widget:
                    widget.deleteLater()
            else:
                layout = item.layout()
                if layout is not None:
                    self._clear_layout_recursive(layout)

    def _clear_layout_recursive(self, layout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            w = child.widget()
            if w is not None:
                w.deleteLater()
            else:
                child_layout = child.layout()
                if child_layout is not None:
                    self._clear_layout_recursive(child_layout)

    def _show_error_state(self) -> None:
        """Display error title, message, and details in the UI."""
        # Error title based on error type (strip "Error" suffix from class names if present)
        error_type = self._error_type
        # Handle class names like "DiskFullError" -> "DiskFull", "NetworkErrorError" -> "NetworkError"
        # but don't strip from alias names like "DiskFull", "NetworkError"
        if error_type.endswith("Error"):
            # Check if stripping "Error" gives a known key
            stripped = error_type[:-5]
            if stripped in ("NetworkError", "ChecksumMismatch", "DiskFull", "DaemonUnavailable"):
                error_type = stripped
        title_map = {
            "NetworkError": self.tr("Download failed"),
            "ChecksumMismatch": self.tr("Checksum mismatch"),
            "DiskFull": self.tr("Not enough disk space"),
            "DaemonUnavailable": self.tr("Background service unavailable"),
        }
        error_title = title_map.get(error_type, self.tr("Operation failed"))

        title_label = QLabel(error_title)
        title_font = QFont(title_label.font())
        title_font.setPointSizeF(title_font.pointSizeF() + 4)
        title_font.setWeight(QFont.Weight.DemiBold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #b71c1c;")
        title_label.setWordWrap(True)
        self._layout.addWidget(title_label)

        # Error message
        if self._error_message:
            msg_label = QLabel(self._error_message)
            msg_label.setWordWrap(True)
            msg_label.setStyleSheet("color: #1d1d1f; font-size: 14px;")
            self._layout.addWidget(msg_label)

        # Error details
        if self._error_details:
            details_label = QLabel(self._error_details)
            details_label.setWordWrap(True)
            details_label.setStyleSheet("color: #86868b; font-size: 12px; font-family: monospace;")
            self._layout.addWidget(details_label)

        self._layout.addSpacing(16)
        self._layout.addWidget(_divider())
        self._layout.addSpacing(16)

    def _header(self, app: App) -> None:
        # Use a vertical layout for the header so buttons wrap on narrow screens
        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(12)
        header_vbox.setContentsMargins(0, 0, 0, 0)

        # Top row: icon + info
        row = QHBoxLayout()
        row.setSpacing(20)
        row.setContentsMargins(0, 0, 0, 0)

        # Icon
        icon_name = (
            app.raw.get("icon", {}).get("name") if isinstance(app.raw.get("icon"), dict) else None
        )
        from aurelis_software.ui.icons import app_icon

        icon_label = QLabel()
        icon_label.setPixmap(app_icon(icon_name, self.icons_dir).pixmap(QSize(96, 96)))
        icon_label.setFixedSize(QSize(96, 96))
        icon_label.setStyleSheet("border-radius: 20px; background: #f5f5f7; padding: 4px;")
        row.addWidget(icon_label, stretch=0, alignment=Qt.AlignmentFlag.AlignTop)

        # Info column
        info = QVBoxLayout()
        info.setSpacing(4)
        info.setContentsMargins(0, 0, 0, 0)

        name = QLabel(app.name)
        name_font = QFont(name.font())
        name_font.setPointSizeF(name_font.pointSizeF() + 8)
        name_font.setWeight(QFont.Weight.Bold)
        name.setFont(name_font)
        name.setWordWrap(True)
        name.setStyleSheet("color: #1d1d1f;")
        info.addWidget(name)

        if app.summary:
            summary = QLabel(app.summary)
            summary.setWordWrap(True)
            summary.setStyleSheet("color: #86868b; font-size: 14px;")
            info.addWidget(summary)

        # Meta chips row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        meta_row.setContentsMargins(0, 6, 0, 0)
        self._add_meta_chip(meta_row, str(app.source), "update")
        if app.version:
            self._add_meta_chip(meta_row, app.version, "installed")
        size = app.raw.get("size")
        if size is not None:
            self._add_meta_chip(meta_row, f"{size // 1_000_000} MB", "neutral")
        meta_row.addStretch()
        info.addLayout(meta_row)

        row.addLayout(info, stretch=1)

        header_vbox.addLayout(row)

        # Buttons row (separate so it wraps on narrow screens)
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(12)
        buttons_row.setContentsMargins(0, 0, 0, 0)
        # No stretch - buttons left-aligned to avoid clipping at narrow widths

        self._action_button = None
        self._secondary_button = None

        # Configure existing progress widget (recreate if it was cleared)
        if self._progress_widget is None:
            self._progress_widget = InlineProgressWidget(
                kind="install",
                cancellable=True,
            )
        self._progress_widget.set_cancellable(self._state in ("Installing", "Updating"))
        kind = (
            self._state.lower()
            if self._state in ("Installing", "Updating", "Removing")
            else "install"
        )
        self._progress_widget._kind = kind
        self._progress_widget.hide()

        config = self._button_config_for_state()
        self._action_button = self._make_button(**config["primary"])
        if config.get("secondary"):
            self._secondary_button = self._make_button(**config["secondary"])
        if config.get("extra"):
            for extra in config["extra"]:
                btn = self._make_button(**extra)
                buttons_row.addWidget(btn)

        if self._action_button:
            buttons_row.addWidget(self._action_button)
        if self._secondary_button:
            buttons_row.addWidget(self._secondary_button)

        header_vbox.addLayout(buttons_row)

        self._layout.addLayout(header_vbox)

        # Add progress widget after header
        self._layout.addWidget(self._progress_widget)

    def _button_config_for_state(self) -> dict:
        """Return button configuration for current state."""
        arch = self._host_arch()
        common = {"enabled": True, "style": "filled"}

        configs = {
            "NotInstalled": {
                "primary": {
                    "text": self.tr("Install"),
                    "color": "#0071e3",
                    "callback": self._on_install_clicked,
                    **common,
                }
            },
            "Incompatible": {
                "primary": {
                    "text": self.tr("Not available for {arch}").format(arch=arch),
                    "color": "#d1d1d6",
                    "callback": None,
                    "enabled": False,
                    "style": "filled",
                }
            },
            "Installing": {
                "primary": {
                    "text": self.tr("Cancel"),
                    "color": "#ff3b30",
                    "callback": self._on_cancel_clicked,
                    "enabled": True,
                    "style": "filled",
                }
            },
            "Installed": {
                "primary": {
                    "text": self.tr("Open"),
                    "color": "#0071e3",
                    "callback": self._on_open_clicked,
                    **common,
                },
                "secondary": {
                    "text": self.tr("Remove"),
                    "color": "#ff3b30",
                    "callback": self._on_remove_clicked,
                    **common,
                    "style": "outline",
                },
            },
            "UpdateAvailable": {
                "primary": {
                    "text": self.tr("Update"),
                    "color": "#34c759",
                    "callback": self._on_update_clicked,
                    **common,
                },
                "secondary": {
                    "text": self.tr("Open"),
                    "color": "#0071e3",
                    "callback": self._on_open_clicked,
                    **common,
                },
                "extra": [
                    {
                        "text": self.tr("Remove"),
                        "color": "#ff3b30",
                        "callback": self._on_remove_clicked,
                        **common,
                        "style": "outline",
                    }
                ],
            },
            "Updating": {
                "primary": {
                    "text": self.tr("Updating…"),
                    "color": "#d1d1d6",
                    "callback": None,
                    "enabled": False,
                    "style": "filled",
                }
            },
            "Removing": {
                "primary": {
                    "text": self.tr("Removing…"),
                    "color": "#d1d1d6",
                    "callback": None,
                    "enabled": False,
                    "style": "filled",
                }
            },
            "Failed": {
                "primary": {
                    "text": self.tr("Retry"),
                    "color": "#0071e3",
                    "callback": self._on_retry_clicked,
                    **common,
                },
                "secondary": {
                    "text": self.tr("Details"),
                    "color": "#86868b",
                    "callback": self._on_details_clicked,
                    **common,
                    "style": "outline",
                },
            },
            "Locked": {
                "primary": {
                    "text": self.tr("Part of the system"),
                    "color": "#d1d1d6",
                    "callback": None,
                    "enabled": False,
                    "style": "filled",
                }
            },
            "PendingInstall": {
                "primary": {
                    "text": self.tr("Will be installed after restart"),
                    "color": "#d1d1d6",
                    "callback": None,
                    "enabled": False,
                    "style": "filled",
                },
                "secondary": {
                    "text": self.tr("Undo"),
                    "color": "#0071e3",
                    "callback": self._on_undo_pending_clicked,
                    **common,
                    "style": "outline",
                },
            },
            "PendingRemove": {
                "primary": {
                    "text": self.tr("Will be removed after restart"),
                    "color": "#d1d1d6",
                    "callback": None,
                    "enabled": False,
                    "style": "filled",
                },
                "secondary": {
                    "text": self.tr("Undo"),
                    "color": "#0071e3",
                    "callback": self._on_undo_pending_clicked,
                    **common,
                    "style": "outline",
                },
            },
            "Unmanaged": {
                "primary": {
                    "text": self.tr("Open"),
                    "color": "#0071e3",
                    "callback": self._on_open_clicked,
                    **common,
                },
                "secondary": {
                    "text": self.tr("Remove"),
                    "color": "#ff3b30",
                    "callback": self._on_remove_clicked,
                    **common,
                    "style": "outline",
                },
                "extra": [
                    {
                        "text": self.tr("Link to catalog"),
                        "color": "#0071e3",
                        "callback": self._on_link_catalog_clicked,
                        **common,
                        "style": "outline",
                    }
                ],
            },
        }

        state_key = self._state
        if self._state.startswith("Pending"):
            state_key = "PendingInstall" if "Install" in self._state else "PendingRemove"

        return configs.get(state_key, configs["NotInstalled"])

    def _make_button(
        self, text: str, color: str, callback, *, enabled: bool = True, style: str = "filled"
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setAccessibleName(text)
        btn.setEnabled(enabled)
        btn.setMinimumSize(80, 36)
        btn.setMaximumWidth(200)
        btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        if style == "filled":
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background: {color}; color: white; border: none;"
                f"  border-radius: 8px; font-size: 13px; font-weight: 600;"
                f"}}"
                f"QPushButton:disabled {{"
                f"  background: #d1d1d6; color: #86868b;"
                f"}}"
                f"QPushButton:hover:!disabled {{ background: {color}dd; }}"
            )
        else:  # outline
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background: transparent; color: {color}; border: 1px solid {color};"
                f"  border-radius: 8px; font-size: 13px; font-weight: 600;"
                f"}}"
                f"QPushButton:disabled {{"
                f"  color: #d1d1d6; border-color: #d1d1d6;"
                f"}}"
                f"QPushButton:hover:!disabled {{ background: {color}22; }}"
            )
        if callback:
            btn.clicked.connect(callback)
        return btn

    def _make_remove_button(self, after_button: QPushButton) -> QPushButton:
        """Add a remove button to the layout."""
        btn = self._make_button(
            self.tr("Remove"), "#ff3b30", self._on_remove_clicked, style="outline"
        )
        self._layout.insertWidget(self._layout.indexOf(after_button) + 1, btn)
        return btn

    def _add_meta_chip(self, layout: QHBoxLayout, text: str, kind: str) -> None:
        chip = QLabel(text)
        color = badge_color(kind)
        lum = color.lightness()
        tc = "#ffffff" if lum < _CHIP_TEXT_LIGHTNESS else "#1a1a1a"
        chip.setStyleSheet(
            f"background-color: {color.name()}; color: {tc}; "
            "padding: 2px 10px; border-radius: 10px; font-size: 12px; font-weight: 500;"
        )
        chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        layout.addWidget(chip)

    # ------------------------------------------------------------------ button handlers

    def _on_install_clicked(self) -> None:
        if self._app:
            self.install_requested.emit(self._app.id)

    def _on_update_clicked(self) -> None:
        if self._app:
            self.update_requested.emit(self._app.id)

    def _on_remove_clicked(self) -> None:
        if self._app:
            self.remove_requested.emit(self._app.id)

    def _on_open_clicked(self) -> None:
        if self._installed:
            self.open_requested.emit(self._installed.get("id", ""))

    def _on_retry_clicked(self) -> None:
        if self._state == "Failed" and self._app:
            self.install_requested.emit(self._app.id)

    def _on_cancel_clicked(self) -> None:
        if self._current_op_id:
            self.cancel_requested.emit(self._current_op_id)

    def _on_details_clicked(self) -> None:
        # Emit signal with error details
        pass

    def _on_undo_pending_clicked(self) -> None:
        # Undo a pending pkg change
        pass

    def _on_link_catalog_clicked(self) -> None:
        if self._app and self._installed:
            self.link_to_catalog_requested.emit(self._app.id)

    # ------------------------------------------------------------------ trust line

    def _trust_line(self, app: App) -> None:
        if app.source != Source.APPIMAGE:
            return
        raw = app.raw or {}
        repo = raw.get("repo")
        developer = raw.get("developer")
        sha256 = raw.get("sha256")
        license_val = raw.get("license")

        has_content = any([repo, developer, sha256 is not None, license_val])
        if not has_content:
            note = QLabel(self.tr("No checksum available."))
            note.setStyleSheet("color: #86868b; font-size: 13px;")
            self._layout.addWidget(note)
            self._layout.addSpacing(16)
            self._layout.addWidget(_divider())
            self._layout.addSpacing(16)
            return

        box = QVBoxLayout()
        box.setSpacing(6)
        box.setContentsMargins(0, 0, 0, 0)

        if repo:
            owner = repo.split("/", 1)[0]
            line = QLabel(self.tr("Packaged by <b>{owner}</b> on GitHub").format(owner=owner))
            line.setTextFormat(Qt.TextFormat.RichText)
            line.setOpenExternalLinks(True)
            line.setWordWrap(True)
            line.setStyleSheet("color: #1d1d1f; font-size: 13px;")
            box.addWidget(line)

        if developer:
            dev = QLabel(self.tr("Developer: {dev}").format(dev=developer))
            dev.setWordWrap(True)
            dev.setStyleSheet("color: #86868b; font-size: 13px;")
            box.addWidget(dev)

        if license_val:
            is_proprietary = str(license_val).startswith("LicenseRef-proprietary")
            label = "Proprietary" if is_proprietary else str(license_val)
            chip = QLabel(label)
            kind = "proprietary" if is_proprietary else "neutral"
            color = badge_color(kind)
            lum = color.lightness()
            tc = "#ffffff" if lum < _CHIP_TEXT_LIGHTNESS else "#1a1a1a"
            chip.setStyleSheet(
                f"background-color: {color.name()}; color: {tc}; "
                "padding: 2px 8px; border-radius: 10px; font-size: 12px;"
            )
            chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
            box.addWidget(chip)

        # In error state, don't show "Checksum verified" (may be misleading)
        if sha256 and self._state != "Failed":
            note = QLabel(self.tr("Checksum verified on install."))
            note.setStyleSheet("color: #34c759; font-size: 13px;")
        else:
            note = QLabel(self.tr("No checksum available."))
            note.setStyleSheet("color: #86868b; font-size: 13px;")
        note.setWordWrap(True)
        box.addWidget(note)

        self._layout.addLayout(box)
        self._layout.addSpacing(16)
        self._layout.addWidget(_divider())
        self._layout.addSpacing(16)

    # ------------------------------------------------------------------ screenshot carousel

    def _screenshot_carousel(self, app: App) -> None:
        screenshots = app.raw.get("screenshots") or []
        if not screenshots:
            return
        carousel = ScreenshotCarousel(screenshots, parent=self)
        self._layout.addWidget(carousel)
        self._layout.addSpacing(16)
        self._layout.addWidget(_divider())
        self._layout.addSpacing(16)

    # ------------------------------------------------------------------ description

    def _description(self, app: App) -> None:
        description = app.raw.get("description") or ""
        paragraphs = _paragraphs(description)
        if not paragraphs:
            return
        self._layout.addWidget(_section_title(self.tr("Description")))
        self._layout.addSpacing(8)
        for para in paragraphs:
            label = QLabel(para)
            label.setWordWrap(True)
            label.setStyleSheet("color: #1d1d1f; font-size: 14px; line-height: 1.5;")
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
            self._layout.addWidget(label)
            self._layout.addSpacing(4)
        self._layout.addSpacing(12)
        self._layout.addWidget(_divider())
        self._layout.addSpacing(16)

    # ------------------------------------------------------------------ links

    def _links(self, app: App) -> None:
        urls = app.raw.get("urls") or {}
        if not isinstance(urls, dict) or not urls:
            return
        self._layout.addWidget(_section_title(self.tr("Links")))
        self._layout.addSpacing(8)
        for key, url in urls.items():
            if not isinstance(url, str) or not url.startswith("https://"):
                continue
            label_text = key.replace("-", " ").replace("_", " ").title()
            link = QLabel(f'<a href="{url}" style="color:#0071e3;">{label_text}</a>')
            link.setTextFormat(Qt.TextFormat.RichText)
            link.setOpenExternalLinks(True)
            link.setWordWrap(True)
            link.setStyleSheet("font-size: 14px;")
            self._layout.addWidget(link)
        self._layout.addSpacing(12)
        self._layout.addWidget(_divider())
        self._layout.addSpacing(16)

    # ------------------------------------------------------------------ also available as

    def _also_available_as(self, app: App) -> None:
        """Show 'Also on Flathub' button when the same app id exists in the Flathub index (R12.3).

        For AppImage source apps, always shows the section.  When ``_flathub_record`` is set,
        shows the "Also on Flathub" action button; otherwise shows a placeholder explaining that
        other packaging formats may also offer this app.
        """
        # Only show this section for AppImage apps.
        if app.source != Source.APPIMAGE:
            return
        flathub = self._flathub_record
        self._layout.addWidget(_section_title(self.tr("Also available as")))
        self._layout.addSpacing(8)
        if flathub:
            row = QHBoxLayout()
            row.setSpacing(10)
            row.setContentsMargins(0, 0, 0, 0)
            flatpak_name = flathub.get("name") or app.id
            label = QLabel(self.tr("This app is also available as a Flatpak on Flathub."))
            label.setWordWrap(True)
            label.setStyleSheet("color: #1d1d1f; font-size: 13px;")
            row.addWidget(label, stretch=1)
            btn = QPushButton(self.tr("Also on Flathub"))
            btn.setAccessibleName(self.tr("View {name} on Flathub").format(name=flatpak_name))
            btn.setFixedHeight(32)
            btn.setStyleSheet(
                "QPushButton {"
                "  background: transparent; color: #0071e3; border: 1px solid #0071e3;"
                "  border-radius: 8px; font-size: 13px; font-weight: 600; padding: 0 14px;"
                "}"
                "QPushButton:hover { background: rgba(0,113,227,0.08); }"
            )
            row.addWidget(btn)
            self._layout.addLayout(row)
        else:
            placeholder = QLabel(self.tr("(other sources with the same id appear here)"))
            placeholder.setWordWrap(True)
            placeholder.setStyleSheet("color: #86868b; font-size: 13px; font-style: italic;")
            self._layout.addWidget(placeholder)
        self._layout.addSpacing(12)
        self._layout.addWidget(_divider())
        self._layout.addSpacing(16)

    # ------------------------------------------------------------------ installed actions

    def _installed_actions(self, app: App) -> None:
        """Show policy selector (AppImages only), revert button for installed apps."""
        self._layout.addWidget(_section_title(self.tr("Manage")))
        self._layout.addSpacing(8)

        # Policy selector — only for installed AppImages (R6.1)
        if app.source == Source.APPIMAGE and self._installed:
            policy_row = QHBoxLayout()
            policy_row.setSpacing(8)
            policy_row.setContentsMargins(0, 0, 0, 0)

            policy_label = QLabel(self.tr("Update policy:"))
            policy_label.setStyleSheet("color: #1d1d1f; font-size: 13px;")
            policy_row.addWidget(policy_label)

            self._policy_combo = QComboBox()
            self._policy_combo.setAccessibleName(self.tr("Update policy"))
            # Internal values map to display labels
            _policy_items = [
                ("auto", self.tr("Automatic")),
                ("manual", self.tr("Ask me")),
                ("pinned", self.tr("Pinned")),
            ]
            for value, label in _policy_items:
                self._policy_combo.addItem(label, userData=value)

            current_policy = self._installed.get("update_policy", "auto")
            for i in range(self._policy_combo.count()):
                if self._policy_combo.itemData(i) == current_policy:
                    self._policy_combo.setCurrentIndex(i)
                    break

            self._policy_combo.currentIndexChanged.connect(self._on_policy_combo_changed)
            policy_row.addWidget(self._policy_combo)
            policy_row.addStretch()
            self._layout.addLayout(policy_row)
        else:
            self._policy_combo = None

        # Revert button
        if self._installed and self._installed.get("previous"):
            self._revert_button = self._make_button(
                self.tr("Revert to previous version"),
                "#af52de",
                self._on_revert_clicked,
                style="outline",
            )
            self._layout.addWidget(self._revert_button)

        # Show in folder
        if self._installed and self._installed.get("path"):
            self._show_folder_button = self._make_button(
                self.tr("Show in folder"), "#86868b", self._on_show_folder_clicked, style="outline"
            )
            self._layout.addWidget(self._show_folder_button)

        self._layout.addSpacing(12)
        self._layout.addWidget(_divider())
        self._layout.addSpacing(16)

    def _on_policy_combo_changed(self, index: int) -> None:
        """Emit set_policy_requested when the combo selection changes."""
        if self._installed and self._policy_combo is not None:
            new_policy = self._policy_combo.itemData(index)
            if new_policy and new_policy != self._installed.get("update_policy", "auto"):
                self.set_policy_requested.emit(self._installed["id"], new_policy)

    def _on_revert_clicked(self) -> None:
        if self._installed:
            self.revert_requested.emit(self._installed["id"])

    def _on_show_folder_clicked(self) -> None:
        if self._installed:
            self.show_in_folder_requested.emit(self._installed["id"])

    # ------------------------------------------------------------------ previous versions

    def _previous_versions(self, app: App) -> None:
        self._layout.addWidget(_section_title(self.tr("Previous versions")))
        self._layout.addSpacing(8)
        previous = self._installed.get("previous", []) if self._installed else []
        for prev in previous:
            row = QHBoxLayout()
            row.setSpacing(8)
            ver = prev.get("version", "?")
            ver_label = QLabel(self.tr("Version {version}").format(version=ver))
            ver_label.setStyleSheet("color: #1d1d1f; font-size: 13px;")
            row.addWidget(ver_label)
            row.addStretch()
            remove_btn = self._make_button(
                self.tr("Remove old version"),
                "#ff3b30",
                lambda _, p=prev: self._on_remove_previous(p),
                style="outline",
            )
            remove_btn.setFixedWidth(140)
            row.addWidget(remove_btn)
            self._layout.addLayout(row)
        self._layout.addSpacing(12)
        self._layout.addWidget(_divider())
        self._layout.addSpacing(16)

    def _on_remove_previous(self, prev: dict) -> None:
        # TODO: Implement revert/remove of previous version
        pass

    def start_operation(self, op_id: str, kind: str) -> None:
        """Called when an operation starts for this app."""
        self._current_op_id = op_id
        self._current_op_kind = kind
        # Reset from Failed state when retrying
        if self._state == "Failed":
            self._state = "NotInstalled"
            self._error_message = ""
            self._error_details = ""
            self._error_type = ""
        if self._progress_widget:
            self._progress_widget.set_cancellable(kind in ("install", "update"))
            self._progress_widget.show()
        self._update_state()
        self._rebuild()

    def operation_failed(self, error: str, details: str = "", error_type: str = "") -> None:
        """Handle operation failure with error details."""
        self._state = "Failed"
        self._error_message = error
        self._error_details = details
        self._error_type = error_type
        self._current_op_id = None
        self._current_op_kind = None
        self._rebuild()

    def reset_to_idle(self) -> None:
        """Reset to NotInstalled (or installed state) after a cancelled conflict dialog."""
        self._current_op_id = None
        self._current_op_kind = None
        self._error_message = ""
        self._error_details = ""
        self._error_type = ""
        self._update_state()
        self._rebuild()
