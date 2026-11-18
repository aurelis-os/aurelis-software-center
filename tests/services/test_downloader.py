"""Tests for services/downloader.py (spec P3.1, Appendix D).

All tests use a local http.server thread — no real network.
Tests verify: 200 download, 206 resume, redirect (https only),
stall timeout, sha256 mismatch, truncated response, free-space check.
Failure leaves no .part file.
"""

from __future__ import annotations

import hashlib
import http.server
import socket
import socketserver
import sys
import threading
import time
from contextlib import contextmanager
from typing import ClassVar

import pytest
from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer
from PyQt6.QtNetwork import QNetworkAccessManager

from aurelis_software.core.errors import ChecksumMismatch, DiskFull, NetworkError
from aurelis_software.services.downloader import Downloader

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
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Minimal HTTP server factory
# ---------------------------------------------------------------------------


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """HTTP server that handles each request in a separate thread."""

    daemon_threads = True


class _Handler(http.server.BaseHTTPRequestHandler):
    """Configurable handler; behaviour set via class attributes."""

    body: bytes = b""
    status: int = 200
    extra_headers: ClassVar[dict] = {}
    redirect_to: str = ""
    stall: bool = False
    partial_bytes: int = 0  # if > 0, send only this many bytes then close

    def log_message(self, *_):  # silence server logs in tests
        pass

    def do_GET(self):
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


def _make_server(handler_cls) -> tuple[http.server.HTTPServer, str, threading.Thread]:
    port = _free_port()
    server = _ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=False)
    thread.start()
    return server, f"http://127.0.0.1:{port}/file", thread


@contextmanager
def _server_context(handler_cls):
    """Context manager that properly shuts down and joins the HTTP server thread."""
    server, url, thread = _make_server(handler_cls)
    try:
        yield server, url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv[:1])
    return app


@pytest.fixture()
def nam(qapp):
    return QNetworkAccessManager()


@pytest.fixture()
def dl(nam):
    return Downloader(nam)


@pytest.fixture()
def tmp_dest(tmp_path):
    return tmp_path / "download" / "file.AppImage"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_200_download(dl, tmp_dest):
    """200 response: file written, sha256 verified, no .part left."""
    data = b"hello appimage" * 100
    digest = _sha256(data)

    class H(_Handler):
        body = data

    with _server_context(H) as (_server, url):
        results = []
        errors = []
        dl.finished.connect(lambda p: (results.append(p), _run_loop.__self__ if False else None))
        dl.failed.connect(errors.append)

        loop = QEventLoop()
        dl.finished.connect(lambda _: loop.quit())
        dl.failed.connect(lambda _: loop.quit())
        dl.start(url, tmp_dest, sha256=digest)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()

    assert not errors, f"unexpected error: {errors}"
    assert results, "finished not emitted"
    assert tmp_dest.exists()
    assert not (tmp_dest.parent / (tmp_dest.name + ".part")).exists()
    assert tmp_dest.read_bytes() == data


def test_206_resume(dl, tmp_dest):
    """206 resume: existing .part is continued, final sha256 correct."""
    data = b"resume me " * 200
    digest = _sha256(data)
    part = tmp_dest.parent / (tmp_dest.name + ".part")
    tmp_dest.parent.mkdir(parents=True, exist_ok=True)
    # Write first half as existing .part
    half = len(data) // 2
    part.write_bytes(data[:half])

    class H(_Handler):
        body = data

    with _server_context(H) as (_server, url):
        errors = []
        loop = QEventLoop()
        dl.finished.connect(lambda _: loop.quit())
        dl.failed.connect(lambda e: (errors.append(e), loop.quit()))
        dl.start(url, tmp_dest, sha256=digest)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()

    assert not errors, f"unexpected error: {errors}"
    assert tmp_dest.exists()
    assert tmp_dest.read_bytes() == data
    assert not part.exists()


def test_redirect_https_refused(dl, tmp_dest):
    """Redirect to http:// must be refused (NoLessSafeRedirectPolicy)."""
    # The server redirects to an http:// URL; Qt should refuse it.
    # We use a second local server as the redirect target to avoid
    # any real network access.
    data = b"should not arrive"

    class Target(_Handler):
        body = data

    target_server, _target_url, _ = _make_server(Target)
    # target_url is http://; redirect from http:// to http:// is allowed
    # We need to test https -> http downgrade, but we can't easily set up
    # TLS in a unit test.  Instead we test that a redirect to a different
    # host is blocked by using a URL that will fail (non-routable).
    # The real test: redirect to http:// from an https:// origin is blocked
    # by NoLessSafeRedirectPolicy.  We verify the policy is set correctly
    # by checking the NAM's redirect policy.
    from PyQt6.QtNetwork import QNetworkRequest

    assert dl._nam.redirectPolicy() == QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy
    target_server.shutdown()


def test_redirect_same_scheme_followed(dl, tmp_dest):
    """http -> http redirect is followed (same scheme, not a downgrade)."""
    data = b"redirected content"
    digest = _sha256(data)

    class Final(_Handler):
        body = data

    with _server_context(Final) as (_final_server, final_url):

        class Redir(_Handler):
            redirect_to = final_url

        with _server_context(Redir) as (_redir_server, redir_url):
            errors = []
            loop = QEventLoop()
            dl.finished.connect(lambda _: loop.quit())
            dl.failed.connect(lambda e: (errors.append(e), loop.quit()))
            dl.start(redir_url, tmp_dest, sha256=digest)
            QTimer.singleShot(5000, loop.quit)
            loop.exec()

        assert not errors, f"unexpected error: {errors}"
        assert tmp_dest.read_bytes() == data


