"""AppCardDelegate: paints catalog cards in icon-grid mode (section 10.2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QAbstractItemDelegate,
    QStyle,
    QStyleOptionViewItem,
)

from aurelis_software.ui.icons import app_icon
from aurelis_software.ui.theme import _CHIP_TEXT_LIGHTNESS, badge_color

# Card geometry — width is a minimum; AppListView stretches to fill viewport.
CARD_MIN_W = 180
CARD_H = 220
ICON_SIZE = QSize(64, 64)
CHIP_H = 18
_CHIP_PADDING_H = 10  # horizontal padding inside each chip
_CHIP_SPACING = 5  # gap between chips
_MIN_CHIP_WIDTH = 20
_CHIP_MAX_W = 110  # max chip width before elision (non-version/license chips)
_CHIP_MAX_WIDTH = _CHIP_MAX_W  # legacy alias used by tests
_RADIUS = 12
_SHADOW_BLUR = 6


@dataclass
class Chip:
    text: str
    kind: str
    width: int  # pixel width of the chip rectangle


# Role offsets mirror AppModel.
IdRole = Qt.ItemDataRole.UserRole + 1
KeyRole = Qt.ItemDataRole.UserRole + 2
NameRole = Qt.ItemDataRole.UserRole + 3
SummaryRole = Qt.ItemDataRole.UserRole + 4
VersionRole = Qt.ItemDataRole.UserRole + 5
SourceRole = Qt.ItemDataRole.UserRole + 6
StoreCategoriesRole = Qt.ItemDataRole.UserRole + 7
RawRole = Qt.ItemDataRole.UserRole + 8

# Keep legacy alias so existing tests importing CARD_SIZE still work.
CARD_SIZE = QSize(CARD_MIN_W, CARD_H)


def _data(index, role, default=None):
    value = index.data(role)
    return value if value is not None else default


def _draw_shadow(painter: QPainter, rect: QRect, radius: int, blur: int) -> None:
    """Draw a soft drop-shadow behind the card."""
    for i in range(blur, 0, -1):
        alpha = int(28 * (blur - i + 1) / blur)
        c = QColor(0, 0, 0, alpha)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(c, 1))
        sr = rect.adjusted(-i, -i + 2, i, i + 2)
        path = QPainterPath()
        path.addRoundedRect(sr.x(), sr.y(), sr.width(), sr.height(), radius + i, radius + i)
        painter.drawPath(path)


def _chip_list(source, categories: tuple, version) -> list[tuple[str, str]]:
    """Order: source, version (protected from elision), then categories."""
    chips: list[tuple[str, str]] = []
    if source is not None:
        chips.append((str(source), "source"))
    if version:
        chips.append((str(version), "version"))
    if isinstance(categories, (list, tuple)):
        chips.extend((str(c), "neutral") for c in categories)
    return chips


def _place_chip(
    rows: list[list[Chip]],
    row_used: list[int],
    chip: Chip,
    max_w: int,
    *,
    force_row2: bool = False,
) -> bool:
    """Try row 0 then row 1; return True if placed normally, False if forced/dropped."""
    for r in (0, 1):
        gap = _CHIP_SPACING if row_used[r] > 0 else 0
        if row_used[r] + gap + chip.width <= max_w:
            rows[r].append(chip)
            row_used[r] += gap + chip.width
            return True
    if force_row2:
        rows[1].append(chip)
    return False


def _overflow_chip(text: str, kind: str, metrics, row_used: list[int], max_w: int) -> Chip | None:
    """Return a chip elided to fit remaining row-2 space, or None if too narrow."""
    remaining = max_w - row_used[1] - (_CHIP_SPACING if row_used[1] > 0 else 0)
    if remaining < _MIN_CHIP_WIDTH:
        return None
    cw = min(
        metrics.horizontalAdvance(
            metrics.elidedText(text, Qt.TextElideMode.ElideRight, _CHIP_MAX_W)
        )
        + _CHIP_PADDING_H * 2,
        remaining,
    )
    elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, cw - _CHIP_PADDING_H * 2)
    return Chip(elided, kind, cw)


def layout_chips(
    texts_kinds: list[tuple[str, str]],
    metrics,
    max_w: int,
) -> tuple[list[Chip], list[Chip]]:
    """Lay chips into two rows; return (row1, row2).

    Version/license chips use natural width and are never elided.
    Category/neutral chips are elided at _CHIP_MAX_W and dropped if no space.
    """
    rows: list[list[Chip]] = [[], []]
    row_used = [0, 0]

    for text, kind in texts_kinds:
        if kind in ("version", "license"):
            cw = metrics.horizontalAdvance(text) + _CHIP_PADDING_H * 2
            _place_chip(rows, row_used, Chip(text, kind, cw), max_w, force_row2=True)
        else:
            elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, _CHIP_MAX_W)
            cw = min(metrics.horizontalAdvance(elided) + _CHIP_PADDING_H * 2, _CHIP_MAX_W)
            if not _place_chip(rows, row_used, Chip(elided, kind, cw), max_w):
                overflow = _overflow_chip(text, kind, metrics, row_used, max_w)
                if overflow:
                    rows[1].append(overflow)

    return rows[0], rows[1]


@dataclass
class _ChipPaintContext:
    painter: QPainter
    x0: int
    row1_y: int
    row2_y: int
    selected: bool


class AppCardDelegate(QAbstractItemDelegate):
    """Paints a single app card: icon (top-centre), name, summary, two chip rows."""

    def __init__(self, icons_dir: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self.icons_dir = icons_dir

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: N802
        return QSize(CARD_MIN_W, CARD_H)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = option.rect.adjusted(_SHADOW_BLUR, _SHADOW_BLUR, -_SHADOW_BLUR, -_SHADOW_BLUR)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        _draw_shadow(painter, rect, _RADIUS, _SHADOW_BLUR)

        if selected:
            bg = option.palette.highlight().color()
        elif hovered:
            bg = option.palette.base().color().lighter(103)
        else:
            bg = option.palette.base().color()

        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), _RADIUS, _RADIUS)
        painter.setBrush(bg)
        border_color = (
            option.palette.highlight().color().lighter(130) if selected else QColor(0, 0, 0, 18)
        )
        painter.setPen(QPen(border_color, 1))
        painter.drawPath(path)
        painter.setClipPath(path)

        name = _data(index, NameRole, "") or ""
        summary = _data(index, SummaryRole, "") or ""
        version = _data(index, VersionRole)
        source = _data(index, SourceRole)
        categories = _data(index, StoreCategoriesRole, ()) or ()
        raw = _data(index, RawRole, {}) or {}
        icon_name = raw.get("icon", {}).get("name") if isinstance(raw, dict) else None

        pad = 14
        inner_w = rect.width() - 2 * pad

        # ── Icon ───────────────────────────────────────────────────────────
        icon_x = rect.x() + (rect.width() - ICON_SIZE.width()) // 2
        icon_y = rect.y() + 16
        app_icon(icon_name, self.icons_dir).paint(
            painter, QRect(icon_x, icon_y, ICON_SIZE.width(), ICON_SIZE.height())
        )

        # ── Name ───────────────────────────────────────────────────────────
        name_y = icon_y + ICON_SIZE.height() + 10
        name_font = QFont(option.font)
        name_font.setPointSizeF(option.font.pointSizeF() + 1)
        name_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(name_font)
        text_color = (
            option.palette.highlightedText().color() if selected else option.palette.text().color()
        )
        painter.setPen(text_color)
        painter.drawText(
            QRect(rect.x() + pad, name_y, inner_w, 36),
            int(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap
            ),
            name,
        )

        # ── Summary ────────────────────────────────────────────────────────
        summary_font = QFont(option.font)
        summary_font.setPointSizeF(max(7.0, option.font.pointSizeF() - 0.5))
        painter.setFont(summary_font)
        muted = (
            option.palette.highlightedText().color()
            if selected
            else option.palette.placeholderText().color()
        )
        painter.setPen(muted)
        metrics = painter.fontMetrics()
        painter.drawText(
            QRect(rect.x() + pad, name_y + 38, inner_w, 18),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(summary, Qt.TextElideMode.ElideRight, inner_w),
        )

        # ── Chips ──────────────────────────────────────────────────────────
        chip_font = QFont(option.font)
        chip_font.setPointSizeF(max(6.5, option.font.pointSizeF() - 1.5))
        chip_font.setWeight(QFont.Weight.Medium)
        painter.setFont(chip_font)

        row1_y = rect.bottom() - 2 * CHIP_H - _CHIP_SPACING - 10
        row1, row2 = layout_chips(
            _chip_list(source, categories, version), painter.fontMetrics(), inner_w
        )
        ctx = _ChipPaintContext(
            painter, rect.x() + pad, row1_y, row1_y + CHIP_H + _CHIP_SPACING, selected
        )
        self._paint_chips(ctx, row1, row2)

        painter.restore()

    def _paint_chips(
        self,
        ctx: _ChipPaintContext,
        row1: list[Chip],
        row2: list[Chip],
    ) -> None:
        """Paint two pre-laid-out chip rows."""
        for row_chips, row_y in ((row1, ctx.row1_y), (row2, ctx.row2_y)):
            x = ctx.x0
            for chip in row_chips:
                color = self._chip_color(chip.kind, ctx.selected)
                chip_rect = QRect(x, row_y, chip.width, CHIP_H)
                path = QPainterPath()
                path.addRoundedRect(
                    chip_rect.x(),
                    chip_rect.y(),
                    chip_rect.width(),
                    chip_rect.height(),
                    CHIP_H / 2,
                    CHIP_H / 2,
                )
                ctx.painter.setBrush(color)
                ctx.painter.setPen(Qt.PenStyle.NoPen)
                ctx.painter.drawPath(path)
                lum = color.lightness()
                tc = QColor("#ffffff") if lum < _CHIP_TEXT_LIGHTNESS else QColor("#1a1a1a")
                ctx.painter.setPen(tc)
                ctx.painter.drawText(chip_rect, int(Qt.AlignmentFlag.AlignCenter), chip.text)
                x += chip.width + _CHIP_SPACING

    def _chip_color(self, kind: str, selected: bool) -> QColor:
        if selected:
            return QColor(255, 255, 255, 55)
        if kind == "source":
            return badge_color("update")
        if kind == "version":
            return badge_color("installed")
        if kind == "license":
            return badge_color("proprietary")
        return badge_color("neutral")
