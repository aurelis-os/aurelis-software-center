"""Tests for core/matching.py (section 4.6) - table-driven over every rule."""

from __future__ import annotations

import pytest

from aurelis_software.core.matching import build_origin, match_installed
from aurelis_software.core.models import App, InstalledApp, Source


def _entry(app_id: str, version: str | None = None, sha256: str | None = None, **raw) -> App:
    raw = dict(raw)
    if version is not None:
        raw["version"] = version
    if sha256 is not None:
        raw["sha256"] = sha256
    return App(
        key=f"appimage:{app_id}",
        id=app_id,
        source=Source.APPIMAGE,
        name=app_id,
        summary="",
        version=version,
        raw=raw,
    )


def _inst(
    *,
    id: str = "org.example.app",
    sha256: str | None = None,
    origin: dict | None = None,
) -> InstalledApp:
    return InstalledApp(id=id, source=Source.APPIMAGE, name="App", sha256=sha256, origin=origin)


CATALOG = {
    _entry("org.example.a").id: _entry("org.example.a", sha256="sha-a"),
    _entry("org.example.b").id: _entry("org.example.b"),
}


@pytest.mark.parametrize(
    "installed,expected_kind",
    [
        # Rule 1: origin.catalog_id present -> linked
        (_inst(id="anything", origin={"catalog_id": "org.example.a"}), "linked"),
        # Rule 2: installed sha256 equals catalog entry sha256 -> auto-link
        (_inst(id="unrelated", sha256="sha-a"), "auto_link"),
        # Rule 3: app_id equal, no hash match -> suggest
        (_inst(id="org.example.a", sha256="other"), "suggest"),
        # Rule 4: neither -> unmanaged
        (_inst(id="org.example.unknown", sha256="nope"), "unmanaged"),
        # Rule 4: nothing at all -> unmanaged
        (_inst(id="org.example.unknown"), "unmanaged"),
        # Rule 1 wins over rule 2 when both hold
        (
            _inst(id="org.example.a", sha256="sha-a", origin={"catalog_id": "org.example.a"}),
            "linked",
        ),
        # Rule 1: origin.catalog_id set but the catalog entry is gone -> linked, no entry
        (_inst(id="anything", origin={"catalog_id": "org.example.gone"}), "linked"),
    ],
)
def test_match_installed_rules(installed, expected_kind):
    entries_by_sha256 = {entry.raw.get("sha256"): entry for entry in CATALOG.values()}
    result = match_installed(installed, CATALOG, entries_by_sha256)
    assert result.kind == expected_kind


def test_auto_link_builds_origin_without_nulls():
    entry = _entry("org.example.a", sha256="sha-a")
    entry.raw["version_changed_at"] = "2026-01-01T00:00:00Z"
    result = match_installed(_inst(sha256="sha-a"), {"org.example.a": entry}, {"sha-a": entry})
    assert result.kind == "auto_link"
    assert result.origin == {
        "source": "aurelis-catalog",
        "catalog_id": "org.example.a",
        "sha256": "sha-a",
        "changed_at": "2026-01-01T00:00:00Z",
    }


def test_build_origin_omits_null_values():
    entry = _entry("org.example.a", sha256=None)
    assert build_origin(entry) == {
        "source": "aurelis-catalog",
        "catalog_id": "org.example.a",
    }


def test_suggest_returns_no_origin_until_confirmed():
    entry = _entry("org.example.a", sha256="sha-a")
    result = match_installed(
        _inst(id="org.example.a", sha256="other"),
        {"org.example.a": entry},
        {},
    )
    assert result.kind == "suggest"
    assert result.entry is entry
    assert result.origin is None


def test_linked_returns_entry_without_origin_call():
    entry = _entry("org.example.a", sha256="sha-a")
    result = match_installed(
        _inst(origin={"catalog_id": "org.example.a"}),
        {"org.example.a": entry},
        {"sha-a": entry},
    )
    assert result.kind == "linked"
    assert result.entry is entry
    assert result.origin is None


def test_linked_when_catalog_entry_gone_has_none_entry():
    result = match_installed(
        _inst(origin={"catalog_id": "org.example.gone"}),
        CATALOG,
        {},
    )
    assert result.kind == "linked"
    assert result.entry is None
    assert result.origin is None
