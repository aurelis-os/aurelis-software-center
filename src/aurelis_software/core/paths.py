"""Filesystem paths for Aurelis Software.

All roots are XDG-based by default and injected, never hard-coded in
logic, so tests run without touching the user's real directories
(section 4.7).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    """Injected filesystem roots (XDG-based by default)."""

    config_dir: Path
    cache_dir: Path
    state_dir: Path

    @classmethod
    def xdg(cls) -> Paths:
        def env(name: str, default: str) -> Path:
            return Path(os.environ.get(name) or os.path.expanduser(default))

        return cls(
            config_dir=env("XDG_CONFIG_HOME", "~/.config"),
            cache_dir=env("XDG_CACHE_HOME", "~/.cache"),
            state_dir=env("XDG_STATE_HOME", "~/.local/state"),
        )

    @property
    def config_file(self) -> Path:
        return self.config_dir / "aurelis-software" / "config.toml"

    @property
    def catalog_dir(self) -> Path:
        return self.cache_dir / "aurelis-software" / "catalog"

    @property
    def catalog_db(self) -> Path:
        return self.catalog_dir / "apps.db"

    @property
    def catalog_prev(self) -> Path:
        return self.catalog_dir / "apps.db.prev"

    @property
    def icons_dir(self) -> Path:
        return self.cache_dir / "aurelis-software" / "icons"

    @property
    def downloads_dir(self) -> Path:
        return self.cache_dir / "aurelis-software" / "downloads"

    @property
    def state_file(self) -> Path:
        return self.state_dir / "aurelis-software" / "catalog-state.json"
