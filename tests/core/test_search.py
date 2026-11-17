"""Tests for core/search.py (section 4.3): folding, ranking, AND tokens,
empty query, and the 500-entry / 50 ms benchmark.
"""

from __future__ import annotations

import time
from pathlib import Path

from aurelis_software.core.catalog import load_catalog
from aurelis_software.core.models import App, Source
from aurelis_software.core.search import build_index, fold_text, search

FIXTURE_DB = Path(__file__).resolve().parent.parent / "fixtures" / "apps.db"


def _app(app_id: str, name: str, summary: str = "", raw: dict | None = None) -> App:
    return App(
        key=f"appimage:{app_id}",
        id=app_id,
        source=Source.APPIMAGE,
        name=name,
        summary=summary,
        raw=raw or {},
    )


def test_fold_strips_accents_and_casefolds():
    assert fold_text("École") == "ecole"
    assert fold_text("\u03b1\u0301") == "\u03b1"  # Greek alpha + combining tonos -> alpha
    assert fold_text("ΦΩΤΟ") == "φωτο"
    assert fold_text("caf\u00e9") == "cafe"


def test_search_kate_ranks_kate_first():
    index = build_index(load_catalog(FIXTURE_DB).apps)
    results = search(index, "kate")
    assert results
    assert results[0].id == "org.kde.kate"


def test_greek_keyword_match_without_tonos():
    index = build_index([_app("org.example.Foto", "Foto", raw={"keywords": ["φωτογραφία"]})])
    assert [app.id for app in search(index, "φωτο")] == ["org.example.Foto"]


def test_accented_name_match():
    index = build_index([_app("org.example.Cafe", "Caf\u00e9")])
    assert [app.id for app in search(index, "cafe")] == ["org.example.Cafe"]


def test_tokens_are_anded():
    index = build_index([_app("org.example.TC", "Tea Coffee", raw={"keywords": ["tea", "coffee"]})])
    assert [app.id for app in search(index, "tea coffee")] == ["org.example.TC"]
    assert search(index, "tea milk") == []


def test_empty_query_returns_all_sorted_by_name():
    index = build_index([_app("b", "Beta"), _app("a", "Alpha"), _app("c", "Gamma")])
    assert [app.id for app in search(index, "")] == ["b", "a", "c"]


def test_ranking_order():
    # exact name beats prefix beats contains
    index = build_index(
        [
            _app("contains", "The Tea Room"),
            _app("prefix", "Teapot"),
            _app("exact", "Tea"),
        ]
    )
    assert [app.id for app in search(index, "tea")] == ["exact", "prefix", "contains"]


def test_ranking_ties_shorter_name_then_name():
    index = build_index(
        [
            _app("bb", "B B"),
            _app("aa", "A A"),
            _app("cccc", "C C C C"),
        ]
    )
    assert [app.id for app in search(index, "")] == ["aa", "bb", "cccc"]


def test_benchmark_500_entries_under_50_ms():
    apps = [
        _app(f"org.example.App{i:04d}", f"Application {i:04d}", summary=f"summary number {i}")
        for i in range(500)
    ]
    index = build_index(apps)
    start = time.perf_counter()
    for _ in range(10):
        search(index, "application 7")
    elapsed = time.perf_counter() - start
    assert elapsed < 0.05, f"search took {elapsed * 1000:.1f} ms for 10 x 500 entries"
