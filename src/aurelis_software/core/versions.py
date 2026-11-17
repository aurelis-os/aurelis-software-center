"""Update logic (section 4.5).

Versions are never ordered. An update is available when the catalog entry
differs from the installed origin by version, sha256, or (for "latest")
by a newer ``version_changed_at``, subject to update policy.
"""

from __future__ import annotations

from .models import App, InstalledApp


def update_available(entry: App, inst: InstalledApp, *, include_self_managed: bool = False) -> bool:
    origin = inst.origin
    if origin is None:
        return False
    if origin.get("catalog_id") != entry.id:
        return False
    if inst.update_policy == "pinned":
        return False
    if inst.self_managed and not include_self_managed:
        return False
    return bool(
        entry.version != origin.get("version")
        or (
            entry.raw.get("sha256")
            and origin.get("sha256")
            and entry.raw.get("sha256") != origin.get("sha256")
        )
        or (
            entry.version == "latest"
            and entry.raw.get("version_changed_at")
            and entry.raw.get("version_changed_at") > origin.get("changed_at", "")
        )
    )


def eligible_for_update_all(inst: InstalledApp) -> bool:
    """``manual`` and ``pinned`` apps and self-managed apps never go in 'Update all'."""
    return inst.origin is not None and inst.update_policy == "auto" and not inst.self_managed
