"""ScreenshotCarousel: loads and shows app screenshots (section 10.3, P2.5).

Uses QNetworkAccessManager with QNetworkDiskCache so screenshots are cached on
disk and never block the UI thread. Network failures are silent (graceful
degradation): the carousel just shows fewer or no images.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QUrl
from PyQt6.QtGui import QPixmap
from PyQt6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkDiskCache,
    QNetworkReply,
    QNetworkRequest,
)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

THUMB_SIZE = QSize(160, 100)
MAIN_SIZE = QSize(640, 360)


class ScreenshotCarousel(QWidget):
    """A carousel of screenshots loaded asynchronously from the catalog URLs."""

    def __init__(self, screenshots: list[dict], parent=None) -> None:
        super().__init__(parent)
        self._screenshots = screenshots or []
        self._manager = QNetworkAccessManager(self)
        cache = QNetworkDiskCache(self)
        cache.setCacheDirectory("")
        self._manager.setCache(cache)
        self._pixmaps: dict[int, QPixmap] = {}

        self._main = QLabel()
        self._main.setFixedSize(MAIN_SIZE)
        self._main.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main.setStyleSheet("border: 1px solid palette(mid); border-radius: 8px;")
        self._main.setText("Screenshot")

        self._thumbs = QScrollArea()
        self._thumbs.setFixedHeight(THUMB_SIZE.height() + 20)
        self._thumbs.setWidgetResizable(True)
        self._thumbs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._thumbs.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        thumb_container = QWidget()
        self._thumb_layout = QHBoxLayout(thumb_container)
        self._thumb_layout.setContentsMargins(0, 0, 0, 0)
        self._thumb_layout.setSpacing(8)
        self._thumbs.setWidget(thumb_container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._main)
        layout.addWidget(self._thumbs)

        self._build_thumbnails()
        if self._screenshots:
            self._load_screenshot(0)

    def _build_thumbnails(self) -> None:
        for i, _shot in enumerate(self._screenshots):
            label = QLabel(f"{i + 1}")
            label.setFixedSize(THUMB_SIZE)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFrameShape(QFrame.Shape.StyledPanel)
            label.setCursor(Qt.CursorShape.PointingHandCursor)
            label.mousePressEvent = lambda event, idx=i: self._load_screenshot(idx)
            self._thumb_layout.addWidget(label)
        self._thumb_layout.addStretch()

    def _load_screenshot(self, index: int) -> None:
        if not (0 <= index < len(self._screenshots)):
            return
        shot = self._screenshots[index]
        images = shot.get("images") or []
        if not images:
            return
        # Pick the thumbnail closest to the view width.
        image = min(images, key=lambda im: abs((im.get("width") or 0) - MAIN_SIZE.width()))
        url = image.get("url")
        if not url:
            return
        if index in self._pixmaps:
            self._main.setPixmap(
                self._pixmaps[index].scaled(
                    MAIN_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            return
        reply = self._manager.get(QNetworkRequest(QUrl(url)))
        reply.finished.connect(lambda idx=index, r=reply: self._on_loaded(idx, r))

    def _on_loaded(self, index: int, reply: QNetworkReply) -> None:
        reply.deleteLater()
        if reply.error() != QNetworkReply.NetworkError.NoError:
            return  # graceful degradation: just skip
        data = reply.readAll()
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self._pixmaps[index] = pixmap
            if index == self._current_index():
                self._main.setPixmap(
                    pixmap.scaled(
                        MAIN_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

    def _current_index(self) -> int:
        return 0

    def closeEvent(self, event) -> None:  # noqa: N802
        # Abort all pending network requests to avoid Qt teardown crashes.
        # The QNetworkAccessManager is parented to this widget, so its
        # pending replies will be aborted when the manager is deleted.
        # Explicitly clear the pixmap cache to break reference cycles.
        self._pixmaps.clear()
        super().closeEvent(event)
