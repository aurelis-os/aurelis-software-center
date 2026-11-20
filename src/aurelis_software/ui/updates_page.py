"""UpdatesPage: available updates grouped by source (section 10.6, P4.4).

Lists available updates grouped by source. Each row has a checkbox, icon,
name, version arrow, source badge, an inline progress bar (hidden until an
operation is running) and a per-row **Update** button. A top-level
**Update all** button runs only ``auto``-policy rows in FIFO order; on
completion a summary dialog lists per-app success/failure/skipped.

Pacman rows carry an "(applies after restart)" note (R5.4).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from aurelis_software.core.models import Source, UpdateInfo
from aurelis_software.core.versions import eligible_for_update_all
from aurelis_software.ui.icons import app_icon
from aurelis_software.ui.theme import _CHIP_TEXT_LIGHTNESS, badge_color

if TYPE_CHECKING:
    from aurelis_software.backends.base import OperationEvent
    from aurelis_software.core.models import InstalledApp

# Sources are rendered in this top-to-bottom order.
_SOURCE_ORDER: list[Source] = [Source.APPIMAGE, Source.FLATPAK, Source.PACMAN]
_SOURCE_LABELS: dict[Source, str] = {
    Source.APPIMAGE: "AppImage",
    Source.FLATPAK: "Flathub",
    Source.PACMAN: "Arch packages",
}
_PACMAN_RESTART_NOTE = "(applies after restart)"

_ROW_STYLE = """
QFrame#UpdateRow {
    background: white;
    border-bottom: 1px solid rgba(0,0,0,0.06);
}
QFrame#UpdateRow:hover {
    background: #fafafa;
}
"""


def _id_of(app_key: str) -> str:
    """Extract the id from an app_key of the form '<source>:<id>'."""
    return app_key.split(":", 1)[1] if ":" in app_key else app_key


def _source_of(app_key: str) -> Source:
    """Extract the Source from an app_key of the form '<source>:<id>'."""
    head = app_key.split(":", 1)[0]
    try:
        return Source(head)
    except ValueError:
        return Source.APPIMAGE


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: rgba(0,0,0,0.06);")
    line.setFixedHeight(1)
    return line


def _source_badge(source: Source) -> QLabel:
    badge = QLabel(_SOURCE_LABELS.get(source, str(source)))
    color = badge_color("neutral")
    tc = "#ffffff" if color.lightness() < _CHIP_TEXT_LIGHTNESS else "#1a1a1a"
    badge.setStyleSheet(
        f"background-color: {color.name()}; color: {tc}; "
        "padding: 2px 10px; border-radius: 10px; font-size: 11px; font-weight: 500;"
    )
    badge.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
    badge.setAccessibleName(f"Source {badge.text()}")
    return badge


def _section_header(text: str) -> QLabel:
    header = QLabel(text)
    font = QFont(header.font())
    font.setPointSizeF(font.pointSizeF() + 1)
    font.setWeight(QFont.Weight.DemiBold)
    header.setFont(font)
    header.setStyleSheet("color: #1d1d1f; padding: 14px 4px 6px 4px;")
    return header


class _UpdateRow(QFrame):
    """A single update row: checkbox, icon, name, version arrow, badge, progress, button."""

    update_clicked = pyqtSignal(str)  # app_id

    def __init__(
        self,
        info: UpdateInfo,
        installed: InstalledApp | None,
        icons_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("UpdateRow")
        self.setStyleSheet(_ROW_STYLE)
        self.app_id = _id_of(info.app_key)
        self.source = _source_of(info.app_key)
        self._installed = installed
        self.icons_dir = icons_dir
        self._finished = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # Checkbox (selects the row for Update all)
        self._checkbox = QCheckBox()
        self._checkbox.setChecked(True)
        self._checkbox.setAccessibleName(f"Select {self.app_id} for update")
        layout.addWidget(self._checkbox)

        # Icon
        icon_name: str | None = None
        if installed is not None and installed.origin:
            icon_name = installed.origin.get("icon")
        self._icon_label = QLabel()
        self._icon_label.setPixmap(app_icon(icon_name, icons_dir).pixmap(QSize(32, 32)))
        self._icon_label.setFixedSize(QSize(32, 32))
        layout.addWidget(self._icon_label)

        # Name + version arrow
        info_box = QVBoxLayout()
        info_box.setSpacing(2)
        info_box.setContentsMargins(0, 0, 0, 0)

        name = installed.name if installed is not None else self.app_id
        self._name_label = QLabel(name)
        self._name_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #1d1d1f;")
        self._name_label.setAccessibleName(name)
        info_box.addWidget(self._name_label)

        version_text = self._version_text(info, installed)
        self._version_label = QLabel(version_text)
        self._version_label.setStyleSheet("color: #86868b; font-size: 12px;")
        self._version_label.setAccessibleName(version_text)
        info_box.addWidget(self._version_label)
        layout.addLayout(info_box, stretch=1)

        # Source badge
        layout.addWidget(_source_badge(self.source))

        # Inline progress bar (hidden until an operation is running)
        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
        self._progress.setFixedWidth(120)
        self._progress.setAccessibleName(f"Progress for {name}")
        self._progress.hide()
        layout.addWidget(self._progress)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #86868b; font-size: 11px;")
        self._status_label.setFixedWidth(96)
        self._status_label.hide()
        layout.addWidget(self._status_label)

        # Update button
        self._update_btn = QPushButton("Update")
        self._update_btn.setFixedHeight(32)
        self._update_btn.setMinimumWidth(84)
        self._update_btn.setAccessibleName(f"Update {name}")
        self._update_btn.setStyleSheet(
            "QPushButton {"
            "  background: #34c759; color: white; border: none;"
            "  border-radius: 8px; font-size: 13px; font-weight: 600;"
            "  padding: 0 16px;"
            "}"
            "QPushButton:disabled { background: #d1d1d6; color: #86868b; }"
            "QPushButton:hover:!disabled { background: #2db84e; }"
        )
        self._update_btn.clicked.connect(lambda: self.update_clicked.emit(self.app_id))
        layout.addWidget(self._update_btn)

    def _version_text(self, info: UpdateInfo, installed: InstalledApp | None) -> str:
        installed_version = info.installed_version
        if not installed_version and installed is not None:
            installed_version = installed.version
        new_version = info.new_version
        parts: list[str] = []
        if installed_version and new_version:
            parts.append(f"{installed_version}  →  {new_version}")
        elif new_version:
            parts.append(new_version)
        elif installed_version:
            parts.append(installed_version)
        # Pacman rows carry the "applies after restart" note (R5.4).
        if self.source == Source.PACMAN:
            parts.append(_PACMAN_RESTART_NOTE)
        return "  ".join(parts)

    @property
    def is_auto_policy(self) -> bool:
        """Whether this row is eligible for Update all (auto, not self-managed)."""
        return eligible_for_update_all(self._installed) if self._installed is not None else False

    @property
    def is_checked(self) -> bool:
        return self._checkbox.isChecked()

    def set_running(self, running: bool) -> None:
        self._update_btn.setEnabled(not running)
        self._checkbox.setEnabled(not running)
        if running:
            self._progress.show()

    def update_progress(self, event: OperationEvent) -> None:
        """Update the inline progress bar from an OperationEvent."""
        self._progress.show()
        self._status_label.show()
        step = getattr(event, "step", "") or ""
        fraction = getattr(event, "fraction", None)
        message = getattr(event, "message", "") or ""
        handlers = {
            "download": lambda: self._set_fraction(fraction, message or "Downloading…"),
            "verify": lambda: self._set_determinate(1000, message or "Verifying…"),
            "handoff": lambda: self._set_determinate(1000, message or "Finishing…"),
            "install": lambda: self._set_busy(message or "Installing…"),
            "update": lambda: self._set_busy(message or "Updating…"),
            "remove": lambda: self._set_busy(message or "Removing…"),
            "finish": lambda: self._set_determinate(1000, "Done"),
            "fail": lambda: self._set_determinate(1000, "Failed"),
        }
        handler = handlers.get(step)
        if handler:
            handler()

    def set_result(self, success: bool, message: str) -> None:
        """Mark the row as finished with the given result."""
        self._finished = True
        self._progress.setRange(0, 1000)
        self._progress.setValue(1000)
        self._status_label.show()
        if success:
            self._status_label.setText("Updated")
            self._update_btn.setEnabled(False)
            self._update_btn.setText("Updated")
            self._checkbox.setEnabled(False)
        else:
            self._status_label.setText("Failed")
            self._update_btn.setEnabled(True)
            self._update_btn.setText("Retry")
        self._progress.hide()

    def _set_fraction(self, fraction: float | None, text: str) -> None:
        self._progress.setRange(0, 1000)
        self._progress.setValue(int((fraction or 0) * 1000))
        self._status_label.setText(text)

    def _set_determinate(self, value: int, text: str) -> None:
        self._progress.setRange(0, 1000)
        self._progress.setValue(value)
        self._status_label.setText(text)

    def _set_busy(self, text: str) -> None:
        self._progress.setRange(0, 0)  # indeterminate (busy) indicator
        self._status_label.setText(text)


class _UpdateSummaryDialog(QDialog):
    """Non-modal-ish summary dialog listing per-app success/failure/skipped."""

    def __init__(self, results: list[tuple[str, str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Update all")
        self.setModal(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Update summary")
        title_font = QFont(title.font())
        title_font.setPointSizeF(title_font.pointSizeF() + 4)
        title_font.setWeight(QFont.Weight.Bold)
        title.setFont(title_font)
        layout.addWidget(title)

        for name, status, message in results:
            row = QHBoxLayout()
            row.setSpacing(10)
            colors = {
                "success": "#2e7d32",
                "failure": "#b71c1c",
                "skipped": "#86868b",
            }
            tag = QLabel(status.capitalize())
            tag.setStyleSheet(
                f"color: white; background: {colors.get(status, '#86868b')}; "
                "padding: 1px 8px; border-radius: 8px; font-size: 11px; font-weight: 600;"
            )
            tag.setFixedWidth(64)
            row.addWidget(tag)
            label = QLabel(name)
            label.setStyleSheet("font-size: 13px; color: #1d1d1f;")
            row.addWidget(label, stretch=1)
            if message:
                detail = QLabel(message)
                detail.setStyleSheet("color: #86868b; font-size: 11px;")
                row.addWidget(detail)
            layout.addLayout(row)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(32)
        close_btn.setMinimumWidth(96)
        close_btn.setStyleSheet(
            "QPushButton {"
            "  background: #0071e3; color: white; border: none;"
            "  border-radius: 8px; font-size: 13px; font-weight: 600;"
            "  padding: 0 18px;"
            "}"
            "QPushButton:hover { background: #0077ed; }"
        )
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class UpdatesPage(QWidget):
    """Page listing available updates, grouped by source (R5.1-R5.4)."""

    update_requested = pyqtSignal(str)  # app_id (per-row Update button)
    update_all_requested = pyqtSignal(list)  # list of app_ids (auto-policy, FIFO)

    def __init__(self, icons_dir: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icons_dir = icons_dir
        self._rows: dict[str, _UpdateRow] = {}
        # Update-all batch tracking (keyed by app_id).
        self._update_all_batch: list[str] = []
        self._update_all_results: dict[str, tuple[bool, str]] = {}
        self._update_all_skipped: list[tuple[str, str]] = []  # (name, reason)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with Update all button
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet("background: #fafafa; border-bottom: 1px solid #d1d1d6;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 16, 0)
        h_layout.setSpacing(12)
        title = QLabel("Updates")
        title.setStyleSheet("font-size: 15px; font-weight: 600; color: #1d1d1f;")
        h_layout.addWidget(title)
        h_layout.addStretch()
        self._update_all_btn = QPushButton("Update all")
        self._update_all_btn.setFixedHeight(34)
        self._update_all_btn.setMinimumWidth(112)
        self._update_all_btn.setAccessibleName("Update all")
        self._update_all_btn.setStyleSheet(
            "QPushButton {"
            "  background: #0071e3; color: white; border: none;"
            "  border-radius: 8px; font-size: 13px; font-weight: 600;"
            "  padding: 0 18px;"
            "}"
            "QPushButton:disabled { background: #d1d1d6; color: #86868b; }"
            "QPushButton:hover:!disabled { background: #0077ed; }"
        )
        self._update_all_btn.clicked.connect(self._on_update_all)
        h_layout.addWidget(self._update_all_btn)
        layout.addWidget(header)

        # Scroll area holding the grouped rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: white; border: none; }")
        self._container = QWidget()
        self._container.setStyleSheet("background: white;")
        self._rows_layout = QVBoxLayout(self._container)
        self._rows_layout.setContentsMargins(16, 12, 16, 12)
        self._rows_layout.setSpacing(0)
        self._rows_layout.addStretch()
        scroll.setWidget(self._container)
        layout.addWidget(scroll, stretch=1)

        # Empty state
        self._empty_label = QLabel("No updates available.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #86868b; font-size: 15px;")
        self._empty_label.hide()
        layout.addWidget(self._empty_label)

    # ------------------------------------------------------------------ public API

    def populate(
        self,
        updates: list[UpdateInfo],
        installed: dict[str, InstalledApp],
    ) -> None:
        """Rebuild the page from a list of available updates.

        Args:
            updates: available updates (each carries app_key, versions, method).
            installed: installed apps keyed by app id.
        """
        self._clear_rows()
        self._rows.clear()

        by_source: dict[Source, list[UpdateInfo]] = {}
        for info in updates:
            by_source.setdefault(_source_of(info.app_key), []).append(info)

        any_rows = False
        for source in _SOURCE_ORDER:
            infos = by_source.pop(source, [])
            if not infos:
                continue
            any_rows = True
            self._rows_layout.insertWidget(
                self._rows_layout.count() - 1,
                _section_header(_SOURCE_LABELS.get(source, str(source))),
            )
            for info in infos:
                app_id = _id_of(info.app_key)
                row = _UpdateRow(info, installed.get(app_id), self.icons_dir)
                row.update_clicked.connect(self.update_requested.emit)
                self._rows[app_id] = row
                self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
                self._rows_layout.insertWidget(self._rows_layout.count() - 1, _hline())
        # Any leftover sources not in the canonical order are appended at the end.
        for source, infos in by_source.items():
            any_rows = True
            self._rows_layout.insertWidget(
                self._rows_layout.count() - 1,
                _section_header(_SOURCE_LABELS.get(source, str(source))),
            )
            for info in infos:
                app_id = _id_of(info.app_key)
                row = _UpdateRow(info, installed.get(app_id), self.icons_dir)
                row.update_clicked.connect(self.update_requested.emit)
                self._rows[app_id] = row
                self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
                self._rows_layout.insertWidget(self._rows_layout.count() - 1, _hline())

        self._empty_label.setVisible(not any_rows)
        self._update_all_btn.setEnabled(any_rows)

    def set_progress(self, app_key: str, event: OperationEvent) -> None:
        """Forward an operation progress event to the matching row."""
        row = self._rows.get(_id_of(app_key))
        if row is not None:
            row.set_running(True)
            row.update_progress(event)

    def set_result(self, app_key: str, success: bool, message: str) -> None:
        """Mark the matching row's result; show the summary when the batch completes."""
        app_id = _id_of(app_key)
        row = self._rows.get(app_id)
        if row is not None:
            row.set_result(success, message)
        if app_id in self._update_all_batch:
            self._update_all_results[app_id] = (success, message)
            if all(k in self._update_all_results for k in self._update_all_batch):
                self._show_summary()

    def show_summary(self, results: dict[str, tuple[bool, str]]) -> None:
        """Show the summary dialog for an externally-driven update-all batch."""
        self._update_all_results = dict(results)
        self._update_all_batch = list(results)
        self._show_summary()

    # ------------------------------------------------------------------ internal

    def _clear_rows(self) -> None:
        # Keep the trailing stretch item (last index).
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _on_update_all(self) -> None:
        """Collect checked auto-policy rows in FIFO order and request Update all."""
        batch: list[str] = []
        skipped: list[tuple[str, str]] = []
        for app_id, row in self._rows.items():
            if row.is_auto_policy and row.is_checked:
                batch.append(app_id)
            elif row.is_auto_policy and not row.is_checked:
                name = row._name_label.text()
                skipped.append((name, "not selected"))
            else:
                name = row._name_label.text()
                reason = (
                    "manual policy"
                    if row._installed and row._installed.update_policy == "manual"
                    else "not eligible"
                )
                skipped.append((name, reason))
        if not batch:
            return
        self._update_all_batch = list(batch)
        self._update_all_results = {}
        self._update_all_skipped = skipped
        self.update_all_requested.emit(batch)

    def _show_summary(self) -> None:
        results: list[tuple[str, str, str]] = []
        for app_id in self._update_all_batch:
            success, message = self._update_all_results.get(app_id, (False, ""))
            row = self._rows.get(app_id)
            name = row._name_label.text() if row is not None else app_id
            status = "success" if success else "failure"
            results.append((name, status, message))
        for name, reason in self._update_all_skipped:
            results.append((name, "skipped", reason))
        dlg = _UpdateSummaryDialog(results, self)
        from PyQt6.QtCore import QTimer

        # Defer showing so we never block a D-Bus reply callback directly.
        QTimer.singleShot(0, dlg.show)
        self._update_all_batch = []
        self._update_all_results = {}
        self._update_all_skipped = []
