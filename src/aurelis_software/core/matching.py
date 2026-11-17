"""Installed-to-catalog matching (section 4.6).

Applied to every installed AppImage, in order:
1. origin.catalog_id present -> linked.
2. installed sha256 equals a catalog entry's sha256 -> auto-link (silent SetOrigin).
3. installed app_id equals a catalog entry id -> suggest (prompt before SetOrigin).
4. Otherwise -> unmanaged.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import App, InstalledApp


@dataclass(slots=True)
class MatchResult:
    kind: str  # "linked" | "auto_link" | "suggest" | "unmanaged"
    entry: App | None
    origin: dict | None  # origin to pass to SetOrigin (auto_link only)


def build_origin(entry: App) -> dict:
    origin = {
        "source": "aurelis-catalog",
        "catalog_id": entry.id,
        "version": entry.version,
        "sha256": entry.raw.get("sha256"),
        "changed_at": entry.raw.get("version_changed_at"),
        "url": entry.raw.get("download_url"),
    }
    return {key: value for key, value in origin.items() if value is not None}


def match_installed(
    inst: InstalledApp,
    entries_by_id: dict[str, App],
    entries_by_sha256: dict[str, App],
) -> MatchResult:
    origin = inst.origin or {}
    catalog_id = origin.get("catalog_id")
    if catalog_id:
        if catalog_id in entries_by_id:
            return MatchResult("linked", entries_by_id[catalog_id], None)
        # The catalog entry this install was linked to is gone.
        return MatchResult("linked", None, None)
    if inst.sha256 and inst.sha256 in entries_by_sha256:
        entry = entries_by_sha256[inst.sha256]
        return MatchResult("auto_link", entry, build_origin(entry))
    if inst.id in entries_by_id:
        return MatchResult("suggest", entries_by_id[inst.id], None)
    return MatchResult("unmanaged", None, None)
