"""Banner widgets for calm status messages (section 10.5)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


class Banner(QWidget):
    """A non-dismissible calm banner shown under the search field."""

    def __init__(self, text: str, kind: str = "info", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Banner")
        colors = {
            "info": "#1565c0",
            "warning": "#b26a00",
            "error": "#b71c1c",
        }
        color = colors.get(kind, colors["info"])
        self.setStyleSheet(
            f"QWidget#Banner {{ background-color: {color}22; border: 1px solid {color}55; "
            "border-radius: 6px; }} QLabel {{ color: palette(window-text); }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        layout.addWidget(self._label, stretch=1)

    def set_text(self, text: str) -> None:
        self._label.setText(text)


class OfflineBanner(Banner):
    def __init__(self, parent=None) -> None:
        super().__init__(
            "You are offline. Showing the last saved catalog.", kind="warning", parent=parent
        )


class RefreshFailedBanner(Banner):
    def __init__(self, parent=None) -> None:
        super().__init__(
            "Could not refresh the catalog. Showing the last saved version.",
            kind="warning",
            parent=parent,
        )
