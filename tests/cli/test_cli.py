"""Tests for the dev CLI ``python -m aurelis_software.cli`` (section P1.8)."""

from __future__ import annotations

import io
import json
import tarfile

from aurelis_software.cli import main
from aurelis_software.services.db_updater import HttpResponse

FIXTURE_DB = __import__("pathlib").Path(__file__).resolve().parent.parent / "fixtures" / "apps.db"


def _make_tar_gz(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _xdg_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def test_search_kate_against_real_fixture(capsys):
    code = main(["search", "kate", "--catalog", str(FIXTURE_DB)])
    assert code == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].startswith("1 results") or lines[0].startswith("2 results")
    assert "org.kde.kate" in out
    assert out.splitlines()[1].startswith("org.kde.kate")


def test_show_kate(capsys):
    code = main(["show", "org.kde.kate", "--catalog", str(FIXTURE_DB)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Kate" in out
    assert "26.08.2-1" in out


def test_show_unknown_id(capsys):
    code = main(["show", "org.example.nope", "--catalog", str(FIXTURE_DB)])
    assert code == 1
    err = capsys.readouterr().err
    assert "unknown id" in err


def test_catalog_list_real_fixture(capsys):
    code = main(["catalog", "list", "--catalog", str(FIXTURE_DB)])
    assert code == 0
    out = capsys.readouterr().out
    assert "apps=22" in out
    assert out.count("org.kde.") >= 1


def test_catalog_refresh_with_fake_http(tmp_path, monkeypatch, capsys):
    _xdg_tmp(tmp_path, monkeypatch)

    def fake_fetch(url, headers):
        if url.endswith("app-icons.tar.gz"):
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                info = tarfile.TarInfo("org.kde.kate.png")
                data = b"fake-png"
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            return HttpResponse(200, body=buf.getvalue())

        payload = {
            "schema_version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "count": 1,
            "apps": [
                {
                    "id": "org.kde.kate",
                    "name": "Kate",
                    "summary": "editor",
                    "download_url": "https://example.com/kate.AppImage",
                }
            ],
        }
        catalog = json.dumps(payload).encode()
        return HttpResponse(200, etag="etag-1", body=_make_tar_gz({"apps.db": catalog}))

    monkeypatch.setattr("aurelis_software.cli.url_fetch", fake_fetch)
    code = main(["catalog", "refresh", "--force"])
    assert code == 0
    out = capsys.readouterr().out
    assert "refreshed" in out


def test_missing_catalog_prints_to_stderr_and_exits_one(capsys):
    code = main(["catalog", "list", "--catalog", "/nonexistent/apps.db"])
    assert code == 1
    err = capsys.readouterr().err
    assert "no catalog cache; run `catalog refresh`" in err


def test_missing_catalog_search_exits_one(capsys):
    code = main(["search", "kate", "--catalog", "/nonexistent/apps.db"])
    assert code == 1
    err = capsys.readouterr().err
    assert "no catalog cache; run `catalog refresh`" in err


def test_missing_catalog_show_exits_one(capsys):
    code = main(["show", "org.kde.kate", "--catalog", "/nonexistent/apps.db"])
    assert code == 1
    err = capsys.readouterr().err
    assert "no catalog cache; run `catalog refresh`" in err
