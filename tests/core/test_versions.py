"""Tests for core/versions.py (section 4.5) - table-driven over every rule."""

from __future__ import annotations

import pytest

from aurelis_software.core.models import App, InstalledApp, Source
from aurelis_software.core.versions import eligible_for_update_all, update_available


def _entry(app_id: str, version: str | None, **raw) -> App:
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
    origin: dict | None = None,
    *,
    policy: str | None = None,
    self_managed: bool = False,
) -> InstalledApp:
    return InstalledApp(
        id="org.example.app",
        source=Source.APPIMAGE,
        name="App",
        origin=origin,
        update_policy=policy,
        self_managed=self_managed,
    )


def _origin(catalog_id: str, version: str | None = None, **raw) -> dict:
    origin = {"source": "aurelis-catalog", "catalog_id": catalog_id, "version": version}
    origin.update(raw)
    return origin


@pytest.mark.parametrize(
    "entry_version,inst_origin_version,expected",
    [
        ("1.0", "1.0", False),  # same version, same sha -> none
        ("1.0", "0.9", True),  # version differs -> update
        ("2.0", "1.0", True),
    ],
)
def test_version_compared_by_inequality_only(entry_version, inst_origin_version, expected):
    entry = _entry("org.example.app", entry_version, sha256="abc")
    inst = _inst(_origin("org.example.app", inst_origin_version, sha256="abc"))
    assert update_available(entry, inst) is expected


def test_same_version_different_sha_is_an_update():
    entry = _entry("org.example.app", "1.0", sha256="new")
    inst = _inst(_origin("org.example.app", "1.0", sha256="old"))
    assert update_available(entry, inst) is True


def test_same_version_same_sha_no_update():
    entry = _entry("org.example.app", "1.0", sha256="abc")
    inst = _inst(_origin("org.example.app", "1.0", sha256="abc"))
    assert update_available(entry, inst) is False


def test_latest_with_newer_changed_at_is_an_update():
    entry = _entry("org.example.app", "latest", version_changed_at="2026-02-01T00:00:00Z")
    inst = _inst(_origin("org.example.app", "latest", changed_at="2026-01-01T00:00:00Z"))
    assert update_available(entry, inst) is True


def test_latest_with_older_changed_at_is_not_an_update():
    entry = _entry("org.example.app", "latest", version_changed_at="2026-01-01T00:00:00Z")
    inst = _inst(_origin("org.example.app", "latest", changed_at="2026-02-01T00:00:00Z"))
    assert update_available(entry, inst) is False


@pytest.mark.parametrize("policy", ["auto", "manual", "pinned"])
def test_pinned_never_updatable(policy):
    entry = _entry("org.example.app", "2.0")
    inst = _inst(_origin("org.example.app", "1.0"), policy="pinned")
    assert update_available(entry, inst) is False
    assert eligible_for_update_all(inst) is False


def test_manual_in_updates_but_not_update_all():
    entry = _entry("org.example.app", "2.0")
    inst = _inst(_origin("org.example.app", "1.0"), policy="manual")
    assert update_available(entry, inst) is True
    assert eligible_for_update_all(inst) is False


def test_auto_eligible_for_update_all():
    entry = _entry("org.example.app", "2.0")
    inst = _inst(_origin("org.example.app", "1.0"), policy="auto")
    assert update_available(entry, inst) is True
    assert eligible_for_update_all(inst) is True


def test_self_managed_excluded_unless_setting_on():
    entry = _entry("org.example.app", "2.0")
    inst = _inst(_origin("org.example.app", "1.0"), policy="auto", self_managed=True)
    assert update_available(entry, inst) is False
    assert update_available(entry, inst, include_self_managed=True) is True
    assert eligible_for_update_all(inst) is False


def test_no_origin_never_updatable():
    entry = _entry("org.example.app", "2.0")
    inst = _inst(None)
    assert update_available(entry, inst) is False
    assert eligible_for_update_all(inst) is False


def test_origin_linked_to_other_catalog_id_never_updatable():
    entry = _entry("org.example.app", "2.0")
    inst = _inst(_origin("org.example.other", "1.0"))
    assert update_available(entry, inst) is False


def test_origin_without_version_no_update_on_version_alone():
    """Origin without version should not trigger update based on version comparison alone.

    Missing version in origin is treated as "unknown" - we fall back to sha256/changed_at checks.
    """
    entry = _entry("org.example.app", "2.0", sha256="abc")
    # Origin has catalog_id but no version key
    inst = _inst({"source": "aurelis-catalog", "catalog_id": "org.example.app", "sha256": "abc"})
    assert update_available(entry, inst) is False


def test_origin_without_version_sha256_diff_triggers_update():
    """Origin without version but with sha256 diff should trigger update."""
    entry = _entry("org.example.app", "2.0", sha256="new_sha")
    inst = _inst(
        {"source": "aurelis-catalog", "catalog_id": "org.example.app", "sha256": "old_sha"}
    )
    assert update_available(entry, inst) is True


def test_origin_without_version_latest_with_newer_changed_at_triggers_update():
    """Origin without version but latest entry with newer changed_at should trigger update."""
    entry = _entry(
        "org.example.app", "latest", version_changed_at="2026-02-01T00:00:00Z", sha256="abc"
    )
    inst = _inst(
        {
            "source": "aurelis-catalog",
            "catalog_id": "org.example.app",
            "changed_at": "2026-01-01T00:00:00Z",
            "sha256": "abc",
        }
    )
    assert update_available(entry, inst) is True


def test_origin_without_version_latest_with_older_changed_at_no_update():
    """Origin without version and latest entry with older changed_at should not trigger update."""
    entry = _entry(
        "org.example.app", "latest", version_changed_at="2026-01-01T00:00:00Z", sha256="abc"
    )
    inst = _inst(
        {
            "source": "aurelis-catalog",
            "catalog_id": "org.example.app",
            "changed_at": "2026-02-01T00:00:00Z",
            "sha256": "abc",
        }
    )
    assert update_available(entry, inst) is False
