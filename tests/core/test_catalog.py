"""Tests for core/catalog.py (section 4.2)."""

from __future__ import annotations

import json

import pytest

from aurelis_software.core.catalog import CatalogResult, CatalogSchemaTooNew, load_catalog
from aurelis_software.core.models import Source

FIXTURE_DB = __import__("pathlib").Path(__file__).resolve().parent.parent / "fixtures" / "apps.db"


def _write_db(tmp_path, payload) -> object:
    path = tmp_path / "apps.db"
    path.write_text(json.dumps(payload))
    return path


def test_real_catalog_loads_all_22_entries():
    result = load_catalog(FIXTURE_DB)
    assert isinstance(result, CatalogResult)
    assert result.schema_version == 1
    assert result.generated_at == "2023-11-14T22:13:20Z"
    assert len(result.apps) == 22
    assert result.skipped == []
    ids = {app.id for app in result.apps}
    assert "org.kde.kate" in ids
    assert "com.getmailspring.Mailspring" in ids


def test_catalog_app_fields_come_from_real_entry():
    result = load_catalog(FIXTURE_DB)
    kate = next(app for app in result.apps if app.id == "org.kde.kate")
    assert kate.key == "appimage:org.kde.kate"
    assert kate.source == Source.APPIMAGE
    assert kate.name == "Kate"
    assert kate.summary  # non-empty
    assert kate.version == "26.08.2-1"
    assert kate.raw["download_url"]  # non-empty via raw
    assert kate.raw["id"] == "org.kde.kate"


def test_unknown_fields_are_kept_in_raw(tmp_path):
    path = _write_db(
        tmp_path,
        {
            "schema_version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "count": 1,
            "apps": [
                {
                    "id": "org.example.Foo",
                    "name": "Foo",
                    "download_url": "https://example.com/Foo.AppImage",
                    "summary": "A foo",
                    "unknown_field": "kept",
                    "another": 42,
                }
            ],
        },
    )
    result = load_catalog(path)
    assert len(result.apps) == 1
    app = result.apps[0]
    assert app.raw["unknown_field"] == "kept"
    assert app.raw["another"] == 42


def test_missing_optional_fields_are_hidden_safely(tmp_path):
    path = _write_db(
        tmp_path,
        {
            "schema_version": 1,
            "apps": [
                {
                    "id": "org.example.Bare",
                    "name": "Bare",
                    "download_url": "https://example.com/Bare.AppImage",
                }
            ],
        },
    )
    result = load_catalog(path)
    assert len(result.apps) == 1
    app = result.apps[0]
    assert app.summary == ""
    assert app.version is None
    assert app.categories == ()
    assert app.search_blob == "Bare"


def test_malformed_entry_is_skipped(tmp_path):
    path = _write_db(
        tmp_path,
        {
            "schema_version": 1,
            "apps": [
                {"name": "No Id", "download_url": "https://example.com/x.AppImage"},
                {"id": "org.example.NoName", "download_url": "https://example.com/x.AppImage"},
                {"id": "org.example.NoUrl", "name": "NoUrl"},
                {
                    "id": "org.example.Ok",
                    "name": "Ok",
                    "download_url": "https://example.com/Ok.AppImage",
                },
            ],
        },
    )
    result = load_catalog(path)
    assert len(result.apps) == 1
    assert result.apps[0].id == "org.example.Ok"
    assert len(result.skipped) == 3


def test_duplicate_ids_keep_first(tmp_path):
    path = _write_db(
        tmp_path,
        {
            "schema_version": 1,
            "apps": [
                {
                    "id": "org.example.Dup",
                    "name": "First",
                    "download_url": "https://example.com/first.AppImage",
                },
                {
                    "id": "org.example.Dup",
                    "name": "Second",
                    "download_url": "https://example.com/second.AppImage",
                },
            ],
        },
    )
    result = load_catalog(path)
    assert len(result.apps) == 1
    assert result.apps[0].name == "First"
    assert len(result.skipped) == 1
    assert result.skipped[0][1] == "duplicate id"


def test_schema_version_too_new_refuses_load(tmp_path):
    path = _write_db(
        tmp_path,
        {
            "schema_version": 2,
            "apps": [{"id": "x", "name": "X", "download_url": "https://example.com/x.AppImage"}],
        },
    )
    with pytest.raises(CatalogSchemaTooNew) as exc_info:
        load_catalog(path)
    assert exc_info.value.code == "catalog-schema-too-new"
