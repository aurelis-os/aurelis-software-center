"""Tests for InstallWizard."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from aurelis_software.core.config import Config
from aurelis_software.core.paths import Paths
from aurelis_software.wizards.install_wizard import InstallWizard


@pytest.fixture
def mock_backend():
    """Create a mock AppImageBackend."""
    backend = Mock()
    backend.available = True
    return backend


@pytest.fixture
def test_paths(tmp_path):
    """Create test paths."""
    return Paths(
        config_dir=tmp_path / "config",
        cache_dir=tmp_path / "cache",
        state_dir=tmp_path / "state",
    )


@pytest.fixture
def test_config():
    """Create test config."""
    return Config({"wizard": {"run_without_asking": []}})


def test_routing_appimage_in_folder(qapp_session, tmp_path, mock_backend, test_paths, test_config):
    """Test that AppImage in applications folder runs directly."""
    apps_dir = Path.home() / ".local" / "share" / "applications-managed"
    apps_dir.mkdir(parents=True, exist_ok=True)
    
    appimage = apps_dir / "test.AppImage"
    appimage.write_text("fake")

    with patch("aurelis_software.wizards.install_wizard.QProcess.startDetached") as mock_start:
        wizard = InstallWizard(appimage, mock_backend, test_config, test_paths)
        # Wizard should auto-accept and not show UI
        assert wizard.result() == wizard.DialogCode.Accepted
        mock_start.assert_called_once_with("appimage", ["run", "test"])

    # Cleanup
    appimage.unlink()


def test_page1_ui(qapp_session, tmp_path, mock_backend, test_paths, test_config):
    """Test that Page 1 has correct widgets."""
    appimage = tmp_path / "test.AppImage"
    appimage.write_text("fake")

    wizard = InstallWizard(appimage, mock_backend, test_config, test_paths)
    
    # Check that wizard has expected widgets
    assert hasattr(wizard, "stack")
    assert hasattr(wizard, "name_label")
    assert hasattr(wizard, "install_button")
    assert hasattr(wizard, "just_run_button")
    assert hasattr(wizard, "dont_ask_checkbox")
    assert hasattr(wizard, "cancel_button")


def test_install_action(qapp_session, tmp_path, mock_backend, test_paths, test_config):
    """Test that Install button calls backend.install_async."""
    appimage = tmp_path / "test.AppImage"
    appimage.write_text("fake")

    wizard = InstallWizard(appimage, mock_backend, test_config, test_paths)
    wizard._on_install()

    # Verify backend.install_async was called
    mock_backend.install_async.assert_called_once()
    args = mock_backend.install_async.call_args
    assert args[0][0] == str(appimage)
    assert args[0][1]["source_action"] == "copy"
    assert args[0][1]["conflict"] == "replace"


def test_just_run(qapp_session, tmp_path, mock_backend, test_paths, test_config):
    """Test that Just run executes the file."""
    appimage = tmp_path / "test.AppImage"
    appimage.write_text("fake")

    wizard = InstallWizard(appimage, mock_backend, test_config, test_paths)

    with patch("aurelis_software.wizards.install_wizard.QProcess.startDetached") as mock_start:
        wizard._on_just_run()
        mock_start.assert_called_once()


def test_dont_ask_again(qapp_session, tmp_path, mock_backend, test_paths, test_config):
    """Test that 'Don't ask again' stores entry in config."""
    appimage = tmp_path / "test.AppImage"
    appimage.write_text("fake content for hashing")

    # Ensure config directory exists
    test_paths.config_file.parent.mkdir(parents=True, exist_ok=True)

    wizard = InstallWizard(appimage, mock_backend, test_config, test_paths)
    wizard.dont_ask_checkbox.setChecked(True)

    with patch("aurelis_software.wizards.install_wizard.QProcess.startDetached"):
        wizard._on_just_run()

    # Check that config was saved with the entry
    from aurelis_software.core.config import load
    saved_config = load(test_paths)
    run_list = saved_config.get("wizard.run_without_asking", [])
    assert len(run_list) == 1
    assert run_list[0]["app_id"] == "test.AppImage"
    assert "sha256" in run_list[0]


def test_flatpak_file(qapp_session, tmp_path, mock_backend, test_paths, test_config):
    """Test that Flatpak files trigger flatpak command."""
    flatpak_file = tmp_path / "test.flatpakref"
    flatpak_file.write_text("fake")

    wizard = InstallWizard(flatpak_file, mock_backend, test_config, test_paths)

    with patch.object(wizard, "_install_flatpak") as mock_flatpak:
        wizard._on_install()
        mock_flatpak.assert_called_once()


def test_startup_time(qapp_session, tmp_path, mock_backend, test_paths, test_config):
    """Test that wizard startup is under 500ms."""
    appimage = tmp_path / "test.AppImage"
    appimage.write_text("fake")

    start = time.time()
    wizard = InstallWizard(appimage, mock_backend, test_config, test_paths)
    # Ensure the wizard is ready to show (page 1 built)
    wizard.show()
    elapsed = time.time() - start

    assert elapsed < 0.5, f"Startup took {elapsed:.3f}s, expected < 0.5s"
