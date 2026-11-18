"""Resumable downloader with incremental sha256 (spec 7.4).

Uses QNetworkAccessManager on the calling thread's event loop.
Never blocks the UI thread — callers connect to ``progress``,
``finished`` and ``failed`` signals and return immediately.

Redirect policy: NoLessSafeRedirectPolicy (https only, no downgrade).
Timeouts: connect 15 s, stall (no bytes) 30 s.
Token / credential rule: never sent to any host.
Free-space check: performed before the download starts.
On any failure the ``.part`` file is deleted.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from aurelis_software.core.errors import ChecksumMismatch, DiskFull, NetworkError

if TYPE_CHECKING:
    from hashlib import _Hash

log = logging.getLogger(__name__)

_CONNECT_TIMEOUT_MS = 15_000
_STALL_TIMEOUT_MS = 30_000
_MIN_FREE_MULTIPLIER = 2  # need 2x the expected size free


class Downloader(QObject):
    """Download one file; emit signals for progress and completion.

    Signals
    -------
    progress(received: int, total: int)
        ``total`` is -1 when unknown.
    finished(path: Path)
        Emitted with the final (non-``.part``) path on success.
    failed(error: AurelisError)
        Emitted on any failure; the ``.part`` file has been deleted.
    """

    progress = pyqtSignal(int, int)
    finished = pyqtSignal(object)  # Path
    failed = pyqtSignal(object)  # AurelisError subclass

    def __init__(self, nam: QNetworkAccessManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._nam = nam
        self._nam.setRedirectPolicy(QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        self._reply: QNetworkReply | None = None
        self._part: Path | None = None
        self._dest: Path | None = None
        self._sha256: str | None = None
        self._hasher: _Hash | None = None
        self._received = 0
        self._fh = None
        self._stall_timer = QTimer(self)
        self._stall_timer.setSingleShot(True)
        self._stall_timer.timeout.connect(self._on_stall)
        self._connect_timer = QTimer(self)
        self._connect_timer.setSingleShot(True)
        self._connect_timer.timeout.connect(self._on_connect_timeout)
        self._timeout_abort = False  # True when abort was triggered by a timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(
        self,
        url: str,
        dest: Path,
        *,
        sha256: str | None = None,
        expected_size: int | None = None,
    ) -> None:
        """Begin downloading *url* to *dest* (final path, without ``.part``).

        If ``dest.name + '.part'`` already exists and the server answers 206,
        the download resumes; otherwise it restarts.
        """
        if self._reply is not None:
            log.warning("downloader already running; ignoring start()")
            return

        self._dest = dest
        self._sha256 = sha256
        self._part = dest.parent / (dest.name + ".part")
        self._hasher = hashlib.sha256()
        self._received = 0
        self._timeout_abort = False

        # Free-space check
        if expected_size is not None:
            try:
                free = shutil.disk_usage(dest.parent).free
            except OSError:
                free = shutil.disk_usage(Path.home()).free
            if free < expected_size * _MIN_FREE_MULTIPLIER:
                self._emit_failed(DiskFull(f"Need {expected_size * 2} bytes free, have {free}"))
                return

        dest.parent.mkdir(parents=True, exist_ok=True)

        req = QNetworkRequest()
        req.setUrl(_qurl(url))

        # Resume if .part exists
        resume_from = 0
        if self._part.exists():
            resume_from = self._part.stat().st_size
            if resume_from > 0:
                req.setRawHeader(b"Range", f"bytes={resume_from}-".encode())
                log.debug("resuming from byte %d", resume_from)

        try:
            if resume_from > 0:
                self._fh = self._part.open("ab")
                with self._part.open("rb") as existing:
                    for chunk in iter(lambda: existing.read(65536), b""):
                        self._hasher.update(chunk)
                self._received = resume_from
            else:
                self._fh = self._part.open("wb")
        except OSError as exc:
            self._emit_failed(NetworkError(str(exc)))
            return

        self._connect_timer.start(_CONNECT_TIMEOUT_MS)
        self._reply = self._nam.get(req)
        self._reply.readyRead.connect(self._on_ready_read)
        self._reply.downloadProgress.connect(self._on_download_progress)
        self._reply.finished.connect(self._on_finished)
        self._reply.errorOccurred.connect(self._on_error)

    def cancel(self) -> None:
        """Abort the current download and delete the ``.part`` file."""
        if self._reply is not None:
            self._reply.abort()

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_ready_read(self) -> None:
        self._connect_timer.stop()
        self._stall_timer.start(_STALL_TIMEOUT_MS)
        if self._reply is None or self._fh is None or self._hasher is None:
            return
        data = bytes(self._reply.readAll())
        if data:
            self._fh.write(data)
            self._hasher.update(data)
            self._received += len(data)

    def _on_download_progress(self, received: int, total: int) -> None:
        self.progress.emit(self._received, total if total > 0 else -1)

    def _on_stall(self) -> None:
        log.warning("download stalled (no bytes for %d ms)", _STALL_TIMEOUT_MS)
        if self._reply is not None:
            self._timeout_abort = True
            self._reply.abort()

    def _on_connect_timeout(self) -> None:
        log.warning("connect timeout (%d ms)", _CONNECT_TIMEOUT_MS)
        if self._reply is not None:
            self._timeout_abort = True
            self._reply.abort()

    def _on_error(self, err: QNetworkReply.NetworkError) -> None:
        if err == QNetworkReply.NetworkError.OperationCanceledError:
            return  # handled in _on_finished
        log.debug("network error: %s", err)

    def _on_finished(self) -> None:
        self._connect_timer.stop()
        self._stall_timer.stop()

        reply = self._reply
        self._reply = None

        if self._fh is not None:
            with contextlib.suppress(OSError):
                self._fh.close()
            self._fh = None

        if reply is None:
            return

        err = reply.error()
        reply.deleteLater()

        if err == QNetworkReply.NetworkError.OperationCanceledError:
            if self._timeout_abort:
                self._emit_failed(NetworkError("Download timed out (no data received)"))
            else:
                self._cleanup_part()  # user cancel — no error signal
            return

        if err != QNetworkReply.NetworkError.NoError:
            self._emit_failed(NetworkError(reply.errorString()))
            return

        # Check HTTP status
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status is not None and status not in (200, 206):
            self._emit_failed(NetworkError(f"HTTP {status}"))
            return

        # Verify sha256
        if self._sha256 is not None:
            assert self._hasher is not None
            digest = self._hasher.hexdigest()
            if digest != self._sha256:
                self._emit_failed(
                    ChecksumMismatch(
                        f"Expected {self._sha256}, got {digest}",
                        details=f"url={reply.url().toString()}",
                    )
                )
                return

        # Rename .part -> dest
        assert self._part is not None
        assert self._dest is not None
        try:
            os.replace(self._part, self._dest)
        except OSError as exc:
            self._emit_failed(NetworkError(str(exc)))
            return

        self._part = None
        self.finished.emit(self._dest)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emit_failed(self, error: Exception) -> None:
        self._cleanup_part()
        self.failed.emit(error)

    def _cleanup_part(self) -> None:
        if self._fh is not None:
            with contextlib.suppress(OSError):
                self._fh.close()
            self._fh = None
        if self._part is not None and self._part.exists():
            with contextlib.suppress(OSError):
                self._part.unlink()


def _qurl(url: str):
    from PyQt6.QtCore import QUrl

    return QUrl(url)
