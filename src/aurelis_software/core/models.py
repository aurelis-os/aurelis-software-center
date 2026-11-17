"""Core domain models (section 4.1).

One ``App`` model for every source, plus ``InstalledApp`` and
``UpdateInfo``. Pure Python: no Qt, no subprocess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Source(StrEnum):
    APPIMAGE = "appimage"
    FLATPAK = "flatpak"
    PACMAN = "pacman"


@dataclass(slots=True)
class App:  # a catalog / index entry
    key: str  # f"{source}:{id}"
    id: str
    source: Source
    name: str
    summary: str
    version: str | None = None
    categories: tuple[str, ...] = ()
    store_categories: tuple[str, ...] = ()
    search_blob: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def get(self, k: str, default: Any = None) -> Any:
        return self.raw.get(k, default)


@dataclass(slots=True)
class InstalledApp:  # something present on this system
    id: str  # AppImage: the launcher's app_id; others: their ids
    source: Source
    name: str
    version: str | None = None
    managed_name: str | None = None  # AppImage: file name in ~/Applications
    path: str | None = None  # AppImage: file path
    role: str = "primary"  # "primary" | "kept"
    sha256: str | None = None  # AppImage: full-file hash if the daemon has it
    update_policy: str | None = None  # AppImage: auto | manual | pinned
    self_managed: bool = False  # AppImage: app updates itself
    origin: dict | None = None  # AppImage: provenance record (catalog link)
    locked: bool = False  # system package, cannot be removed
    pending: str | None = None  # "install" | "remove" | None (pacman via pkg)
    previous: tuple[dict, ...] = ()  # AppImage: revertible versions


@dataclass(slots=True)
class UpdateInfo:
    app_key: str
    installed_version: str | None = None
    new_version: str | None = None
    size: int | None = None
    method: str = ""  # "zsync" | "full" | "flatpak" | "pkg"
