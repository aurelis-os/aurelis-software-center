"""Search index and ranking (section 4.3).

Folding: ``casefold()`` + Unicode NFKD with combining marks stripped, so
Greek search works without tonos and ``é`` matches ``e``. Ranking
(highest first): exact name, name prefix, name word prefix, name
contains, keyword hit, summary contains, description contains. Ties:
shorter name, then name. Query tokens are ANDed; an empty query returns
everything. Budget: under 50 ms for 500 apps.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .models import App


def fold_text(text: str) -> str:
    folded = text.casefold()
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


@dataclass(slots=True)
class SearchEntry:
    app: App
    name: str
    keywords: str
    summary: str
    description: str


@dataclass(slots=True)
class SearchIndex:
    entries: tuple[SearchEntry, ...]


def build_index(apps) -> SearchIndex:
    entries = []
    for app in apps:
        raw_keywords = app.raw.get("keywords") or []
        keywords = " ".join(fold_text(str(kw)) for kw in raw_keywords)
        entries.append(
            SearchEntry(
                app=app,
                name=fold_text(app.name),
                keywords=keywords,
                summary=fold_text(app.summary),
                description=fold_text(app.raw.get("description") or ""),
            )
        )
    return SearchIndex(entries=tuple(entries))


def _rank_tiers(entry: SearchEntry, token: str) -> list[int]:
    tiers = []
    if token == entry.name:
        tiers.append(0)
    if entry.name.startswith(token):
        tiers.append(1)
    if any(word.startswith(token) for word in entry.name.split()):
        tiers.append(2)
    if token in entry.name:
        tiers.append(3)
    if token in entry.keywords:
        tiers.append(4)
    if token in entry.summary:
        tiers.append(5)
    if token in entry.description:
        tiers.append(6)
    return tiers


def search(index: SearchIndex, query: str) -> list[App]:
    tokens = [fold_text(token) for token in query.split()]
    tokens = [token for token in tokens if token]

    if not tokens:
        ordered = sorted(index.entries, key=lambda entry: (len(entry.app.name), entry.app.name))
        return [entry.app for entry in ordered]

    results = []
    for entry in index.entries:
        token_tiers = []
        for token in tokens:
            tiers = _rank_tiers(entry, token)
            if not tiers:
                break
            token_tiers.append(min(tiers))
        else:
            results.append((max(token_tiers), entry.app))

    results.sort(key=lambda item: (item[0], len(item[1].name), item[1].name))
    return [app for _, app in results]
