"""Semantic badge colors (section 10.7).

System palette and font are used for basics; only semantic badge colors
live here, with light and dark variants derived from the palette.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

_LIGHTNESS_THRESHOLD = 128
_CHIP_TEXT_LIGHTNESS = 140  # below this → white text on chip
_SRGB_THRESHOLD = 0.03928  # sRGB to linear threshold
_WCAG_AA_RATIO = 4.5  # WCAG AA contrast ratio requirement


def _palette() -> QColor:
    return QApplication.instance().palette()


def badge_color(kind: str) -> QColor:
    """Return a semantic badge color for the current palette.

    Kinds: installed, update, proprietary, incompatible, linked, neutral, success, warning.
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
        "success": ("#2e7d32", "#69f0ae"),
        "warning": ("#b26a00", "#ffb74d"),
    }
    dark, light = table[kind]
    return QColor(light if is_light else dark)


def _relative_luminance(color: QColor) -> float:
    """Calculate relative luminance for WCAG contrast ratio (0.0-1.0)."""

    def srgb_to_linear(val: float) -> float:
        if val <= _SRGB_THRESHOLD:
            return val / 12.92
        return ((val + 0.055) / 1.055) ** 2.4

    r = srgb_to_linear(color.redF())
    g = srgb_to_linear(color.greenF())
    b = srgb_to_linear(color.blueF())
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(c1: QColor, c2: QColor) -> float:
    """Calculate WCAG contrast ratio between two colors."""
    l1 = _relative_luminance(c1)
    l2 = _relative_luminance(c2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def assert_badge_contrast() -> None:
    """Assert that all badge colors meet WCAG AA contrast ratio (4.5:1) with their text color.

    Raises AssertionError if any badge fails the contrast check.
    """
    badge_kinds = [
        "installed",
        "update",
        "proprietary",
        "incompatible",
        "linked",
        "neutral",
        "success",
        "warning",
    ]

    for kind in badge_kinds:
        bg_color = badge_color(kind)
        # Determine text color based on background lightness
        text_color = (
            QColor("white") if bg_color.lightness() < _CHIP_TEXT_LIGHTNESS else QColor("black")
        )

        ratio = _contrast_ratio(bg_color, text_color)
        if ratio < _WCAG_AA_RATIO:
            msg = (
                f"Badge '{kind}' fails WCAG AA contrast: "
                f"ratio {ratio:.2f} < {_WCAG_AA_RATIO} "
                f"(bg={bg_color.name()}, text={text_color.name()})"
            )
            raise AssertionError(msg)
