"""Icon loading with caching and theme fallback (section 10.2)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap

ICON_SIZE = QSize(64, 64)
FALLBACK_ICON_NAME = "application-x-executable"

_cache: dict[str, QPixmap] = {}


def app_icon(icon_name: str | None, icons_dir: Path | None = None) -> QIcon:
    """Return a QIcon for an app, falling back to the theme executable icon.

    ``icons_dir`` is the cache directory holding ``<id>.png`` files. When the
    named icon file exists it is loaded; otherwise the theme fallback is used.
    Results are cached in memory.
    """
    key = icon_name or ""
    if key in _cache:
        return QIcon(_cache[key])

    pixmap: QPixmap | None = None
    if icon_name and icons_dir is not None:
        # icon_name may already include ".png" (e.g. "org.kde.kate.png")
        # Accept both with and without extension.
        if icon_name.lower().endswith(".png"):
            icon_path = icons_dir / icon_name
        else:
            icon_path = icons_dir / f"{icon_name}.png"
        if icon_path.is_file():
            pixmap = QPixmap(str(icon_path))

    if pixmap is None or pixmap.isNull():
        theme = QIcon.fromTheme(FALLBACK_ICON_NAME)
        if theme.isNull():
            pixmap = QPixmap(ICON_SIZE)
            pixmap.fill(Qt.GlobalColor.transparent)
        else:
            pixmap = theme.pixmap(ICON_SIZE)

    pixmap = pixmap.scaled(
        ICON_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    _cache[key] = pixmap
    return QIcon(pixmap)


def clear_icon_cache() -> None:
    _cache.clear()
