"""Tests for ui/detail_page.py (P2.4): detail page with and without optional fields."""

from __future__ import annotations

from aurelis_software.core.models import App, Source
from aurelis_software.ui.detail_page import DetailPage


def _full_app() -> App:
    return App(
        key="appimage:org.kde.kate",
        id="org.kde.kate",
        source=Source.APPIMAGE,
        name="Kate",
        summary="Advanced text editor",
        version="26.08.2-1",
        raw={
            "repo": "KDE/kate",
            "developer": "KDE e.V.",
            "license": "GPL-2.0-only",
            "sha256": "a1b2",
            "size": 45000000,
            "icon": {"name": "org.kde.kate.png"},
            "screenshots": [{"default": True, "images": []}],
            "urls": {"homepage": "https://kate-editor.org", "bugtracker": "https://bugs.kde.org"},
            "description": "A powerful text editor.\nSupports plugins and sessions.",
        },
    )


def _empty_app() -> App:
    return App(
        key="appimage:org.example.noicon",
        id="org.example.noicon",
        source=Source.APPIMAGE,
        name="No Icon App",
        summary="",
        version=None,
        raw={},
    )


def test_detail_page_full_app_renders(qtbot):
    page = DetailPage(icons_dir=None)
    qtbot.addWidget(page)
    page.set_app(_full_app())
    # Primary action present and enabled for NotInstalled (Phase 3)
    assert page._action_button.isEnabled() is True
    assert page._action_button.text() == "Install"
    assert page.install_requested is not None


def test_detail_page_empty_app_renders(qtbot):
    # Every optional field missing must still render.
    page = DetailPage(icons_dir=None)
    qtbot.addWidget(page)
    page.set_app(_empty_app())
    assert page._action_button.isEnabled() is True
    assert page._action_button.text() == "Install"


def test_detail_page_clear_shows_empty(qtbot):
    page = DetailPage(icons_dir=None)
    qtbot.addWidget(page)
    page.set_app(_full_app())
    page.clear()


def _visible_label_texts(page: DetailPage) -> set[str]:
    """Collect non-empty text from all visible QLabels in the page."""
    from PyQt6.QtWidgets import QLabel

    texts = set()
    for label in page.findChildren(QLabel):
        # Skip widgets that are being deleted (deleteLater scheduled but not yet processed)
        try:
            if not label.isVisible():
                continue
            txt = label.text().strip()
        except RuntimeError:
            # Widget has been deleted
            continue
        if txt:
            # Strip HTML tags from link labels
            if txt.startswith("<a href="):
                txt = txt.split(">", 1)[-1].rsplit("<", 1)[0]
            texts.add(txt)
    return texts


def test_detail_page_switch_a_to_b_to_a(qtbot):
    """DetailPage A->B->A: after each set_app (+ qtbot.wait(0)),
    the set of visible QLabel texts equals the expected set for that app."""
    page = DetailPage(icons_dir=None)
    qtbot.addWidget(page)
    page.resize(800, 1000)
    page.show()
    qtbot.waitExposed(page)
    from PyQt6.QtWidgets import QApplication

    QApplication.processEvents()

    # App A: full app
    page.set_app(_full_app())
    qtbot.wait(100)
    QApplication.processEvents()
    texts_a = _visible_label_texts(page)
    expected_a = {
        "Kate",
        "Advanced text editor",
        "appimage",
        "26.08.2-1",
        "45 MB",
        "Packaged by <b>KDE</b> on GitHub",
        "Developer: KDE e.V.",
        "GPL-2.0-only",
        "Checksum verified on install.",
        "Description",
        "A powerful text editor.",
        "Supports plugins and sessions.",
        "Links",
        "Homepage",
        "Bugtracker",
        "Also available as",
        "(other sources with the same id appear here)",
        "Screenshot",
        "1",
    }
    assert texts_a == expected_a, f"Full app labels mismatch: got {texts_a}, expected {expected_a}"

    # App B: empty app (no optional fields)
    page.set_app(_empty_app())
    qtbot.wait(100)
    QApplication.processEvents()
    texts_b = _visible_label_texts(page)
    expected_b = {
        "No Icon App",
        "appimage",
        "No checksum available.",
        "Also available as",
        "(other sources with the same id appear here)",
    }
    assert texts_b == expected_b, f"Empty app labels mismatch: got {texts_b}, expected {expected_b}"

    # Back to App A
    page.set_app(_full_app())
    qtbot.wait(100)
    QApplication.processEvents()
    texts_a2 = _visible_label_texts(page)
    assert texts_a2 == expected_a, (
        f"Full app (again) labels mismatch: got {texts_a2}, expected {expected_a}"
    )


