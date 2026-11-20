"""Configuration: TOML load/save with defaults and unknown keys preserved.

Read with ``tomllib``; written with a tiny hand-rolled serializer. Unknown
keys found on disk are kept, so the config survives edits by other tools
(section 4.7).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import Any

from .paths import Paths

DEFAULTS: dict[str, Any] = {
    "catalog": {
        "apps_url": "https://github.com/aurelis-os/aurelis-software-database/releases/download/latest/apps.db.tar.gz",
        "icons_url": "https://github.com/aurelis-os/aurelis-software-database/releases/download/latest/app-icons.tar.gz",
        "refresh_hours": 24,
    },
    "ui": {
        "language": "system",
        "show_proprietary": True,
        "hide_incompatible": True,
    },
    "network": {"offline": False},
    "flathub": {"enabled": False},
    "pacman": {"enabled": False},
    "updates": {"include_self_managed": False, "notify": False},
    "downloads": {"allow_unverified": "ask"},
    "wizard": {"run_without_asking": []},
}


@dataclass(frozen=True)
class Config:
    data: dict[str, Any]

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load(paths: Paths) -> Config:
    data: dict[str, Any] = {}
    file = paths.config_file
    if file.is_file():
        with file.open("rb") as fh:
            loaded = tomllib.load(fh)
            if isinstance(loaded, dict):
                data = loaded
    return Config(_merge(DEFAULTS, data))


def _serialize(value: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(value, dict):
        out: list[str] = []
        for key, val in value.items():
            if isinstance(val, dict):
                out.append(f"{pad}[{key}]")
                out.append(_serialize(val, indent + 1))
            else:
                out.append(f"{pad}{key} = {_toml_value(val)}")
        return "\n".join(out)
    return _toml_value(value)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        items = [_toml_value(item) for item in value]
        return "[" + ", ".join(items) + "]"
    msg = f"unsupported config value type: {type(value)!r}"
    raise TypeError(msg)


def save(paths: Paths, config: Config) -> None:
    file = paths.config_file
    file.parent.mkdir(parents=True, exist_ok=True)
    sections = [section for section in config.data if isinstance(config.data[section], dict)]
    blocks = [f"[{section}]\n" + _serialize(config.data[section], 1) for section in sections]
    file.write_text("\n".join(blocks) + "\n")
