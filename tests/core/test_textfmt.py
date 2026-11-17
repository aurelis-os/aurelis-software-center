"""Tests for core/textfmt.py (description paragraphs, Appendix C URL labels)."""

from __future__ import annotations

from aurelis_software.core.textfmt import paragraphs, url_labels


def test_paragraphs_split_on_newlines():
    assert paragraphs("First.\n\nSecond.\nThird.") == ["First.", "Second.", "Third."]
    assert paragraphs("") == []
    assert paragraphs("\n\n") == []


def test_url_labels_known_keys():
    assert url_labels({"homepage": "https://example.com"}) == [("Website", "https://example.com")]
    assert url_labels({"bugtracker": "https://bugs.example.com"}) == [
        ("Report a problem", "https://bugs.example.com")
    ]
    assert url_labels({"vcs-browser": "https://git.example.com/repo"}) == [
        ("Source code", "https://git.example.com/repo")
    ]


def test_url_labels_unknown_keys_are_title_cased():
    assert url_labels({"my-link": "https://example.com"}) == [("My Link", "https://example.com")]
    assert url_labels({"custom_key": "https://example.com"}) == [
        ("Custom Key", "https://example.com")
    ]


def test_url_labels_only_https_are_clickable():
    assert url_labels({"homepage": "http://example.com"}) == []
    assert url_labels({"homepage": "ftp://example.com"}) == []
    assert url_labels({"homepage": 123}) == []
    assert url_labels({}) == []
