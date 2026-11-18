"""Conflict dialog for AppImage install conflicts (P3.5, section 7.2 step 5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


@dataclass
class ConflictInfo:
    """Information about a conflicting installed app."""

    app_id: str
    name: str
    version: str | None
    relation: Literal["upgrade", "downgrade", "same"]  # relative to new version


class ConflictDialog(QDialog):
    """In-GUI conflict resolution dialog (section 7.2 step 5).

    Shows old vs new version and offers Replace / Keep both / Cancel.
    No daemon notification appears because conflict=error and silent=true.
    """

    # Emitted with the user's choice: "replace", "keep", or "cancel"
    choice_made = pyqtSignal(str)

    def __init__(
        self,
        new_name: str,
        new_version: str | None,
        conflicts: list[ConflictInfo],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("AppImage Conflict"))
        self.setModal(True)
        self.setMinimumWidth(480)
        self._conflicts = conflicts

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel(self.tr("An AppImage with the same name already exists."))
        title.setWordWrap(True)
        title.setStyleSheet("color: #1d1d1f; font-size: 15px; font-weight: 500;")
        layout.addWidget(title)

        # New app info
        new_box = QVBoxLayout()
        new_box.setSpacing(4)
        new_label = QLabel(self.tr("New AppImage"))
        new_label.setStyleSheet("color: #86868b; font-size: 12px; font-weight: 600;")
        new_box.addWidget(new_label)

        new_name_label = QLabel(new_name)
        new_name_font = QFont(new_name_label.font())
        new_name_font.setPointSizeF(new_name_font.pointSizeF() + 2)
        new_name_font.setWeight(QFont.Weight.DemiBold)
        new_name_label.setFont(new_name_font)
        new_name_label.setStyleSheet("color: #1d1d1f;")
        new_box.addWidget(new_name_label)

        if new_version:
            new_ver = QLabel(self.tr("Version: {version}").format(version=new_version))
            new_ver.setStyleSheet("color: #86868b; font-size: 12px;")
            new_box.addWidget(new_ver)

        layout.addLayout(new_box)

        # Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #d1d1d6;")
        layout.addWidget(sep)

        # Conflicts list
        for conflict in conflicts:
            self._add_conflict_row(layout, conflict)

        # Explanation
        explain = QLabel(
            self.tr(
                "The daemon will keep the existing file's user-chosen name and menu entry. "
                "Choose what to do with the new file:"
            )
        )
        explain.setWordWrap(True)
        explain.setStyleSheet("color: #86868b; font-size: 12px;")
        layout.addWidget(explain)

        # Buttons
        buttons = QDialogButtonBox()
        buttons.setOrientation(Qt.Orientation.Horizontal)

        self._replace_btn = buttons.addButton(
            self.tr("Replace"),
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self._replace_btn.setToolTip(
            self.tr(
                "Replace the existing AppImage with the new one. The old version is moved to a backup location."
            )
        )

        self._keep_btn = buttons.addButton(
            self.tr("Keep both"),
            QDialogButtonBox.ButtonRole.ActionRole,
        )
        self._keep_btn.setToolTip(
            self.tr(
                "Install the new version alongside the existing one. Both will appear in your Applications."
            )
        )

        self._cancel_btn = buttons.addButton(
            self.tr("Cancel"),
            QDialogButtonBox.ButtonRole.RejectRole,
        )

        # Style buttons
        for btn in buttons.buttons():
            btn.setFixedHeight(36)
            btn.setMinimumWidth(100)

        self._replace_btn.setStyleSheet(
            "QPushButton {"
            "  background: #0071e3; color: white; border: none;"
            "  border-radius: 8px; font-size: 13px; font-weight: 600;"
            "}"
            "QPushButton:hover { background: #0077ed; }"
        )
        self._keep_btn.setStyleSheet(
            "QPushButton {"
            "  background: #e5e5ea; color: #1d1d1f; border: none;"
            "  border-radius: 8px; font-size: 13px; font-weight: 600;"
            "}"
            "QPushButton:hover { background: #d1d1d6; }"
        )
        self._cancel_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #1d1d1f; border: none;"
            "  border-radius: 8px; font-size: 13px; font-weight: 600;"
            "}"
            "QPushButton:hover { background: #e5e5ea; }"
        )

        buttons.accepted.connect(self._on_replace)
        buttons.rejected.connect(self._on_cancel)
        self._keep_btn.clicked.connect(self._on_keep)

        layout.addWidget(buttons)

    def _add_conflict_row(self, layout: QVBoxLayout, conflict: ConflictInfo) -> None:
        row = QHBoxLayout()
        row.setSpacing(12)

        # Existing app info
        info_box = QVBoxLayout()
        info_box.setSpacing(2)

        existing_label = QLabel(self.tr("Existing"))
        existing_label.setStyleSheet("color: #86868b; font-size: 11px; font-weight: 600;")
        info_box.addWidget(existing_label)

        name_label = QLabel(conflict.name)
        name_font = QFont(name_label.font())
        name_font.setPointSizeF(name_font.pointSizeF() + 1)
        name_font.setWeight(QFont.Weight.Medium)
        name_label.setFont(name_font)
        name_label.setStyleSheet("color: #1d1d1f;")
        info_box.addWidget(name_label)

        version_text = conflict.version or self.tr("unknown version")
        ver_label = QLabel(self.tr("Version: {version}").format(version=version_text))
        ver_label.setStyleSheet("color: #86868b; font-size: 11px;")
        info_box.addWidget(ver_label)

        row.addLayout(info_box)

        # Relation label (plain colored text, not a badge)
        relation_colors = {
            "upgrade": "#34c759",
            "downgrade": "#ff9f0a",
            "same": "#0071e3",
        }
        relation_labels = {
            "upgrade": self.tr("Upgrade"),
            "downgrade": self.tr("Downgrade"),
            "same": self.tr("Same version"),
        }
        color = relation_colors.get(conflict.relation, "#86868b")
        label = QLabel(relation_labels.get(conflict.relation, conflict.relation))
        label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(label)

        layout.addLayout(row)

    def _on_replace(self) -> None:
        self.choice_made.emit("replace")
        self.accept()

    def _on_keep(self) -> None:
        self.choice_made.emit("keep")
        self.accept()

    def _on_cancel(self) -> None:
        self.choice_made.emit("cancel")
        self.reject()


class UnverifiedDownloadDialog(QDialog):
    """Confirmation dialog for downloads without checksum (section 7.2 step 3)."""

    def __init__(
        self,
        app_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("No Checksum Available"))
        self.setModal(True)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Warning icon and message
        icon_msg = QHBoxLayout()
        icon_msg.setSpacing(12)

        warning_label = QLabel("⚠")
        warning_label.setStyleSheet("font-size: 32px;")
        icon_msg.addWidget(warning_label, alignment=Qt.AlignmentFlag.AlignTop)

        msg_box = QVBoxLayout()
        msg_box.setSpacing(4)
        title = QLabel(self.tr("No checksum available for {name}").format(name=app_name))
        title.setWordWrap(True)
        title.setStyleSheet("color: #1d1d1f; font-size: 14px; font-weight: 500;")
        msg_box.addWidget(title)

        detail = QLabel(
            self.tr(
                "The catalog does not provide a SHA256 checksum for this AppImage. "
                "Without verification, we cannot confirm the file hasn't been tampered with. "
                "Only proceed if you trust the source."
            )
        )
        detail.setWordWrap(True)
        detail.setStyleSheet("color: #86868b; font-size: 12px;")
        msg_box.addWidget(detail)

        icon_msg.addLayout(msg_box, stretch=1)
        layout.addLayout(icon_msg)

        # Checkbox for "Don't ask again"
        from PyQt6.QtWidgets import QCheckBox

        self._dont_ask = QCheckBox(self.tr("Don't ask again for this app"))
        self._dont_ask.setStyleSheet("font-size: 12px; color: #1d1d1f;")
        layout.addWidget(self._dont_ask)

        # Buttons
        buttons = QDialogButtonBox()
        buttons.setOrientation(Qt.Orientation.Horizontal)

        self._proceed_btn = buttons.addButton(
            self.tr("Proceed anyway"),
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self._proceed_btn.setStyleSheet(
            "QPushButton {"
            "  background: #b71c1c; color: white; border: none;"
            "  border-radius: 8px; font-size: 13px; font-weight: 600; min-width: 120px;"
            "}"
            "QPushButton:hover { background: #c02020; }"
        )

        self._cancel_btn = buttons.addButton(
            self.tr("Cancel"),
            QDialogButtonBox.ButtonRole.RejectRole,
        )
        self._cancel_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #1d1d1f; border: none;"
            "  border-radius: 8px; font-size: 13px; font-weight: 600; min-width: 80px;"
            "}"
            "QPushButton:hover { background: #e5e5ea; }"
        )

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

    @property
    def dont_ask_again(self) -> bool:
        return self._dont_ask.isChecked()
