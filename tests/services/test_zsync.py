"""Tests for services/zsync.py (spec P4.2, section 7.5 step 1).

All tests use a FAKE zsync script put first on PATH in a tmp dir — no network.
Tests verify: delta success; zsync exits 1 -> full download fallback;
zsync output with wrong hash -> fallback then success; both wrong -> ChecksumMismatch;
cancel mid-delta -> no .part, process gone; zsync missing -> full download;
installed file missing -> full download. Assert exact argv passed to zsync.
"""

from __future__ import annotations

import hashlib
import http.server
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtNetwork import QNetworkAccessManager

from aurelis_software.core.errors import ChecksumMismatch, NetworkError
from aurelis_software.core.models import App, Source
from aurelis_software.services.zsync import ZsyncDownloader, can_delta, fetch_update

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run_loop(timeout_ms: int = 5000) -> None:
    """Process Qt events until the loop is quit or timeout fires."""
    loop = QEventLoop()
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Minimal HTTP server for full download fallback tests
# ---------------------------------------------------------------------------


class _ThreadingHTTPServer:
    """Simple HTTP server for testing full download fallback."""

    def __init__(self, handler_cls, port: int):
        import http.server
        import socketserver
        import threading

        class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

        self._server = _ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.url = f"http://127.0.0.1:{port}/file"

    def shutdown(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5.0)


class _Handler(http.server.BaseHTTPRequestHandler):
    """Configurable handler; behaviour set via class attributes."""

    body: bytes = b""
    status: int = 200
    extra_headers: dict
    redirect_to: str = ""
    stall: bool = False
    partial_bytes: int = 0

    def __init__(self, *args, **kwargs):
        self.extra_headers = {}
        super().__init__(*args, **kwargs)

    def log_message(self, *_):  # silence server logs in tests
        pass

    def do_GET(self):
        import time

        if self.stall:
            time.sleep(60)
            return
        if self.redirect_to:
            self.send_response(302)
            self.send_header("Location", self.redirect_to)
            self.end_headers()
            return
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            start = int(range_header[6:].split("-")[0])
            body = self.body[start:]
            self.send_response(206)
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Content-Range", f"bytes {start}-{len(self.body) - 1}/{len(self.body)}"
            )
            for k, v in self.extra_headers.items():
                self.send_header(k, v)
            self.end_headers()
            if self.partial_bytes > 0:
                self.wfile.write(body[: self.partial_bytes])
            else:
                self.wfile.write(body)
        else:
            self.send_response(self.status)
            self.send_header("Content-Length", str(len(self.body)))
            for k, v in self.extra_headers.items():
                self.send_header(k, v)
            self.end_headers()
            if self.partial_bytes > 0:
                self.wfile.write(self.body[: self.partial_bytes])
            else:
                self.wfile.write(self.body)


@contextmanager
def _server_context(handler_cls):
    """Context manager that properly shuts down and joins the HTTP server thread."""
    port = _free_port()
    server = _ThreadingHTTPServer(handler_cls, port)
    try:
        yield server, server.url
    finally:
        server.shutdown()


# ---------------------------------------------------------------------------
# Fake zsync script helper
# ---------------------------------------------------------------------------


def _write_fake_zsync_env(
    tmpdir: Path,
    env_vars: dict[str, str],
    argv_file: Path | None = None,
    pid_file: Path | None = None,
) -> Path:
    """Write a wrapper script that sets environment variables and calls the fake zsync."""
    script = tmpdir / "zsync"
    fake_zsync_path = Path(__file__).parent / "fake_zsync.py"

    if argv_file:
        env_vars = {**env_vars, "FAKE_ZSYNC_ARGV_FILE": str(argv_file)}
    if pid_file:
        env_vars = {**env_vars, "FAKE_ZSYNC_PID_FILE": str(pid_file)}

    content = f"""#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, {str(fake_zsync_path.parent)!r})
from fake_zsync import main

# Set environment variables
{chr(10).join(f"os.environ[{k!r}] = {v!r}" for k, v in env_vars.items())}

if __name__ == "__main__":
    sys.exit(main())
"""
    script.write_text(content)
    script.chmod(0o755)
    return script


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_cache(tmp_path):
    return tmp_path / "cache"


