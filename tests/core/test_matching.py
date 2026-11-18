"""Tests for core/matching.py (P3.8)."""

from __future__ import annotations

from aurelis_software.core.matching import MatchKind, match_installed_to_catalog
from aurelis_software.core.models import App, InstalledApp, Source


def _catalog_app(
    app_id: str, sha256: str | None = None, raw_data: dict | None = None, **raw
) -> App:
    """Create a catalog App for testing."""
    if raw_data is not None:
        raw = dict(raw_data)
    if sha256 is not None:
        raw = dict(raw)
        raw["sha256"] = sha256
    return App(
        key=f"appimage:{app_id}",
        id=app_id,
        source=Source.APPIMAGE,
        name=app_id,
        summary="",
        version="1.0",
        raw=raw,
    )


def _installed_app(
    app_id: str,
    origin: dict | None = None,
    sha256: str | None = None,
    **kwargs,
) -> InstalledApp:
    """Create an InstalledApp for testing."""
    defaults = {
        "id": app_id,
        "source": Source.APPIMAGE,
        "name": app_id,
        "version": "1.0",
        "managed_name": app_id,
        "path": f"/home/user/Applications/{app_id}.AppImage",
        "role": "primary",
        "sha256": sha256,
        "update_policy": "auto",
        "self_managed": False,
        "origin": origin,
        "locked": False,
        "pending": None,
        "previous": (),
    }
    defaults.update(kwargs)
    return InstalledApp(**defaults)


# ---------------------------------------------------------------------------
# Rule 1: origin match
# ---------------------------------------------------------------------------
def test_match_by_origin():
    """Origin match takes precedence (highest confidence)."""
    catalog = [_catalog_app("org.kde.kate", sha256="aaa")]
    installed = _installed_app("different-id", origin={"catalog_id": "org.kde.kate"})

    match = match_installed_to_catalog(installed, catalog)

    assert match.kind == MatchKind.ORIGIN
    assert match.confidence == 1.0
    assert match.catalog_app.id == "org.kde.kate"


def test_match_by_origin_over_sha256():
    """Origin beats sha256 even if sha256 matches a different app."""
    catalog = [
        _catalog_app("org.kde.kate", sha256="aaa"),
        _catalog_app("org.gimp.gimp", sha256="bbb"),
    ]
    # Installed has origin pointing to kate, but file sha256 matches gimp
    installed = _installed_app("some-id", origin={"catalog_id": "org.kde.kate"}, sha256="bbb")

    match = match_installed_to_catalog(installed, catalog, file_sha256="bbb")

    assert match.kind == MatchKind.ORIGIN
    assert match.catalog_app.id == "org.kde.kate"


# ---------------------------------------------------------------------------
# Rule 2: sha256 match
# ---------------------------------------------------------------------------
def test_match_by_sha256():
    """File sha256 matches catalog entry."""
    catalog = [_catalog_app("org.kde.kate", sha256="aaa")]
    installed = _installed_app("org.kde.kate", sha256="aaa")

    match = match_installed_to_catalog(installed, catalog, file_sha256="aaa")

    assert match.kind == MatchKind.SHA256
    assert match.confidence == 0.95
    assert match.catalog_app.id == "org.kde.kate"


def test_sha256_case_insensitive():
    """SHA256 comparison is case-insensitive."""
    catalog = [_catalog_app("org.kde.kate", sha256="AAA")]
    installed = _installed_app("org.kde.kate", sha256="aaa")

    match = match_installed_to_catalog(installed, catalog, file_sha256="AAA")

    assert match.kind == MatchKind.SHA256


def test_sha256_no_match_falls_through():
    """SHA256 mismatch falls through to app_id match."""
    catalog = [_catalog_app("org.kde.kate", sha256="aaa")]
    installed = _installed_app("org.kde.kate", sha256="bbb")

    match = match_installed_to_catalog(installed, catalog, file_sha256="bbb")

    assert match.kind == MatchKind.APP_ID


# ---------------------------------------------------------------------------
# Rule 3: app_id match
# ---------------------------------------------------------------------------
def test_match_by_app_id_exact():
    """Exact app_id match in catalog."""
    catalog = [_catalog_app("org.kde.kate")]
    installed = _installed_app("org.kde.kate")

    match = match_installed_to_catalog(installed, catalog)

    assert match.kind == MatchKind.APP_ID
    assert match.confidence == 0.9


def test_match_by_desktop_entry_id():
    """Match by desktop-entry/appstream id."""
    catalog = [_catalog_app("org.kde.kate", raw_data={"desktop_entry_id": "kate.desktop"})]
    installed = _installed_app("kate.desktop")

    match = match_installed_to_catalog(installed, catalog)

    assert match.kind == MatchKind.APP_ID
    assert match.confidence == 0.85


def test_app_id_case_insensitive():
    """App ID comparison is case-insensitive."""
    catalog = [_catalog_app("ORG.KDE.KATE")]
    installed = _installed_app("org.kde.kate")

    match = match_installed_to_catalog(installed, catalog)

    assert match.kind == MatchKind.APP_ID


