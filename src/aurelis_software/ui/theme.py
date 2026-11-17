"""Semantic badge colors (section 10.7).

System palette and font are used for basics; only semantic badge colors
live here, with light and dark variants derived from the palette.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

_LIGHTNESS_THRESHOLD = 128
_CHIP_TEXT_LIGHTNESS = 140  # below this → white text on chip
_CHIP_TEXT_LIGHTNESS = 140  # below this → white text on chip


def _palette() -> QColor:
    return QApplication.instance().palette()


def badge_color(kind: str) -> QColor:
    """Return a semantic badge color for the current palette.

    Kinds: installed, update, proprietary, incompatible, linked, neutral.
    """
    pal = _palette()
    base = pal.color(pal.ColorRole.Window)
    is_light = base.lightness() > _LIGHTNESS_THRESHOLD
    table = {
        "installed": ("#2e7d32", "#69f0ae"),
        "update": ("#1565c0", "#4dabff"),
        "proprietary": ("#b26a00", "#ffb74d"),
        "incompatible": ("#b71c1c", "#ef9a9a"),
        "linked": ("#6a1b9a", "#ce93d8"),
        "neutral": ("#546e7a", "#90a4ae"),
    }
    dark, light = table[kind]
    return QColor(light if is_light else dark)