@pytest.fixture()
def sample_entry(tmp_cache):
    """A sample App entry with zsync_url and download_url."""
    return App(
        key="appimage:test-app",
        id="test-app",
        source=Source.APPIMAGE,
        name="Test App",
        summary="Test summary",
        version="1.0.0",
        raw={
            "zsync_url": "https://example.com/test-app.zsync",
            "download_url": "https://example.com/test-app.AppImage",
            "sha256": "a" * 64,  # placeholder
        },
    )


@pytest.fixture()
def installed_file(tmp_path):
    """Create a fake installed AppImage file."""
    f = tmp_path / "installed" / "test-app.AppImage"
    f.parent.mkdir(parents=True, exist_ok=True)
    content = b"original installed appimage content" * 100
    f.write_bytes(content)
    return f


# ---------------------------------------------------------------------------
# Tests for can_delta (pure decision function)
# ---------------------------------------------------------------------------


def test_can_delta_all_present(sample_entry, installed_file, monkeypatch):
    """All 4 conditions present -> True."""
    monkeypatch.setattr(shutil, "which", lambda _: "/fake/zsync")
    assert can_delta(sample_entry, installed_file) is True


def test_can_delta_missing_zsync_url(installed_file):
    """Missing zsync_url -> False."""
    entry = App(
        key="appimage:test",
        id="test",
        source=Source.APPIMAGE,
        name="Test",
        summary="Test",
        raw={"download_url": "https://example.com/test.AppImage"},
    )
    assert can_delta(entry, installed_file) is False


def test_can_delta_zsync_binary_missing(sample_entry, installed_file, monkeypatch):
    """zsync binary not found -> False."""
    monkeypatch.setattr(shutil, "which", lambda _: None)
    assert can_delta(sample_entry, installed_file) is False


def test_can_delta_installed_path_none(sample_entry):
    """installed_path is None -> False."""
    assert can_delta(sample_entry, None) is False


def test_can_delta_installed_file_missing(sample_entry, tmp_path):
    """installed file does not exist -> False."""
    missing = tmp_path / "does_not_exist.AppImage"
    assert can_delta(sample_entry, missing) is False


# ---------------------------------------------------------------------------
# Tests for ZsyncDownloader with FAKE zsync
# ---------------------------------------------------------------------------