# ---------------------------------------------------------------------------
# Rule 4: unmanaged
# ---------------------------------------------------------------------------
def test_no_match_returns_unmanaged():
    """No match returns unmanaged."""
    catalog = [_catalog_app("org.kde.kate")]
    installed = _installed_app("org.unknown.app")

    match = match_installed_to_catalog(installed, catalog)

    assert match.kind == MatchKind.UNMANAGED
    assert match.confidence == 0.0
    assert match.catalog_app is None


def test_unmanaged_origin_none():
    """No origin and no other match -> unmanaged."""
    catalog = [_catalog_app("org.kde.kate")]
    installed = _installed_app("org.unknown.app", origin=None)

    match = match_installed_to_catalog(installed, catalog)

    assert match.kind == MatchKind.UNMANAGED


# ---------------------------------------------------------------------------
# Ambiguous match
# ---------------------------------------------------------------------------
def test_ambiguous_when_two_catalog_apps_same_id():
    """Two catalog apps with same app_id -> ambiguous."""
    catalog = [
        _catalog_app("org.kde.kate", raw_data={"name": "Kate"}),
        _catalog_app("org.kde.kate", raw_data={"name": "Kate Beta"}),
    ]
    installed = _installed_app("org.kde.kate")

    match = match_installed_to_catalog(installed, catalog)

    assert match.kind == MatchKind.AMBIGUOUS
    assert match.catalog_app is None


# ---------------------------------------------------------------------------
# Rule precedence
# ---------------------------------------------------------------------------
def test_precedence_origin_beats_sha256_beats_app_id():
    """Origin > sha256 > app_id precedence."""
    catalog = [
        _catalog_app("org.kde.kate", sha256="aaa"),
        _catalog_app("org.gimp.gimp", sha256="bbb"),
    ]
    # Origin points to kate, file sha256 matches gimp, installed_id is gimp
    installed = _installed_app(
        "org.gimp.gimp",
        origin={"catalog_id": "org.kde.kate"},
        sha256="bbb",
    )

    match = match_installed_to_catalog(installed, catalog, file_sha256="bbb")

    assert match.kind == MatchKind.ORIGIN
    assert match.catalog_app.id == "org.kde.kate"


def test_sha256_beats_app_id():
    """SHA256 beats app_id when origin not available."""
    catalog = [
        _catalog_app("org.kde.kate", sha256="aaa"),
        _catalog_app("org.gimp.gimp", sha256="bbb"),
    ]
    # No origin, file sha256 matches kate, but installed_id is gimp
    installed = _installed_app("org.gimp.gimp", sha256="aaa")

    match = match_installed_to_catalog(installed, catalog, file_sha256="aaa")

    assert match.kind == MatchKind.SHA256
    assert match.catalog_app.id == "org.kde.kate"


# ---------------------------------------------------------------------------
# Hash matches but different origin stored
# ---------------------------------------------------------------------------
def test_hash_matches_but_different_origin_origin_wins():
    """Hash matches catalog app A, but origin points to B -> origin wins."""
    catalog = [
        _catalog_app("org.kde.kate", sha256="aaa"),
        _catalog_app("org.gimp.gimp", sha256="bbb"),
    ]
    # File sha256 matches gimp, but origin says kate
    installed = _installed_app(
        "some-id",
        origin={"catalog_id": "org.kde.kate"},
        sha256="bbb",
    )

    match = match_installed_to_catalog(installed, catalog, file_sha256="bbb")

    assert match.kind == MatchKind.ORIGIN
    assert match.catalog_app.id == "org.kde.kate"
    assert match.confidence == 1.0


# ---------------------------------------------------------------------------
# Empty catalog
# ---------------------------------------------------------------------------
def test_empty_catalog_returns_unmanaged():
    """Empty catalog returns unmanaged."""
    installed = _installed_app("org.kde.kate")

    match = match_installed_to_catalog(installed, [])

    assert match.kind == MatchKind.UNMANAGED


# ---------------------------------------------------------------------------
# Match bool behavior
# ---------------------------------------------------------------------------
def test_match_bool_true_for_matched():
    """Match is truthy when matched."""
    catalog = [_catalog_app("org.kde.kate")]
    installed = _installed_app("org.kde.kate")

    match = match_installed_to_catalog(installed, catalog)

    assert bool(match) is True


def test_match_bool_false_for_unmanaged():
    """Match is falsy when unmanaged."""
    catalog = [_catalog_app("org.kde.kate")]
    installed = _installed_app("org.unknown.app")

    match = match_installed_to_catalog(installed, catalog)

    assert bool(match) is False


def test_match_bool_false_for_ambiguous():
    """Match is falsy when ambiguous."""
    catalog = [
        _catalog_app("org.kde.kate"),
        _catalog_app("org.kde.kate"),
    ]
    installed = _installed_app("org.kde.kate")

    match = match_installed_to_catalog(installed, catalog)

    assert bool(match) is False