def _app_with_license(license_val: str | None) -> App:
    raw = {"repo": "example/repo", "developer": "Example Dev"}  # ensure trust line renders
    if license_val is not None:
        raw["license"] = license_val
    return App(
        key="appimage:org.example.test",
        id="org.example.test",
        source=Source.APPIMAGE,
        name="Test App",
        summary="Test",
        version="1.0",
        raw=raw,
    )


def _find_license_chip(page):
    """Return the license chip QLabel (identified by its padding style)."""
    from PyQt6.QtWidgets import QLabel

    return [
        w
        for w in page.findChildren(QLabel)
        if w.styleSheet() and "padding: 2px 8px" in w.styleSheet()
    ]


def test_license_chip_not_clipped(qtbot):
    """chip.width() must equal sizeHint().width() — no setMaximumWidth constraint.

    The bug: setMaximumWidth(horizontalAdvance(text) + 16) was called before the
    widget is polished. Qt's CSS padding adds more than 16px to sizeHint, so
    setMaximumWidth caps chip.width() below sizeHint, clipping the text.
    Fix: remove setMaximumWidth; QSizePolicy.Maximum already prevents expansion.
    """
    from PyQt6.QtWidgets import QApplication

    page = DetailPage(icons_dir=None)
    qtbot.addWidget(page)
    page.resize(800, 1000)
    page.show()
    qtbot.waitExposed(page)
    QApplication.processEvents()

    cases = [
        ("GPL-2.0-only", "GPL-2.0-only"),
        ("GPL-3.0-or-later", "GPL-3.0-or-later"),
        ("LicenseRef-proprietary", "Proprietary"),
    ]
    for license_val, expected_label in cases:
        page.set_app(_app_with_license(license_val))
        qtbot.wait(1)
        QApplication.processEvents()

        chips = _find_license_chip(page)
        assert len(chips) == 1, f"{license_val}: expected 1 chip, got {len(chips)}"
        chip = chips[0]
        assert chip.text() == expected_label

        # chip.width() must equal sizeHint().width(): setMaximumWidth must not
        # artificially constrain the chip below its natural painted size.
        assert chip.width() >= chip.sizeHint().width(), (
            f"{license_val}: chip.width() {chip.width()} < sizeHint {chip.sizeHint().width()} —"
            " setMaximumWidth is clipping the chip"
        )


def test_license_classification_chip_kind(qtbot):
    """License classification table -> chip kind, and chip width <= text width + padding."""
    from PyQt6.QtGui import QFontMetrics
    from PyQt6.QtWidgets import QApplication

    page = DetailPage(icons_dir=None)
    qtbot.addWidget(page)
    page.resize(800, 1000)
    page.show()
    qtbot.waitExposed(page)
    QApplication.processEvents()

    test_cases = [
        ("GPL-2.0-only", "neutral", "GPL-2.0-only"),
        ("MIT", "neutral", "MIT"),
        ("proprietary", "neutral", "proprietary"),
        ("LicenseRef-proprietary", "proprietary", "Proprietary"),
        (None, None, None),  # no license -> no chip
    ]

    for license_val, expected_kind, expected_label in test_cases:
        page.set_app(_app_with_license(license_val))
        qtbot.wait(50)
        QApplication.processEvents()

        chips = _find_license_chip(page)

        if expected_kind is None:
            assert len(chips) == 0, f"Expected no license chip for {license_val}, got {len(chips)}"
            continue

        assert len(chips) == 1, f"Expected one license chip for {license_val}, got {len(chips)}"
        chip = chips[0]

        assert chip.text() == expected_label, (
            f"Chip label mismatch for {license_val}: got {chip.text()}, expected {expected_label}"
        )

        metrics = QFontMetrics(chip.font())
        text_width = metrics.horizontalAdvance(chip.text())
        # chip must be at least as wide as the text (not clipped)
        assert chip.width() >= text_width, (
            f"Chip width {chip.width()} < text width {text_width} for {license_val}"
        )
        # chip must not be full-width
        assert chip.width() < page.width() // 2, (
            f"Chip width {chip.width()} should not be full-width for {license_val}"
        )