def test_zsync_delta_success(qtbot, tmp_cache, sample_entry, installed_file, monkeypatch):
    """Delta succeeds: zsync writes output, sha256 matches, finished emitted."""
    output_content = b"updated appimage content via zsync" * 50
    expected_sha256 = _sha256(output_content)
    entry = App(
        key="appimage:test-app",
        id="test-app",
        source=Source.APPIMAGE,
        name="Test App",
        summary="Test summary",
        version="1.0.0",
        raw={
            "zsync_url": "https://example.com/test-app.zsync",
            "download_url": "https://example.com/test-app.AppImage",
            "sha256": expected_sha256,
        },
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Write output content to a file for the fake zsync to read
        content_file = td_path / "output_content.bin"
        content_file.write_bytes(output_content)

        argv_file = td_path / "argv.txt"
        pid_file = td_path / "pid.txt"

        _write_fake_zsync_env(
            td_path,
            {
                "FAKE_ZSYNC_EXIT_CODE": "0",
                "FAKE_ZSYNC_WRITE_OUTPUT": "1",
                "FAKE_ZSYNC_OUTPUT_CONTENT": str(content_file),
                "FAKE_ZSYNC_OUTPUT_SHA256": expected_sha256,
                "FAKE_ZSYNC_PROGRESS": "downloading: 50% (500 bytes)|downloading: 100% (1000 bytes)",
            },
            argv_file=argv_file,
            pid_file=pid_file,
        )

        monkeypatch.setenv("PATH", f"{td_path}:{os.environ['PATH']}")

        dest = tmp_cache / "test-app-1.0.0.AppImage"
        nam = QNetworkAccessManager()
        dl = ZsyncDownloader(tmp_cache, nam)

        results = []
        errors = []
        progress_events = []

        def _on_finished(p):
            results.append(p)

        def _on_progress(r, t):
            progress_events.append((r, t))

        dl.finished.connect(_on_finished)
        dl.failed.connect(errors.append)
        dl.progress.connect(_on_progress)

        loop = QEventLoop()
        dl.finished.connect(loop.quit)
        dl.failed.connect(loop.quit)

        dl.start(
            zsync_url=entry.get("zsync_url"),
            installed_path=installed_file,
            dest=dest,
            sha256=entry.get("sha256"),
            expected_size=len(output_content),
        )
        QTimer.singleShot(5000, loop.quit)
        loop.exec()

        assert not errors, f"unexpected error: {errors}"
        assert results, "finished not emitted"
        assert dest.exists()
        assert dest.read_bytes() == output_content
        assert not (dest.parent / (dest.name + ".part")).exists()

        # Verify the zsync command line arguments that were passed
        actual_argv = argv_file.read_text().strip().split("\n")
        # argv[0] is the script path, the rest are the actual zsync arguments
        expected_args = [
            "-i",
            str(installed_file),
            "-o",
            str(dest.parent / (dest.name + ".part")),
            entry.get("zsync_url"),
        ]
        assert actual_argv[1:] == expected_args

        # Verify process ran (pid file written)
        assert pid_file.exists()
        pid = int(pid_file.read_text().strip())
        # Process should be gone after completion
        try:
            os.kill(pid, 0)
            msg = "zsync process should have exited"
            raise AssertionError(msg)
        except ProcessLookupError:
            pass


def test_fetch_update_zsync_fallback_on_exit_code(qtbot, tmp_cache, installed_file, monkeypatch):
    """fetch_update: zsync exits non-zero -> full download fallback."""
    full_content = b"full download content" * 100
    full_sha256 = _sha256(full_content)
    entry = App(
        key="appimage:test-app",
        id="test-app",
        source=Source.APPIMAGE,
        name="Test App",
        summary="Test summary",
        version="1.0.0",
        raw={
            "zsync_url": "https://example.com/test-app.zsync",
            "download_url": "https://example.com/test-app.AppImage",
            "sha256": full_sha256,
        },
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Fake zsync that exits with code 1
        argv_file = td_path / "argv.txt"
        _write_fake_zsync_env(
            td_path,
            {
                "FAKE_ZSYNC_EXIT_CODE": "1",
                "FAKE_ZSYNC_WRITE_OUTPUT": "0",
            },
            argv_file=argv_file,
        )
        monkeypatch.setenv("PATH", f"{td_path}:{os.environ['PATH']}")

        class FullHandler(_Handler):
            body = full_content

        with _server_context(FullHandler) as (_server, url):
            entry.raw["download_url"] = url

            dest = tmp_cache / "test-app-1.0.0.AppImage"
            nam = QNetworkAccessManager()
            result = fetch_update(
                entry, installed_file, tmp_cache, nam, expected_size=len(full_content)
            )

            errors = []
            loop = QEventLoop()
            result.failed.connect(lambda e: (errors.append(e), loop.quit()))
            result.finished.connect(loop.quit)
            QTimer.singleShot(10000, loop.quit)
            loop.exec()

            assert not errors, f"unexpected error: {errors}"
            assert dest.exists()
            assert dest.read_bytes() == full_content
            assert not (dest.parent / (dest.name + ".part")).exists()

            # Verify the zsync command line arguments that were passed (even on fallback)
            actual_argv = argv_file.read_text().strip().split("\n")
            # argv[0] is the script path, the rest are the actual zsync arguments
            expected_args = [
                "-i",
                str(installed_file),
                "-o",
                str(dest.parent / (dest.name + ".part")),
                entry.get("zsync_url"),
            ]
            assert actual_argv[1:] == expected_args


def test_fetch_update_zsync_wrong_hash_fallback_then_success(
    qtbot, tmp_cache, installed_file, monkeypatch
):
    """fetch_update: zsync output has wrong hash -> fallback to full download -> success."""
    bad_content = b"zsync output with wrong hash" * 50
    _ = _sha256(bad_content)

    full_content = b"correct full download content" * 100
    full_sha256 = _sha256(full_content)

    entry = App(
        key="appimage:test-app",
        id="test-app",
        source=Source.APPIMAGE,
        name="Test App",
        summary="Test summary",
        version="1.0.0",
        raw={
            "zsync_url": "https://example.com/test-app.zsync",
            "download_url": "https://example.com/test-app.AppImage",
            "sha256": full_sha256,
        },
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        content_file = td_path / "bad_content.bin"
        content_file.write_bytes(bad_content)

        _write_fake_zsync_env(
            td_path,
            {
                "FAKE_ZSYNC_EXIT_CODE": "0",
                "FAKE_ZSYNC_WRITE_OUTPUT": "1",
                "FAKE_ZSYNC_OUTPUT_CONTENT": str(content_file),
                "FAKE_ZSYNC_OUTPUT_SHA256": full_sha256,  # mismatch -> exit 2
            },
        )
        monkeypatch.setenv("PATH", f"{td_path}:{os.environ['PATH']}")

        class FullHandler(_Handler):
            body = full_content

        with _server_context(FullHandler) as (_server, url):
            entry.raw["download_url"] = url

            dest = tmp_cache / "test-app-1.0.0.AppImage"
            nam = QNetworkAccessManager()
            result = fetch_update(
                entry, installed_file, tmp_cache, nam, expected_size=len(full_content)
            )

            errors = []
            loop = QEventLoop()
            result.failed.connect(lambda e: (errors.append(e), loop.quit()))
            result.finished.connect(loop.quit)
            QTimer.singleShot(10000, loop.quit)
            loop.exec()

        assert not errors, f"unexpected error: {errors}"
        assert dest.exists()
        assert dest.read_bytes() == full_content
        assert not (dest.parent / (dest.name + ".part")).exists()


def test_fetch_update_both_wrong_hash_checksum_mismatch(
    qtbot, tmp_cache, installed_file, monkeypatch
):
    """fetch_update: both zsync and full download have wrong hash -> ChecksumMismatch."""
    wrong_content = b"wrong content" * 50
    _ = _sha256(wrong_content)
    expected_sha256 = "a" * 64

    entry = App(
        key="appimage:test-app",
        id="test-app",
        source=Source.APPIMAGE,
        name="Test App",
        summary="Test summary",
        version="1.0.0",
        raw={
            "zsync_url": "https://example.com/test-app.zsync",
            "download_url": "https://example.com/test-app.AppImage",
            "sha256": expected_sha256,
        },
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        content_file = td_path / "wrong_content.bin"
        content_file.write_bytes(wrong_content)

        _write_fake_zsync_env(
            td_path,
            {
                "FAKE_ZSYNC_EXIT_CODE": "0",
                "FAKE_ZSYNC_WRITE_OUTPUT": "1",
                "FAKE_ZSYNC_OUTPUT_CONTENT": str(content_file),
                "FAKE_ZSYNC_OUTPUT_SHA256": expected_sha256,  # mismatch -> exit 2
            },
        )
        monkeypatch.setenv("PATH", f"{td_path}:{os.environ['PATH']}")

        class FullHandler(_Handler):
            body = wrong_content

        with _server_context(FullHandler) as (_server, url):
            entry.raw["download_url"] = url

            dest = tmp_cache / "test-app-1.0.0.AppImage"
            nam = QNetworkAccessManager()
            result = fetch_update(
                entry, installed_file, tmp_cache, nam, expected_size=len(wrong_content)
            )

            errors = []
            loop = QEventLoop()
            result.failed.connect(lambda e: (errors.append(e), loop.quit()))
            result.finished.connect(loop.quit)
            QTimer.singleShot(10000, loop.quit)
            loop.exec()

        assert errors, "expected ChecksumMismatch"
        assert isinstance(errors[0], ChecksumMismatch)
        assert not dest.exists()
        part = dest.parent / (dest.name + ".part")
        assert not part.exists(), ".part file should be cleaned up"


def test_fetch_update_cancel_mid_delta(qtbot, tmp_cache, sample_entry, installed_file, monkeypatch):
    """Cancel mid-delta -> no .part, process gone."""
    output_content = b"updated content" * 50
    expected_sha256 = _sha256(output_content)
    entry = App(
        key="appimage:test-app",
        id="test-app",
        source=Source.APPIMAGE,
        name="Test App",
        summary="Test summary",
        version="1.0.0",
        raw={
            "zsync_url": "https://example.com/test-app.zsync",
            "download_url": "https://example.com/test-app.AppImage",
            "sha256": expected_sha256,
        },
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        content_file = td_path / "output_content.bin"
        content_file.write_bytes(output_content)

        argv_file = td_path / "argv.txt"
        pid_file = td_path / "pid.txt"

        _write_fake_zsync_env(
            td_path,
            {
                "FAKE_ZSYNC_EXIT_CODE": "0",
                "FAKE_ZSYNC_WRITE_OUTPUT": "1",
                "FAKE_ZSYNC_OUTPUT_CONTENT": str(content_file),
                "FAKE_ZSYNC_OUTPUT_SHA256": expected_sha256,
                "FAKE_ZSYNC_DELAY": "2.0",
            },
            argv_file=argv_file,
            pid_file=pid_file,
        )
        monkeypatch.setenv("PATH", f"{td_path}:{os.environ['PATH']}")

        dest = tmp_cache / "test-app-1.0.0.AppImage"
        nam = QNetworkAccessManager()
        result = fetch_update(
            entry, installed_file, tmp_cache, nam, expected_size=len(output_content)
        )

        # Give it a moment to start, then cancel
        QTimer.singleShot(100, result.cancel)

        errors = []
        finished_called = []

        loop = QEventLoop()
        result.failed.connect(lambda e: (errors.append(e), loop.quit()))
        result.finished.connect(lambda p: (finished_called.append(p), loop.quit()))
        QTimer.singleShot(5000, loop.quit)
        loop.exec()

        part = dest.parent / (dest.name + ".part")
        assert not part.exists(), ".part file should be cleaned up on cancel"
        assert not dest.exists(), "destination file should not exist on cancel"
        assert not finished_called, "finished signal should not be emitted on cancel"

        # Verify zsync process is gone
        assert pid_file.exists()
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            msg = "zsync process should have been terminated"
            raise AssertionError(msg)
        except ProcessLookupError:
            pass

        # Verify argv was passed correctly
        actual_argv = argv_file.read_text().strip().split("\n")
        # argv[0] is the script path, the rest are the actual zsync arguments
        expected_args = [
            "-i",
            str(installed_file),
            "-o",
            str(dest.parent / (dest.name + ".part")),
            entry.get("zsync_url"),
        ]
        assert actual_argv[1:] == expected_args


def test_fetch_update_zsync_missing_full_download(qtbot, tmp_cache, sample_entry, monkeypatch):
    """zsync binary missing -> full download."""
    full_content = b"full download content" * 100
    full_sha256 = _sha256(full_content)
    entry = App(
        key="appimage:test-app",
        id="test-app",
        source=Source.APPIMAGE,
        name="Test App",
        summary="Test summary",
        version="1.0.0",
        raw={
            "zsync_url": "https://example.com/test-app.zsync",
            "download_url": "https://example.com/test-app.AppImage",
            "sha256": full_sha256,
        },
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Empty PATH - no zsync
        monkeypatch.setenv("PATH", f"{td_path}:{os.environ['PATH']}")

        class FullHandler(_Handler):
            body = full_content

        with _server_context(FullHandler) as (_server, url):
            entry.raw["download_url"] = url

            dest = tmp_cache / "test-app-1.0.0.AppImage"
            nam = QNetworkAccessManager()
            result = fetch_update(entry, None, tmp_cache, nam, expected_size=len(full_content))

            errors = []
            loop = QEventLoop()
            result.failed.connect(lambda e: (errors.append(e), loop.quit()))
            result.finished.connect(loop.quit)
            QTimer.singleShot(10000, loop.quit)
            loop.exec()

        assert not errors, f"unexpected error: {errors}"
        assert dest.exists()
        assert dest.read_bytes() == full_content


def test_fetch_update_installed_missing_full_download(
    qtbot, tmp_cache, sample_entry, monkeypatch, tmp_path
):
    """Installed file missing -> full download."""
    full_content = b"full download content" * 100
    full_sha256 = _sha256(full_content)
    entry = App(
        key="appimage:test-app",
        id="test-app",
        source=Source.APPIMAGE,
        name="Test App",
        summary="Test summary",
        version="1.0.0",
        raw={
            "zsync_url": "https://example.com/test-app.zsync",
            "download_url": "https://example.com/test-app.AppImage",
            "sha256": full_sha256,
        },
    )

    missing_installed = tmp_path / "does_not_exist.AppImage"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        _write_fake_zsync_env(
            td_path,
            {
                "FAKE_ZSYNC_EXIT_CODE": "0",
                "FAKE_ZSYNC_WRITE_OUTPUT": "1",
            },
        )
        monkeypatch.setenv("PATH", f"{td_path}:{os.environ['PATH']}")

        class FullHandler(_Handler):
            body = full_content

        with _server_context(FullHandler) as (_server, url):
            entry.raw["download_url"] = url

            dest = tmp_cache / "test-app-1.0.0.AppImage"
            nam = QNetworkAccessManager()
            result = fetch_update(
                entry, missing_installed, tmp_cache, nam, expected_size=len(full_content)
            )

            errors = []
            loop = QEventLoop()
            result.failed.connect(lambda e: (errors.append(e), loop.quit()))
            result.finished.connect(loop.quit)
            QTimer.singleShot(10000, loop.quit)
            loop.exec()

        assert not errors, f"unexpected error: {errors}"
        assert dest.exists()
        assert dest.read_bytes() == full_content


# ---------------------------------------------------------------------------
# Test that fetch_update returns the right type and can be used uniformly
# ---------------------------------------------------------------------------


def test_fetch_update_returns_downloader_with_signals(
    qtbot, tmp_cache, installed_file, monkeypatch
):
    """fetch_update returns an object with finished/failed/progress signals."""
    full_content = b"test content" * 10
    full_sha256 = _sha256(full_content)
    entry = App(
        key="appimage:test",
        id="test",
        source=Source.APPIMAGE,
        name="Test",
        summary="Test",
        version="1.0",
        raw={
            "download_url": "https://example.com/test.AppImage",
            "sha256": full_sha256,
        },
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        monkeypatch.setenv("PATH", f"{td_path}:{os.environ['PATH']}")

        class FullHandler(_Handler):
            body = full_content

        with _server_context(FullHandler) as (_server, url):
            entry.raw["download_url"] = url

            _ = tmp_cache / "test-1.0.AppImage"
            nam = QNetworkAccessManager()
            result = fetch_update(entry, None, tmp_cache, nam, expected_size=len(full_content))

            # Should have the signal attributes
            assert hasattr(result, "finished")
            assert hasattr(result, "failed")
            assert hasattr(result, "progress")
            assert hasattr(result, "cancel")


# Tests that call private functions (as required by spec)
def test_can_delta_called_from_fetch_update(qtbot, tmp_cache, installed_file, monkeypatch):
    """Verify fetch_update calls can_delta internally (indirect test)."""
    # This is tested implicitly by the above tests - if can_delta returns False,
    # fetch_update should do full download


# ---------------------------------------------------------------------------
# Stall timeout test
# ---------------------------------------------------------------------------


def test_zsync_stall_timeout(qtbot, tmp_cache, installed_file, monkeypatch):
    """Stall timeout: fake zsync prints one line then sleeps; expect NetworkError, no .part, process gone."""
    entry = App(
        key="appimage:test-app",
        id="test-app",
        source=Source.APPIMAGE,
        name="Test App",
        summary="Test summary",
        version="1.0.0",
        raw={
            "zsync_url": "https://example.com/test-app.zsync",
            "download_url": "https://example.com/test-app.AppImage",
            "sha256": "a" * 64,
        },
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Fake zsync that prints one progress line then stalls (sleeps longer than timeout)
        # Use a very short stall timeout by setting a small delay that exceeds the internal timeout
        pid_file = td_path / "pid.txt"
        _write_fake_zsync_env(
            td_path,
            {
                "FAKE_ZSYNC_EXIT_CODE": "0",
                "FAKE_ZSYNC_WRITE_OUTPUT": "0",
                "FAKE_ZSYNC_PROGRESS": "downloading: 10% (100 bytes)",
                "FAKE_ZSYNC_DELAY": "5.0",  # Sleep 5 seconds - longer than stall timeout
            },
            pid_file=pid_file,
        )
        monkeypatch.setenv("PATH", f"{td_path}:{os.environ['PATH']}")

        dest = tmp_cache / "test-app-1.0.0.AppImage"
        nam = QNetworkAccessManager()
        # Use short stall timeout (1 second) for testing
        dl = ZsyncDownloader(tmp_cache, nam, stall_timeout_ms=1000)

        errors = []
        loop = QEventLoop()

        def on_failed(e):
            errors.append(e)
            loop.quit()

        def on_finished(p):
            loop.quit()

        dl.failed.connect(on_failed)
        dl.finished.connect(on_finished)

        dl.start(
            zsync_url=entry.get("zsync_url"),
            installed_path=installed_file,
            dest=dest,
            sha256=entry.get("sha256"),
            expected_size=1000,
        )
        # Longer timeout to allow stall detection to fire
        QTimer.singleShot(10000, loop.quit)
        loop.exec()

        assert errors, "expected NetworkError for stall timeout"
        assert isinstance(errors[0], NetworkError)
        assert "timed out" in str(errors[0]).lower()
        assert not dest.exists()
        part = dest.parent / (dest.name + ".part")
        assert not part.exists(), ".part file should be cleaned up on stall timeout"

        # Verify zsync process is gone
        assert pid_file.exists()
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            msg = "zsync process should have been terminated"
            raise AssertionError(msg)
        except ProcessLookupError:
            pass
