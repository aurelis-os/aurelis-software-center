"""Sidebar navigation (section 10.1)."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

SECTION_EXPLORE = "explore"
SECTION_INSTALLED = "installed"
SECTION_UPDATES = "updates"
SECTION_SETTINGS = "settings"

_ICONS = {
    SECTION_EXPLORE: "🔍",
    SECTION_INSTALLED: "📦",
    SECTION_UPDATES: "🔄",
    "source:appimage": "🖼",
    "source:flatpak": "📐",
    "source:pacman": "🏹",
    SECTION_SETTINGS: "⚙",
}


class Sidebar(QWidget):
    """Left navigation sidebar."""

    item_selected = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # App name header
        header = QLabel("Aurelis Software")
        header.setFixedHeight(52)
        header.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        header.setContentsMargins(16, 0, 16, 0)
        header.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #1d1d1f; "
            "background: #f0f0f2; border-bottom: 1px solid #d1d1d6;"
        )
        layout.addWidget(header)

        self._list = QListWidget()
        self._list.setFrameShape(QListWidget.Shape.NoFrame)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.currentItemChanged.connect(self._on_changed)
        layout.addWidget(self._list, stretch=1)

        self._items: dict[str, QListWidgetItem] = {}
        self._updates_count = 0
        self._build()

    def _build(self) -> None:
        self._add("Explore", SECTION_EXPLORE)
        self._add("Installed", SECTION_INSTALLED)
        self._updates_item = self._add("Updates", SECTION_UPDATES)
        self._section_label("Sources")
        self._add("AppImage", "source:appimage")
        self._add("Flathub", "source:flatpak")
        self._add("Pacman", "source:pacman")
        self._separator()
        self._add("Settings", SECTION_SETTINGS)
        self._list.setCurrentRow(0)

    def _section_label(self, text: str) -> None:
        item = QListWidgetItem(text.upper())
        item.setSizeHint(QSize(0, 28))
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        font = item.font()
        font.setPointSizeF(font.pointSizeF() - 1.5)
        font.setWeight(font.Weight.Bold)
        item.setFont(font)
        item.setForeground(Qt.GlobalColor.gray)
        self._list.addItem(item)

    def _add(self, text: str, section: str) -> QListWidgetItem:
        icon = _ICONS.get(section, "")
        label = f"  {icon}  {text}" if icon else f"  {text}"
        item = QListWidgetItem(label)
        item.setSizeHint(QSize(0, 36))
        item.setData(Qt.ItemDataRole.UserRole, section)
        self._items[section] = item
        self._list.addItem(item)
        return item

    def _separator(self) -> None:
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 8))
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self._list.addItem(item)

    def set_updates_count(self, count: int) -> None:
        self._updates_count = count
        item = self._items.get(SECTION_UPDATES)
        if item is None:
            return
        icon = _ICONS.get(SECTION_UPDATES, "")
        suffix = f"  ({count})" if count else ""
        item.setText(f"  {icon}  Updates{suffix}")

    def _on_changed(self, current, previous) -> None:
        if current is None:
            return
        section = current.data(Qt.ItemDataRole.UserRole)
        if section:
            self.item_selected.emit(section)

    def select_section(self, section: str) -> None:
        item = self._items.get(section)
        if item is not None:
            self._list.setCurrentItem(item)
