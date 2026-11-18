"""Matching logic for installed apps to catalog entries (P3.8).

Pure Python: no Qt, no subprocess.

Matching precedence (spec order):
1. origin (xattr/desktop-entry origin from daemon List/Info)
2. sha256 of the file == catalog hash
3. app_id suggestion (catalog app_id vs desktop-entry/appstream id)
4. unmanaged (no match)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import App, InstalledApp


class MatchKind(str):
    ORIGIN = "origin"
    SHA256 = "sha256"
    APP_ID = "app_id"
    UNMANAGED = "unmanaged"
    AMBIGUOUS = "ambiguous"


@dataclass(slots=True)
class Match:
    """Result of matching an installed app to a catalog entry."""

    kind: str  # one of MatchKind
    confidence: float  # 0.0 to 1.0
    catalog_app: App | None  # App if matched, None if unmanaged/ambiguous

    def __bool__(self) -> bool:
        return self.catalog_app is not None and self.kind != MatchKind.AMBIGUOUS


def _extract_origin_id(origin: dict | None) -> str | None:
    """Extract catalog_id from origin dict."""
    if not isinstance(origin, dict):
        return None
    return origin.get("catalog_id")


def _extract_desktop_entry_id(app: App) -> str | None:
    """Extract desktop-entry/appstream id from catalog app raw data."""
    raw = getattr(app, "raw", {}) or {}
    # Try common desktop entry ID fields
    for key in ("desktop_entry_id", "appstream_id", "flatpak_id", "desktop-id"):
        val = raw.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def _normalize_id(s: str) -> str:
    """Normalize an ID for comparison (lowercase, strip)."""
    return s.strip().lower()


def match_installed_to_catalog(
    installed: InstalledApp,
    catalog_apps: list[App],
    *,
    file_sha256: str | None = None,
) -> Match:
    """
    Match an installed app to a catalog entry.

    Args:
        installed: InstalledApp instance with origin, sha256, id, path
        catalog_apps: List of catalog App entries
        file_sha256: Optional SHA256 of the installed file (computed separately)

    Returns:
        Match with kind, confidence, and catalog_app (or None)
    """
    if not catalog_apps:
        return Match(kind=MatchKind.UNMANAGED, confidence=0.0, catalog_app=None)

    installed_id = installed.id
    installed_origin = installed.origin
    installed_sha256 = installed.sha256
    effective_sha256 = file_sha256 or installed_sha256

    # 1. Match by origin (highest precedence)
    match = _try_match_by_origin(installed_origin, catalog_apps)
    if match:
        return match

    # 2. Match by sha256
    if effective_sha256:
        match = _try_match_by_sha256(effective_sha256, catalog_apps)
        if match:
            return match

    # Check for ambiguous match BEFORE app_id matching
    # (spec: "no silent wrong pick: returns ambiguous" when multiple catalog apps have same app_id)
    if _is_ambiguous(installed_id, catalog_apps):
        return Match(kind=MatchKind.AMBIGUOUS, confidence=0.0, catalog_app=None)

    # 3. Match by app_id suggestion
    match = _try_match_by_app_id(installed_id, catalog_apps)
    if match:
        return match

    # 4. No match -> unmanaged
    return Match(kind=MatchKind.UNMANAGED, confidence=0.0, catalog_app=None)


def _try_match_by_origin(origin: dict | None, catalog_apps: list[App]) -> Match | None:
    """Try to match by origin catalog_id."""
    origin_id = _extract_origin_id(origin)
    if not origin_id:
        return None
    for app in catalog_apps:
        if _normalize_id(app.id) == _normalize_id(origin_id):
            return Match(
                kind=MatchKind.ORIGIN,
                confidence=1.0,
                catalog_app=app,
            )
    return None


def _try_match_by_sha256(sha256: str, catalog_apps: list[App]) -> Match | None:
    """Try to match by sha256."""
    norm_sha256 = _normalize_id(sha256)
    for app in catalog_apps:
        catalog_sha256 = app.raw.get("sha256")
        if catalog_sha256 and _normalize_id(catalog_sha256) == norm_sha256:
            return Match(
                kind=MatchKind.SHA256,
                confidence=0.95,
                catalog_app=app,
            )
    return None


def _try_match_by_app_id(installed_id: str, catalog_apps: list[App]) -> Match | None:
    """Try to match by app_id (exact or desktop-entry)."""
    norm_installed_id = _normalize_id(installed_id)
    if not norm_installed_id:
        return None

    # First try exact installed_id match (case-insensitive)
    for app in catalog_apps:
        if _normalize_id(app.id) == norm_installed_id:
            return Match(
                kind=MatchKind.APP_ID,
                confidence=0.9,
                catalog_app=app,
            )

    # Try desktop-entry/appstream id match
    for app in catalog_apps:
        desktop_id = _extract_desktop_entry_id(app)
        if desktop_id and _normalize_id(desktop_id) == norm_installed_id:
            return Match(
                kind=MatchKind.APP_ID,
                confidence=0.85,
                catalog_app=app,
            )
    return None


def build_origin(entry: App) -> dict:
    """Build origin dict from catalog app entry for SetOrigin call."""
    raw = entry.raw
    origin = {
        "source": "aurelis-catalog",
        "catalog_id": entry.id,
        "version": entry.version,
        "sha256": raw.get("sha256"),
        "changed_at": raw.get("version_changed_at"),
        "url": raw.get("download_url"),
        "update_policy": "auto",
    }
    return {key: value for key, value in origin.items() if value is not None}


def _is_ambiguous(installed_id: str, catalog_apps: list[App]) -> bool:
    """Check if installed_id has multiple catalog entries (case-insensitive)."""
    norm_installed_id = _normalize_id(installed_id)
    if not norm_installed_id:
        return False
    count = sum(1 for app in catalog_apps if _normalize_id(app.id) == norm_installed_id)
    return count > 1