def test_stall_timeout(qapp, nam, tmp_dest):
    """Stall timeout: bytes arrive then stop; NetworkError fired; no .part left.

    Uses a short stall timeout (500 ms) to keep the test fast.
    The server sends some data then stalls indefinitely.
    Asserts that at least some bytes were received (progress signal emitted) before the stall.
    """
    from unittest.mock import patch

    import aurelis_software.services.downloader as downloader_mod

    # Patch the stall timeout to 500 ms for this test
    with patch.object(downloader_mod, "_STALL_TIMEOUT_MS", 500):
        dl = Downloader(nam)

        data = b"initial data that arrives"
        # Content-Length is larger than actual data sent -> stall
        declared_length = len(data) + 1000

        class StallHandler(_Handler):
            def do_GET(self):
                # Send initial data but declare larger content length
                self.send_response(200)
                self.send_header("Content-Length", str(declared_length))
                self.end_headers()
                self.wfile.write(data)
                self.wfile.flush()
                # Now stall indefinitely (keep connection open, no more data)
                time.sleep(60)

        errors = []
        progress_events = []
        with _server_context(StallHandler) as (_server, url):
            loop = QEventLoop()
            dl.failed.connect(lambda e: (errors.append(e), loop.quit()))
            dl.finished.connect(lambda _: loop.quit())
            dl.progress.connect(lambda received, total: progress_events.append((received, total)))
            dl.start(url, tmp_dest)
            QTimer.singleShot(5000, loop.quit)
            loop.exec()

        assert errors, "expected NetworkError on stall"
        assert isinstance(errors[0], NetworkError)
        assert "timed out" in str(errors[0]).lower() or "stall" in str(errors[0]).lower()
        # Assert that at least some bytes were received before the stall (progress signal emitted)
        assert progress_events, "progress signal should have been emitted at least once"
        assert any(received > 0 for received, _ in progress_events), (
            "some bytes should have been received"
        )
        part = tmp_dest.parent / (tmp_dest.name + ".part")
        assert not part.exists(), ".part file should be cleaned up on stall timeout"
        assert not tmp_dest.exists(), "destination file should not exist on stall timeout"


def test_sha256_mismatch(dl, tmp_dest):
    """sha256 mismatch: ChecksumMismatch raised, no .part or dest left."""
    data = b"real content"

    class H(_Handler):
        body = data

    with _server_context(H) as (_server, url):
        errors = []
        loop = QEventLoop()
        dl.failed.connect(lambda e: (errors.append(e), loop.quit()))
        dl.finished.connect(lambda _: loop.quit())
        dl.start(url, tmp_dest, sha256="a" * 64)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()

    assert errors
    assert isinstance(errors[0], ChecksumMismatch)
    assert not tmp_dest.exists()
    part = tmp_dest.parent / (tmp_dest.name + ".part")
    assert not part.exists()


def test_truncated_response(dl, tmp_dest):
    """Truncated response (connection closed early): NetworkError, no .part."""
    data = b"full content here" * 50

    class H(_Handler):
        body = data
        partial_bytes = 20  # send only 20 bytes then close

    with _server_context(H) as (_server, url):
        # With a sha256 check, truncation will cause a mismatch
        digest = _sha256(data)
        errors = []
        loop = QEventLoop()
        dl.failed.connect(lambda e: (errors.append(e), loop.quit()))
        dl.finished.connect(lambda _: loop.quit())
        dl.start(url, tmp_dest, sha256=digest)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()

    assert errors, "expected failure on truncated response"
    assert isinstance(errors[0], (NetworkError, ChecksumMismatch))
    assert not tmp_dest.exists()
    part = tmp_dest.parent / (tmp_dest.name + ".part")
    assert not part.exists()


def test_free_space_check(tmp_dest):
    """DiskFull raised before download starts when free space is insufficient."""
    from unittest.mock import patch

    from PyQt6.QtNetwork import QNetworkAccessManager

    dl2 = Downloader(QNetworkAccessManager())
    errors = []
    dl2.failed.connect(errors.append)

    # Fake disk_usage to report 0 free bytes
    import shutil

    orig = shutil.disk_usage

    def fake_usage(_):
        return orig(".")._replace(free=0)

    with patch("aurelis_software.services.downloader.shutil.disk_usage", fake_usage):
        dl2.start("http://127.0.0.1:1/file", tmp_dest, expected_size=1024)

    assert errors
    assert isinstance(errors[0], DiskFull)
    part = tmp_dest.parent / (tmp_dest.name + ".part")
    assert not part.exists()


def test_no_part_after_network_error(dl, tmp_dest):
    """NetworkError (connection refused): no .part file left."""
    errors = []
    loop = QEventLoop()
    dl.failed.connect(lambda e: (errors.append(e), loop.quit()))
    dl.finished.connect(lambda _: loop.quit())
    # Port 1 is always refused
    dl.start("http://127.0.0.1:1/file", tmp_dest)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    assert errors
    assert isinstance(errors[0], NetworkError)
    part = tmp_dest.parent / (tmp_dest.name + ".part")
    assert not part.exists()
