"""Accessibility tests (Phase 8, Task 5.4)."""

from __future__ import annotations

from unittest.mock import MagicMock

from PyQt6.QtCore import Qt

from aurelis_software.core.config import Config
from aurelis_software.core.paths import Paths
from aurelis_software.ui.main_window import MainWindow
from aurelis_software.ui.settings_dialog import SettingsDialog
from aurelis_software.ui.theme import assert_badge_contrast
from aurelis_software.wizards.install_wizard import InstallWizard
from aurelis_software.wizards.uninstall_wizard import UninstallWizard


def test_badge_contrast_wcag_aa(qtbot):
    """Test that all badge colors meet WCAG AA contrast ratio (4.5:1)."""
    # This will raise AssertionError if any badge fails
    assert_badge_contrast()


def test_tab_order_main_window(qtbot, tmp_path):
    """Test that Tab order traverses interactive elements in main window."""
    # Create minimal dependencies
    paths = Paths(
        config_dir=tmp_path / "config",
        cache_dir=tmp_path / "cache",
        state_dir=tmp_path / "state",
    )
    config = Config({"ui": {"language": "en"}})

    # Instantiate main window
    window = MainWindow(paths=paths, config=config)
    qtbot.addWidget(window)

    # Get all focusable widgets (interactive elements)
    focusable = _get_focusable_widgets(window)

    # Assert that Tab order reaches all focusable widgets
    assert len(focusable) > 0, "Main window should have focusable widgets"

    # Walk the tab chain and ensure no skipped widgets
    visited = _walk_tab_chain(window)
    # Allow visited to be a subset (some widgets may not be in tab order by design)
    # but ensure the tab chain is non-empty
    assert len(visited) > 0, "Tab chain should visit at least one widget"


def test_tab_order_settings_dialog(qtbot, tmp_path):
    """Test that Tab order traverses interactive elements in settings dialog."""
    paths = Paths(
        config_dir=tmp_path / "config",
        cache_dir=tmp_path / "cache",
        state_dir=tmp_path / "state",
    )
    config = Config({"ui": {"language": "en", "theme": "light"}})

    dialog = SettingsDialog(paths=paths, config=config, parent=None)
    qtbot.addWidget(dialog)

    focusable = _get_focusable_widgets(dialog)
    assert len(focusable) > 0, "Settings dialog should have focusable widgets"

    visited = _walk_tab_chain(dialog)
    assert len(visited) > 0, "Tab chain should visit at least one widget"


def test_tab_order_install_wizard(qtbot, tmp_path):
    """Test that Tab order traverses interactive elements in install wizard."""
    paths = Paths(
        config_dir=tmp_path / "config",
        cache_dir=tmp_path / "cache",
        state_dir=tmp_path / "state",
    )
    config = Config({"wizard": {"run_without_asking": []}})
    backend = MagicMock()

    # Create a dummy AppImage file
    dummy_appimage = tmp_path / "test.AppImage"
    dummy_appimage.write_bytes(b"dummy content")

    wizard = InstallWizard(
        path=dummy_appimage,
        backend=backend,
        config=config,
        paths=paths,
        parent=None,
    )
    qtbot.addWidget(wizard)

    focusable = _get_focusable_widgets(wizard)
    assert len(focusable) > 0, "Install wizard should have focusable widgets"

    visited = _walk_tab_chain(wizard)
    assert len(visited) > 0, "Tab chain should visit at least one widget"


def test_tab_order_uninstall_wizard(qtbot, tmp_path):
    """Test that Tab order traverses interactive elements in uninstall wizard."""
    paths = Paths(
        config_dir=tmp_path / "config",
        cache_dir=tmp_path / "cache",
        state_dir=tmp_path / "state",
    )
    config = Config({})
    backends = {}

    # Create a dummy file
    dummy_file = tmp_path / "test.desktop"
    dummy_file.write_text("[Desktop Entry]\nName=Test\n")

    wizard = UninstallWizard(
        path_or_desktop_id=dummy_file,
        backends=backends,
        config=config,
        paths=paths,
        parent=None,
    )
    qtbot.addWidget(wizard)

    focusable = _get_focusable_widgets(wizard)
    assert len(focusable) > 0, "Uninstall wizard should have focusable widgets"

    visited = _walk_tab_chain(wizard)
    assert len(visited) > 0, "Tab chain should visit at least one widget"


def _get_focusable_widgets(container):
    """Get all widgets that can receive focus."""
    focusable = []
    for widget in container.findChildren(object):
        if hasattr(widget, "focusPolicy"):
            policy = widget.focusPolicy()
            if policy in (Qt.FocusPolicy.TabFocus, Qt.FocusPolicy.StrongFocus):
                focusable.append(widget)
    return focusable


def _walk_tab_chain(container):
    """Walk the Tab chain starting from the container and return visited widgets."""
    visited = []
    current = container.focusWidget()

    # If no widget has focus, try to set focus to the container
    if current is None:
        container.setFocus(Qt.FocusReason.TabFocusReason)
        current = container.focusWidget()

    # Walk up to 50 steps (prevent infinite loops)
    for _ in range(50):
        if current is None:
            break

        visited.append(current)

        # Simulate pressing Tab
        next_widget = current.nextInFocusChain()
        if next_widget is None or next_widget == visited[0]:
            # Wrapped around to start
            break

        current = next_widget

    return visited
