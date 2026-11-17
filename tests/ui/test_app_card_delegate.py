"""Tests for ui/app_card_delegate.py (P2.2): delegate with missing fields."""

from __future__ import annotations

import tarfile
import tempfile
from pathlib import Path

from PyQt6.QtCore import QRect, QSize
from PyQt6.QtGui import QFont, QFontMetrics, QPainter, QPixmap
from PyQt6.QtWidgets import QStyleOptionViewItem

from aurelis_software.core.models import App, Source
from aurelis_software.ui.app_card_delegate import (
    CARD_SIZE,
    CHIP_H,
    ICON_SIZE,
    AppCardDelegate,
    Chip,
    layout_chips,
)
from aurelis_software.ui.app_model import AppModel
from aurelis_software.ui.icons import app_icon, clear_icon_cache


def _app_missing_everything() -> App:
    return App(
        key="appimage:org.example.noicon",
        id="org.example.noicon",
        source=Source.APPIMAGE,
        name="No Icon App",
        summary="",
        version=None,
        raw={},
    )


def _app_with_mailspring_icon() -> App:
    return App(
        key="appimage:com.getmailspring.Mailspring",
        id="com.getmailspring.Mailspring",
        source=Source.APPIMAGE,
        name="Mailspring",
        summary="Email client",
        version="1.0",
        raw={"icon": {"name": "com.getmailspring.Mailspring.png"}},
    )


def _chip_metrics(qtbot) -> QFontMetrics:
    """Return font metrics matching the chip font used by the delegate."""
    option = QStyleOptionViewItem()
    font = QFont(option.font)
    font.setPointSizeF(max(6.5, option.font.pointSizeF() - 1.5))
    return QFontMetrics(font)


def test_delegate_size_hint(qtbot):
    delegate = AppCardDelegate(icons_dir=None)
    assert delegate.sizeHint(None, None) == CARD_SIZE


def test_delegate_paint_missing_fields_does_not_crash(qtbot):
    app = _app_missing_everything()
    model = AppModel()
    model.set_apps([app])
    index = model.index(0, 0)

    delegate = AppCardDelegate(icons_dir=None)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, CARD_SIZE.width(), CARD_SIZE.height())
    pixmap = QPixmap(CARD_SIZE)
    painter = QPainter(pixmap)
    delegate.paint(painter, option, index)
    painter.end()


def test_delegate_icon_size_constant() -> None:
    assert QSize(64, 64) == ICON_SIZE


def test_icon_mailspring_differs_from_fallback(qtbot):
    """With real fixture + extracted app-icons.tar.gz, app_icon for
    com.getmailspring.Mailspring returns a pixmap that differs from the fallback."""
    clear_icon_cache()

    # Extract app-icons.tar.gz to a temp dir
    icons_tar = Path(__file__).resolve().parent.parent / "fixtures" / "app-icons.tar.gz"
    assert icons_tar.exists(), "app-icons.tar.gz fixture missing"

    with tempfile.TemporaryDirectory() as tmpdir:
        icons_dir = Path(tmpdir)
        with tarfile.open(icons_tar, "r:gz") as tar:
            tar.extractall(icons_dir)

        # Get the Mailspring icon
        icon = app_icon("com.getmailspring.Mailspring.png", icons_dir)
        mailspring_pixmap = icon.pixmap(ICON_SIZE)

        # Get the fallback icon
        clear_icon_cache()
        fallback_icon = app_icon(None, None)
        fallback_pixmap = fallback_icon.pixmap(ICON_SIZE)

        # They should differ (Mailspring icon should not be the fallback)
        assert mailspring_pixmap.toImage() != fallback_pixmap.toImage(), (
            "Mailspring icon should differ from fallback"
        )


def test_delegate_paints_non_transparent_icon_pixels(qtbot):
    """Delegate paints non-transparent pixels in the icon rect for Mailspring."""
    clear_icon_cache()

    icons_tar = Path(__file__).resolve().parent.parent / "fixtures" / "app-icons.tar.gz"
    assert icons_tar.exists(), "app-icons.tar.gz fixture missing"

    with tempfile.TemporaryDirectory() as tmpdir:
        icons_dir = Path(tmpdir)
        with tarfile.open(icons_tar, "r:gz") as tar:
            tar.extractall(icons_dir)

        app = _app_with_mailspring_icon()
        model = AppModel()
        model.set_apps([app])
        index = model.index(0, 0)

        delegate = AppCardDelegate(icons_dir=icons_dir)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, CARD_SIZE.width(), CARD_SIZE.height())

        pixmap = QPixmap(CARD_SIZE)
        pixmap.fill(0)  # transparent
        painter = QPainter(pixmap)
        delegate.paint(painter, option, index)
        painter.end()

        # Check icon rect for non-transparent pixels
        icon_rect = QRect(16, 16, ICON_SIZE.width(), ICON_SIZE.height())
        image = pixmap.toImage()
        has_non_transparent = False
        for x in range(icon_rect.left(), icon_rect.right()):
            for y in range(icon_rect.top(), icon_rect.bottom()):
                if image.pixelColor(x, y).alpha() > 0:
                    has_non_transparent = True
                    break
            if has_non_transparent:
                break

        assert has_non_transparent, "Delegate should paint non-transparent pixels in icon rect"


