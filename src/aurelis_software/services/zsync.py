"""zsync delta downloader (spec 7.5 step 1).

Pure decision function plus a subprocess-based runner with progress,
cancel, timeout/stall handling, and sha256 verification. Falls back to
the full Downloader on any failure.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from aurelis_software.core.errors import ChecksumMismatch, NetworkError
from aurelis_software.core.models import App
from aurelis_software.services.downloader import Downloader

if TYPE_CHECKING:
    from PyQt6.QtNetwork import QNetworkAccessManager

log = logging.getLogger(__name__)

_CONNECT_TIMEOUT_MS = 15_000
_STALL_TIMEOUT_MS = 30_000
_MIN_FREE_MULTIPLIER = 2


def can_delta(entry: App, installed_path: Path | str | None) -> bool:
    """Return True only when ALL conditions for a delta update hold.

    Conditions (spec 7.5 step 1):
    1. Catalog entry has a zsync_url
    2. The `zsync` binary is found on PATH (shutil.which)
    3. The installed file path is known (not None)
    4. The installed file exists on disk

    This function is pure (no I/O except shutil.which and Path.exists)
    and is tested for each of the 4 conditions.
    """
    if not entry.get("zsync_url"):
        return False
    if shutil.which("zsync") is None:
        return False
    if installed_path is None:
        return False
    return Path(installed_path).exists()


@dataclass
class ZsyncParams:
    """Parameters for zsync execution."""

    zsync_path: str
    args: list[str]
    part_path: Path
    dest_path: Path
    sha256: str | None
    expected_size: int | None
    download_url: str | None
    cache_dir: Path


class ZsyncDownloader(QObject):
    """Run zsync as a subprocess to produce a delta update.

    On any failure (zsync not found, non-zero exit, wrong hash, timeout,
    stall), falls back to a full download via Downloader. Only one fallback
    attempt is made; if that also fails verification, ChecksumMismatch is
    emitted.

    Signals
    -------
    progress(received: int, total: int)
        ``total`` is -1 when unknown (zsync does not always report total).
    finished(path: Path)
        Emitted with the final (non-``.part``) path on success.
    failed(error: AurelisError)
        Emitted on any failure; the ``.part`` file has been deleted.
    """

    progress = pyqtSignal(int, int)
    finished = pyqtSignal(object)  # Path
    failed = pyqtSignal(object)  # AurelisError subclass

    def __init__(
        self,
        cache_dir: Path,
        nam: QNetworkAccessManager | None = None,
        parent: QObject | None = None,
        *,
        stall_timeout_ms: int = 30_000,
    ) -> None:
        super().__init__(parent)
        self._cache_dir = cache_dir
        self._nam = nam
        self._process: QProcess | None = None
        self._params: ZsyncParams | None = None
        self._fallback_dl: Downloader | None = None
        self._fallback_attempted = False
        self._stall_timeout_ms = stall_timeout_ms
        self._stall_timer = QTimer(self)
        self._stall_timer.setSingleShot(True)
        self._stall_timer.timeout.connect(self._check_stall)
        self._last_output_time = 0.0
        self._received = 0
        self._total = -1
        self._failed = False  # Track if we've already emitted a failure

    def start(
        self,
        zsync_url: str,
        installed_path: Path,
        dest: Path,
        *,
        sha256: str | None = None,
        expected_size: int | None = None,
        download_url: str | None = None,
    ) -> None:
        """Begin zsync delta from *installed_path* to *dest* using *zsync_url*.

        If *download_url* is provided, it will be used for fallback to full
        download when zsync fails.
        """
        if self._process is not None:
            log.warning("zsync downloader already running; ignoring start()")
            return

        self._dest = dest
        self._sha256 = sha256
        self._download_url = download_url
        self._expected_size = expected_size
        self._part = dest.parent / (dest.name + ".part")
        self._fallback_attempted = False

        # Free-space check
        if expected_size is not None:
            try:
                free = shutil.disk_usage(dest.parent).free
            except OSError:
                free = shutil.disk_usage(Path.home()).free
            if free < expected_size * _MIN_FREE_MULTIPLIER:
                self._emit_failed(NetworkError(f"Need {expected_size * 2} bytes free, have {free}"))
                return

        dest.parent.mkdir(parents=True, exist_ok=True)

        # Remove any existing .part
        with contextlib.suppress(OSError):
            if self._part.exists():
                self._part.unlink()

        # Find zsync binary
        zsync_path = shutil.which("zsync")
        if zsync_path is None:
            self._emit_failed(NetworkError("zsync binary not found in PATH"))
            return

        # zsync -i <installed> -o <output.part> <url>
        args = ["-i", str(installed_path), "-o", str(self._part), zsync_url]
        log.debug("Starting zsync: %s %s", zsync_path, " ".join(args))

        # Create parameters dataclass
        self._params = ZsyncParams(
            zsync_path=zsync_path,
            args=args,
            part_path=self._part,
            dest_path=dest,
            sha256=sha256,
            expected_size=expected_size,
            download_url=download_url,
            cache_dir=self._cache_dir,
        )

        # Create and configure QProcess
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_ready_read)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

        # Start stall monitoring
        self._last_output_time = time.monotonic()
        self._stall_timer.start(self._stall_timeout_ms)

        # Start the process
        self._process.start(self._params.zsync_path, self._params.args)

    def cancel(self) -> None:
        """Abort the current zsync run and delete the ``.part`` file."""
        if self._process is not None:
            self._process.terminate()
            if not self._process.waitForFinished(2000):
                self._process.kill()
                self._process.waitForFinished(1000)
        if self._fallback_dl is not None:
            self._fallback_dl.cancel()

    def _on_ready_read(self) -> None:
        """Handle stdout data from zsync process."""
        if self._process is None:
            return

        self._last_output_time = time.monotonic()
        data = bytes(self._process.readAllStandardOutput())
        if not data:
            return

        text = data.decode(errors="replace")
        for line in text.splitlines():
            self._parse_progress(line)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        """Handle zsync process completion."""
        self._stall_timer.stop()

        if self._failed or self._process is None or self._params is None:
            return

        fallback = False
        if exit_status == QProcess.ExitStatus.CrashExit:
            log.warning("zsync crashed, falling back to full download")
            fallback = True
        elif exit_code != 0:
            log.warning("zsync exited with code %d, falling back to full download", exit_code)
            fallback = True
        elif not self._params.part_path.exists() or self._params.part_path.stat().st_size == 0:
            log.warning("zsync output missing or empty, falling back to full download")
            fallback = True
        elif self._params.sha256 is not None and not self._verify_sha256():
            log.warning("zsync output sha256 mismatch, falling back to full download")
            fallback = True

        if fallback:
            self._start_fallback()
            return

        # Rename .part -> dest
        try:
            os.replace(self._params.part_path, self._params.dest_path)
        except OSError as exc:
            self._emit_failed(NetworkError(str(exc)))
            return

        self._params = None
        self._process = None
        self.finished.emit(self._dest)

    def _on_error(self, error: QProcess.ProcessError) -> None:
        """Handle QProcess errors."""
        if self._failed:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._emit_failed(NetworkError("Failed to start zsync process"))
        elif error == QProcess.ProcessError.Crashed:
            log.warning("zsync process crashed, falling back to full download")
            self._start_fallback()
        elif error == QProcess.ProcessError.Timedout:
            self._emit_failed(NetworkError("zsync timed out"))
        elif error == QProcess.ProcessError.WriteError:
            self._emit_failed(NetworkError("zsync write error"))
        elif error == QProcess.ProcessError.ReadError:
            self._emit_failed(NetworkError("zsync read error"))
        else:
            self._emit_failed(NetworkError(f"zsync process error: {error}"))

    def _check_stall(self) -> None:
        """Check if zsync has stalled (no output for stall_timeout_ms)."""
        if self._process is None or self._failed:
            return

        if time.monotonic() - self._last_output_time > self._stall_timeout_ms / 1000:
            log.warning("zsync stalled (no output for %d ms)", self._stall_timeout_ms)
            self._failed = True  # Set before waiting to prevent _on_finished fallback
            self._process.terminate()
            if not self._process.waitForFinished(2000):
                self._process.kill()
                self._process.waitForFinished(1000)
            self._emit_failed(NetworkError("zsync timed out (no data received)"))
        else:
            self._stall_timer.start(self._stall_timeout_ms)

    def _parse_progress(self, line: str) -> None:
        """Parse zsync progress output."""
        line = line.strip()
        # Pattern: downloading: 45% (1234567 bytes)
        m = re.search(r"downloading:\s*(\d+)%\s*\((\d+)\s*bytes?\)", line, re.IGNORECASE)
        if m:
            pct = int(m.group(1))
            total = int(m.group(2))
            self._total = total
            self._received = int(total * pct / 100)
            self.progress.emit(self._received, self._total)
            return

        # Pattern: downloaded NNN bytes
        m = re.search(r"downloaded\s+(\d+)\s*bytes?", line, re.IGNORECASE)
        if m:
            self._received = int(m.group(1))
            self.progress.emit(self._received, self._total)
            return

        # Pattern: reading seed file: XX%
        m = re.search(r"reading seed file:\s*(\d+)%", line, re.IGNORECASE)
        if m:
            self.progress.emit(self._received, -1)

    def _verify_sha256(self) -> bool:
        """Verify the .part file's sha256 matches expected."""
        assert self._params is not None
        assert self._params.sha256 is not None

        hasher = hashlib.sha256()
        try:
            with self._params.part_path.open("rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
        except OSError:
            return False

        digest = hasher.hexdigest()
        if digest != self._params.sha256:
            log.warning("sha256 mismatch: expected %s, got %s", self._params.sha256, digest)
            return False
        return True

    def _start_fallback(self) -> None:
        """Start full download fallback using Downloader."""
        if self._fallback_attempted:
            self._emit_failed(NetworkError("fallback already attempted"))
            return
        if not self._download_url:
            self._emit_failed(NetworkError("No download_url available for fallback"))
            return
        if self._nam is None:
            self._emit_failed(
                NetworkError("No QNetworkAccessManager available for fallback download")
            )
            return

        self._fallback_attempted = True

        # Clean up .part from zsync
        with contextlib.suppress(OSError):
            if self._part is not None and self._part.exists():
                self._part.unlink()

        # Start full download
        self._fallback_dl = Downloader(self._nam)
        self._fallback_dl.finished.connect(self._on_fallback_finished)
        self._fallback_dl.failed.connect(self._on_fallback_failed)
        self._fallback_dl.progress.connect(self.progress.emit)

        log.info("Starting full download fallback for %s", self._dest)
        self._fallback_dl.start(
            url=self._download_url,
            dest=self._dest,
            sha256=self._sha256,
            expected_size=self._expected_size,
        )

    def _on_fallback_finished(self, path: Path) -> None:
        log.info("Fallback download finished: %s", path)
        self._fallback_dl = None
        self.finished.emit(path)

    def _on_fallback_failed(self, error: Exception) -> None:
        log.warning("Fallback download failed: %s", error)
        self._fallback_dl = None
        if isinstance(error, ChecksumMismatch):
            self.failed.emit(error)
        else:
            self._emit_failed(error)

    def _emit_failed(self, error: Exception) -> None:
        self._failed = True
        self._cleanup_part()
        self._params = None
        self._process = None
        self.failed.emit(error)

    def _cleanup_part(self) -> None:
        if self._part is not None and self._part.exists():
            with contextlib.suppress(OSError):
                self._part.unlink()


def fetch_update(
    entry: App,
    installed_path: Path,
    cache_dir: Path,
    nam: QNetworkAccessManager,
    *,
    expected_size: int | None = None,
) -> ZsyncDownloader | Downloader:
    """Entry point for P4.3: obtain the updated file (delta or full).

    Returns a ZsyncDownloader that emits finished(path) or failed(error).
    The caller connects to the signals and handles the result.

    Decision logic (spec 7.5 step 1):
    - If can_delta(entry, installed_path): run zsync delta with fallback
    - Otherwise: full download via Downloader

    After zsync: verify sha256 when entry has it. On mismatch, delete .part
    and fall back to ONE full download; if that also fails the hash, fail
    with ChecksumMismatch. Never leave a .part behind on any failure path.
    """
    zsync_url = entry.get("zsync_url")
    download_url = entry.get("download_url")
    sha256 = entry.get("sha256")

    if not download_url:
        msg = "Catalog entry missing download_url"
        raise ValueError(msg)

    dest = cache_dir / f"{entry.id}-{entry.version or 'latest'}.AppImage"

    if can_delta(entry, installed_path):
        log.info("Attempting zsync delta for %s", entry.id)
        downloader = ZsyncDownloader(cache_dir, nam)
        downloader.start(
            zsync_url=zsync_url,
            installed_path=installed_path,
            dest=dest,
            sha256=sha256,
            expected_size=expected_size,
            download_url=download_url,
        )
        return downloader

    log.info("Full download for %s (delta not possible)", entry.id)
    downloader = Downloader(nam)
    downloader.start(
        url=download_url,
        dest=dest,
        sha256=sha256,
        expected_size=expected_size,
    )
    return downloader
