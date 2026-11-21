"""Accessibility tests (Phase 8, Task 5.4)."""

from __future__ import annotations

from aurelis_software.ui.theme import assert_badge_contrast


def test_badge_contrast_wcag_aa(qtbot):
    """Test that all badge colors meet WCAG AA contrast ratio (4.5:1)."""
    # This will raise AssertionError if any badge fails
    assert_badge_contrast()
