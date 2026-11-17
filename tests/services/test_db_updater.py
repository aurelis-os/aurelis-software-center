"""Tests for services/db_updater.py (section 5) with a fake HTTP layer.

Tests never touch the network.
"""

from __future__ import annotations

import io
import json
import os
import tarfile
from pathlib import Path

from aurelis_software.core.config import load
from aurelis_software.core.paths import Paths
from aurelis_software.services.db_updater import DbUpdater, HttpResponse

FIXTURE_DB = Path(__file__).resolve().parent.parent / "fixtures" / "apps.db"


def _make_tar_gz(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _apps_db(apps, *, schema_version=1, generated_at="2026-01-01T00:00:00Z") -> bytes:
    payload = {
        "schema_version": schema_version,
        "generated_at": generated_at,
        "count": len(apps),
        "apps": apps,
    }
    return json.dumps(payload).encode()


_ICONS_TAR = _make_tar_gz({"org.kde.kate.png": b"fake-png-bytes"})


def _updater(tmp_path, clock_value=1000.0):
    paths = Paths(
        config_dir=tmp_path / "cfg",
        cache_dir=tmp_path / "cache",
        state_dir=tmp_path / "state",
    )
    config = load(paths)

    def clock():
        return clock_value

    return paths, config, clock


def _fake(catalog_body, icons_body=_ICONS_TAR):
    def fake(url, headers):
        if url.endswith("app-icons.tar.gz"):
            return HttpResponse(200, body=icons_body)
        return HttpResponse(200, body=catalog_body)

    return fake


def test_200_installs_catalog_saves_etag_and_generated_at(tmp_path):
    paths, config, clock = _updater(tmp_path)
    body = _make_tar_gz(
        {
            "apps.db": _apps_db(
                [
                    {
                        "id": "org.kde.kate",
                        "name": "Kate",
                        "summary": "editor",
                        "download_url": "https://example.com/kate.AppImage",
                        "version": "1.0",
                    }
                ]
            )
        }
    )
    fetched = {}

    def fake(url, headers):
        if url.endswith("app-icons.tar.gz"):
            return HttpResponse(200, body=_ICONS_TAR)
        fetched["url"] = url
        fetched["headers"] = dict(headers)
        return HttpResponse(200, etag="etag-1", last_modified="lm-1", body=body)

    updater = DbUpdater(paths, config, fake, clock=clock)
    result = updater.refresh(force=True)

    assert result.changed is True
    assert result.reason == "refreshed"
    assert result.catalog is not None
    assert len(result.catalog.apps) == 1
    assert result.catalog.apps[0].id == "org.kde.kate"
    assert paths.catalog_db.is_file()
    assert fetched["headers"].get("If-None-Match") is None  # no etag on first run

    state = json.loads(paths.state_file.read_text())
    assert state["etag"] == "etag-1"
    assert state["last_modified"] == "lm-1"
    assert state["generated_at"] == "2026-01-01T00:00:00Z"
    assert state["last_check"] == 1000.0


def test_conditional_request_sends_stored_etag(tmp_path):
    paths, config, clock = _updater(tmp_path)
    body = _make_tar_gz({"apps.db": _apps_db([])})
    paths.catalog_db.parent.mkdir(parents=True, exist_ok=True)
    paths.catalog_db.write_bytes(body)
    paths.state_file.parent.mkdir(parents=True, exist_ok=True)
    paths.state_file.write_text(
        json.dumps(
            {
                "last_check": 0.0,
                "etag": "etag-0",
                "last_modified": "lm-0",
                "generated_at": "2026-01-01T00:00:00Z",
            }
        )
    )

    seen = {}

    def fake(url, headers):
        if url.endswith("app-icons.tar.gz"):
            return HttpResponse(200, body=_ICONS_TAR)
        seen["headers"] = dict(headers)
        return HttpResponse(304)

    updater = DbUpdater(paths, config, fake, clock=clock)
    result = updater.refresh(force=True)

    assert result.changed is False
    assert result.reason == "not modified"
    assert seen["headers"]["If-None-Match"] == "etag-0"
    assert seen["headers"]["If-Modified-Since"] == "lm-0"


def test_refresh_not_due_without_force(tmp_path):
    paths, config, clock = _updater(tmp_path)
    calls = []

    def fake(url, headers):
        calls.append(url)
        if url.endswith("app-icons.tar.gz"):
            return HttpResponse(200, body=_ICONS_TAR)
        return HttpResponse(200, body=_make_tar_gz({"apps.db": _apps_db([])}))

    updater = DbUpdater(paths, config, fake, clock=clock)
    first = updater.refresh(force=True)
    assert first.changed is True
    assert len(calls) == 2  # catalog, then icons

    second = updater.refresh(force=False)
    assert second.changed is False
    assert second.reason == "refresh not due"
    assert len(calls) == 2  # no fetch when not due


def test_corrupt_archive_keeps_cache(tmp_path):
    paths, config, clock = _updater(tmp_path)
    paths.catalog_db.parent.mkdir(parents=True, exist_ok=True)
    paths.catalog_db.write_bytes(b'{"schema_version": 1, "apps": []}')

    def fake(url, headers):
        return HttpResponse(200, body=b"not a gzip archive at all")

    updater = DbUpdater(paths, config, fake, clock=clock)
    result = updater.refresh(force=True)

    assert result.changed is False
    assert result.error is not None
    assert paths.catalog_db.read_bytes() == b'{"schema_version": 1, "apps": []}'


def test_schema_too_new_keeps_cache(tmp_path):
    paths, config, clock = _updater(tmp_path)
    paths.catalog_db.parent.mkdir(parents=True, exist_ok=True)
    paths.catalog_db.write_bytes(b'{"schema_version": 1, "apps": []}')

    body = _make_tar_gz({"apps.db": _apps_db([], schema_version=2)})

    def fake(url, headers):
        return HttpResponse(200, body=body)

    updater = DbUpdater(paths, config, fake, clock=clock)
    result = updater.refresh(force=True)

    assert result.changed is False
    assert paths.catalog_db.read_bytes() == b'{"schema_version": 1, "apps": []}'


def test_older_generated_at_is_ignored(tmp_path):
    paths, config, clock = _updater(tmp_path)
    v2 = _make_tar_gz({"apps.db": _apps_db([], generated_at="2026-02-02T00:00:00Z")})
    v1 = _make_tar_gz({"apps.db": _apps_db([], generated_at="2026-01-01T00:00:00Z")})

    def fake_v2(url, headers):
        return HttpResponse(200, body=v2)

    updater = DbUpdater(paths, config, fake_v2, clock=clock)
    first = updater.refresh(force=True)
    assert first.changed is True

    def fake_v1(url, headers):
        return HttpResponse(200, body=v1)

    updater.fetch = fake_v1
    second = updater.refresh(force=True)
    assert second.changed is False
    assert second.reason == "downgrade ignored"


def test_truncated_partial_download_keeps_cache(tmp_path):
    paths, config, clock = _updater(tmp_path)
    paths.catalog_db.parent.mkdir(parents=True, exist_ok=True)
    paths.catalog_db.write_bytes(b'{"schema_version": 1, "apps": []}')

    good = _make_tar_gz({"apps.db": _apps_db([])})
    truncated = good[: len(good) // 2]

    def fake(url, headers):
        return HttpResponse(200, body=truncated)

    updater = DbUpdater(paths, config, fake, clock=clock)
    result = updater.refresh(force=True)

    assert result.changed is False
    assert result.error is not None
    assert paths.catalog_db.read_bytes() == b'{"schema_version": 1, "apps": []}'


def test_simulated_crash_during_swap_keeps_cache(tmp_path, monkeypatch):
    paths, config, clock = _updater(tmp_path)
    v1 = _make_tar_gz({"apps.db": _apps_db([], generated_at="2026-01-01T00:00:00Z")})
    v2 = _make_tar_gz({"apps.db": _apps_db([], generated_at="2026-02-01T00:00:00Z")})

    def fake_v1(url, headers):
        return HttpResponse(200, body=v1)

    updater = DbUpdater(paths, config, fake_v1, clock=clock)
    first = updater.refresh(force=True)
    assert first.changed is True
    before = paths.catalog_db.read_bytes()

    def boom(src, dst):
        msg = "simulated crash"
        raise OSError(msg)

    monkeypatch.setattr(os, "replace", boom)

    def fake_v2(url, headers):
        return HttpResponse(200, body=v2)

    updater.fetch = fake_v2
    second = updater.refresh(force=True)
    assert second.changed is False
    assert second.error is not None
    assert paths.catalog_db.read_bytes() == before


def test_real_fixture_catalog_loads_through_updater_staging(tmp_path):
    """The staging path parses the real 22-entry fixture catalog."""
    paths, config, clock = _updater(tmp_path)
    body = _make_tar_gz({"apps.db": FIXTURE_DB.read_bytes()})

    def fake(url, headers):
        if url.endswith("app-icons.tar.gz"):
            return HttpResponse(200, body=_ICONS_TAR)
        return HttpResponse(200, body=body)

    updater = DbUpdater(paths, config, fake, clock=clock)
    result = updater.refresh(force=True)

    assert result.changed is True
    assert len(result.catalog.apps) == 22