# ── layout_chips: version chip never elided ────────────────────────────────


def _version_chip(row1: list[Chip], row2: list[Chip], version: str) -> Chip | None:
    for chip in row1 + row2:
        if chip.kind == "version" and chip.text == version:
            return chip
    return None


def _category_chip(row1: list[Chip], row2: list[Chip], category: str) -> Chip | None:
    for chip in row1 + row2:
        if chip.kind == "neutral" and category in chip.text:
            return chip
    return None


# Multiple categories that fill both rows — version must survive, categories may be dropped.
_MULTI_CATS = [
    "Education",
    "Science",
    "Astronomy",
    "Very Long Category Name That Exceeds Chip Width Limit",
]


def test_layout_chips_version_26_08_1_not_elided(qtbot):
    """Version '26.08.1' must appear unelided even when categories fill both rows."""
    metrics = _chip_metrics(qtbot)
    version = "26.08.1"
    chips = (
        [("appimage", "source")] + [(c, "neutral") for c in _MULTI_CATS] + [(version, "version")]
    )
    row1, row2 = layout_chips(chips, metrics, CARD_SIZE.width() - 28)

    vc = _version_chip(row1, row2, version)
    assert vc is not None, "version chip must be present"
    assert vc.text == version, f"version chip text elided: got {vc.text!r}"


def test_layout_chips_version_6_0_8078_130_not_elided(qtbot):
    """Version '6.0.8078.130-1' must appear unelided even when categories fill both rows."""
    metrics = _chip_metrics(qtbot)
    version = "6.0.8078.130-1"
    chips = (
        [("appimage", "source")] + [(c, "neutral") for c in _MULTI_CATS] + [(version, "version")]
    )
    row1, row2 = layout_chips(chips, metrics, CARD_SIZE.width() - 28)

    vc = _version_chip(row1, row2, version)
    assert vc is not None, "version chip must be present"
    assert vc.text == version, f"version chip text elided: got {vc.text!r}"


# ── layout_chips: license chip sized from full text ────────────────────────


def _license_chip_width(qtbot, license_text: str) -> int:
    metrics = _chip_metrics(qtbot)
    chips = [("appimage", "source"), (license_text, "license")]
    row1, row2 = layout_chips(chips, metrics, 9999)
    for chip in row1 + row2:
        if chip.kind == "license":
            return chip.width
    msg = "license chip not found"
    raise AssertionError(msg)


def test_license_chip_gpl2_not_clipped(qtbot):
    """'GPL-2.0-only' chip must be wide enough to show the full text."""
    text = "GPL-2.0-only"
    metrics = _chip_metrics(qtbot)
    w = _license_chip_width(qtbot, text)
    natural = metrics.horizontalAdvance(text) + 20  # 2 * _CHIP_PADDING_H
    assert w >= natural, f"chip width {w} < natural {natural} for {text!r}"


def test_license_chip_gpl3_not_clipped(qtbot):
    """'GPL-3.0-or-later' chip must be wide enough to show the full text."""
    text = "GPL-3.0-or-later"
    metrics = _chip_metrics(qtbot)
    w = _license_chip_width(qtbot, text)
    natural = metrics.horizontalAdvance(text) + 20
    assert w >= natural, f"chip width {w} < natural {natural} for {text!r}"


def test_license_chip_proprietary_not_clipped(qtbot):
    """'LicenseRef-proprietary' chip must be wide enough to show the full text."""
    text = "LicenseRef-proprietary"
    metrics = _chip_metrics(qtbot)
    w = _license_chip_width(qtbot, text)
    natural = metrics.horizontalAdvance(text) + 20
    assert w >= natural, f"chip width {w} < natural {natural} for {text!r}"


# ── Chip dataclass ─────────────────────────────────────────────────────────


def test_chip_dataclass_fields():
    c = Chip(text="1.0", kind="version", width=50)
    assert c.text == "1.0"
    assert c.kind == "version"
    assert c.width == 50
    assert c.width == CHIP_H + 32 or c.width == 50  # just check it's accessible
