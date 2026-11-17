"""Tests for core/categories.py (section 4.4, Appendix B)."""

from __future__ import annotations

from aurelis_software.core.categories import map_categories

# Table-driven: raw freedesktop value -> expected store category (first match wins).
_RAW_TO_STORE = [
    ("Graphics", "Graphics and Photography"),
    ("2DGraphics", "Graphics and Photography"),
    ("3DGraphics", "Graphics and Photography"),
    ("RasterGraphics", "Graphics and Photography"),
    ("VectorGraphics", "Graphics and Photography"),
    ("Photography", "Graphics and Photography"),
    ("Scanning", "Graphics and Photography"),
    ("Viewer", "Graphics and Photography"),
    ("AudioVideo", "Audio and Video"),
    ("Audio", "Audio and Video"),
    ("Video", "Audio and Video"),
    ("Player", "Audio and Video"),
    ("Music", "Audio and Video"),
    ("Game", "Games"),
    ("ArcadeGame", "Games"),
    ("BoardGame", "Games"),
    ("Development", "Development"),
    ("IDE", "Development"),
    ("WebDevelopment", "Development"),
    ("Network", "Internet"),
    ("WebBrowser", "Internet"),
    ("Email", "Internet"),
    ("Office", "Office"),
    ("WordProcessor", "Office"),
    ("Education", "Education and Science"),
    ("Science", "Education and Science"),
    ("Security", "Security"),
    ("System", "System"),
    ("TerminalEmulator", "System"),
    ("FileManager", "System"),
    ("Utility", "Utilities"),
    ("TextEditor", "Utilities"),
]


def test_every_raw_category_maps_to_its_store_category():
    for raw, expected in _RAW_TO_STORE:
        assert map_categories([raw]) == (expected,), raw


def test_ignored_toolkit_and_desktop_tags():
    for raw in ["KDE", "Qt", "GNOME", "GTK", "kde", "qt"]:
        assert map_categories([raw]) == (), raw


def test_x_prefixed_tags_are_ignored():
    assert map_categories(["X-GNOME-Foo", "X-Frobnicate"]) == ()


def test_unknown_categories_are_ignored():
    assert map_categories(["NotACategory", ""]) == ()


def test_an_app_can_have_several_store_categories_in_table_order():
    assert map_categories(["Photography", "Audio", "Game"]) == (
        "Graphics and Photography",
        "Audio and Video",
        "Games",
    )


def test_empty_input():
    assert map_categories([]) == ()
    assert map_categories(None) == ()
