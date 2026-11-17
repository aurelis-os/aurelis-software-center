"""DetailPage: the read-only app detail view (section 10.3)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
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
    """Read-only detail page for a single catalog App."""

    install_requested = pyqtSignal(str)

    def __init__(self, icons_dir: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self.icons_dir = icons_dir
        self._app: App | None = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: white; }")

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

    def set_app(self, app: App | None) -> None:
        self._app = app
        self._rebuild()

    def clear(self) -> None:
        self._app = None
        self._rebuild()

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

        self._header(app)
        self._layout.addSpacing(20)
        self._trust_line(app)
        self._screenshot_carousel(app)
        self._description(app)
        self._links(app)
        self._also_available_as(app)
        self._layout.addStretch()

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
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

    def _header(self, app: App) -> None:
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

        # Action button
        self._action_button = QPushButton(self.tr("Install"))
        self._action_button.setEnabled(False)
        self._action_button.setToolTip(
            self.tr("Install is not available in this read-only preview.")
        )
        self._action_button.setFixedSize(100, 36)
        self._action_button.setStyleSheet(
            "QPushButton {"
            "  background: #0071e3; color: white; border: none;"
            "  border-radius: 8px; font-size: 13px; font-weight: 600;"
            "}"
            "QPushButton:disabled {"
            "  background: #d1d1d6; color: #86868b;"
            "}"
        )
        self._action_button.clicked.connect(lambda: self.install_requested.emit(app.id))
        row.addWidget(self._action_button, stretch=0, alignment=Qt.AlignmentFlag.AlignTop)

        self._layout.addLayout(row)

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
            # Still show checksum note
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

        if sha256:
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

    def _screenshot_carousel(self, app: App) -> None:
        screenshots = app.raw.get("screenshots") or []
        if not screenshots:
            return
        carousel = ScreenshotCarousel(screenshots, parent=self)
        self._layout.addWidget(carousel)
        self._layout.addSpacing(16)
        self._layout.addWidget(_divider())
        self._layout.addSpacing(16)

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

    def _also_available_as(self, app: App) -> None:
        self._layout.addWidget(_section_title(self.tr("Also available as")))
        self._layout.addSpacing(8)
        placeholder = QLabel(self.tr("(other sources with the same id appear here)"))
        placeholder.setStyleSheet("color: #86868b; font-size: 13px; font-style: italic;")
        self._layout.addWidget(placeholder)
