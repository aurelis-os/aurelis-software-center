"""Catalog parsing (section 4.2).

``load_catalog`` reads the JSON envelope, normalises entries defensively,
skips broken ones, deduplicates by ``id`` and reports everything it
skipped. Unknown fields are preserved in ``App.raw``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .categories import map_categories
from .errors import CatalogSchemaTooNew
from .models import App, Source

SUPPORTED_SCHEMA_VERSION = 1

logger = logging.getLogger("aurelis_software.core.catalog")


@dataclass(slots=True)
class CatalogResult:
    apps: list[App]
    skipped: list[tuple[str, str]]
    schema_version: int | None
    generated_at: str | None


def _clean_string(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _clean_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _normalise_screenshots(value: Any) -> list[dict[str, Any]]:
    normalised: list[dict[str, Any]] = []
    for shot in value or []:
        if not isinstance(shot, dict):
            continue  # ignore malformed screenshots
        cleaned: dict[str, Any] = {}
        for key, val in shot.items():
            if key == "size":
                cleaned[key] = _clean_int(val)
            else:
                cleaned[key] = val
        normalised.append(cleaned)
    return normalised


def _normalise_entry(entry: dict[str, Any], app_id: str) -> App:
    name = _clean_string(entry.get("name"))
    summary = _clean_string(entry.get("summary"))
    version = _clean_string(entry.get("version")) or None
    categories = tuple(
        _clean_string(cat) for cat in (entry.get("categories") or []) if _clean_string(cat)
    )
    keywords = tuple(_clean_string(kw) for kw in (entry.get("keywords") or []) if _clean_string(kw))
    description = _clean_string(entry.get("description"))

    raw = dict(entry)
    raw["screenshots"] = _normalise_screenshots(entry.get("screenshots"))

    search_blob = " ".join(part for part in (name, summary, description, *keywords) if part)

    return App(
        key=f"{Source.APPIMAGE}:{app_id}",
        id=app_id,
        source=Source.APPIMAGE,
        name=name,
        summary=summary,
        version=version,
        categories=categories,
        store_categories=map_categories(categories),
        search_blob=search_blob,
        raw=raw,
    )


def load_catalog(path: Path | str) -> CatalogResult:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, dict):
        msg = "catalog root must be a JSON object"
        raise TypeError(msg)

    schema = data.get("schema_version")
    if isinstance(schema, int) and schema > SUPPORTED_SCHEMA_VERSION:
        msg = f"catalog schema version {schema} is newer than supported {SUPPORTED_SCHEMA_VERSION}"
        raise CatalogSchemaTooNew(msg)

    raw_apps = data.get("apps") or []
    if not isinstance(raw_apps, list):
        raw_apps = []

    apps: list[App] = []
    skipped: list[tuple[str, str]] = []
    seen: set[str] = set()

    for entry in raw_apps:
        if not isinstance(entry, dict):
            skipped.append(("<non-object>", "entry is not an object"))
            continue

        app_id = _clean_string(entry.get("id"))
        name = _clean_string(entry.get("name"))
        download_url = _clean_string(entry.get("download_url"))

        if not app_id or not name or not download_url:
            skipped.append((app_id or "<missing>", "missing id/name/download_url"))
            continue

        if app_id in seen:
            logger.warning("duplicate catalog id %r; keeping the first entry", app_id)
            skipped.append((app_id, "duplicate id"))
            continue

        seen.add(app_id)
        apps.append(_normalise_entry(entry, app_id))

    return CatalogResult(
        apps=apps,
        skipped=skipped,
        schema_version=schema if isinstance(schema, int) else None,
        generated_at=_clean_string(data.get("generated_at")) or None,
    )
