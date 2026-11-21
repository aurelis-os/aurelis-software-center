"""Tests for UninstallWizard."""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest

from aurelis_software.core.config import Config
from aurelis_software.core.paths import Paths
from aurelis_software.wizards.uninstall_wizard import UninstallWizard


@pytest.fixture
def mock_backends():
    """Create mock backends."""
    appimage = Mock()
    appimage.available = True
    return {"appimage": appimage}


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
    return Config({})


def test_system_package_refusal(qapp_session, tmp_path, mock_backends, test_paths, test_config):
    """Test that system packages show refusal page."""
    # Create package JSON files
    cache_dir = test_paths.cache_dir / "aurelis-software"
    cache_dir.mkdir(parents=True)
    core_packages = cache_dir / "core-packages.json"
    core_packages.write_text(json.dumps(["bash", "systemd"]))
    user_packages = cache_dir / "user-packages.json"
    user_packages.write_text(json.dumps([]))

    file_path = tmp_path / "testfile"
    file_path.write_text("content")

    def fake_runner(cmd):
        if cmd[0] == "pacman" and cmd[1] == "-Qo":
            return (0, f"{file_path} is owned by bash 5.2-1\n", "")
        return (1, "", "")

    with patch("aurelis_software.wizards.uninstall_wizard.detect") as mock_detect:
        from aurelis_software.wizards.detect import DetectionResult

        mock_detect.return_value = DetectionResult("pacman-system", "bash", "bash")
        wizard = UninstallWizard(file_path, mock_backends, test_config, test_paths)

        # Should not have stack (single page refusal)
        assert not hasattr(wizard, "stack")


def test_appimage_removal(qapp_session, tmp_path, mock_backends, test_paths, test_config):
    """Test that AppImage removal calls backend.remove_async."""
    appimage = tmp_path / "test.AppImage"
    appimage.write_text("fake")

    with patch("aurelis_software.wizards.uninstall_wizard.detect") as mock_detect:
        from aurelis_software.wizards.detect import DetectionResult

        mock_detect.return_value = DetectionResult("appimage", "test", "Test App")
        wizard = UninstallWizard(appimage, mock_backends, test_config, test_paths)

        wizard._on_remove()

        # Verify backend.remove_async was called
        mock_backends["appimage"].remove_async.assert_called_once()
        args = mock_backends["appimage"].remove_async.call_args
        assert args[0][0] == "test"
        assert args[0][1]["file_action"] == "trash"
        assert args[0][1]["silent"] is True


def test_flatpak_uninstall(qapp_session, tmp_path, mock_backends, test_paths, test_config):
    """Test that Flatpak uninstall triggers flatpak command."""
    desktop_file = tmp_path / "org.kde.kate.desktop"
    desktop_file.write_text("[Desktop Entry]\nName=Kate\n")

    with patch("aurelis_software.wizards.uninstall_wizard.detect") as mock_detect:
        from aurelis_software.wizards.detect import DetectionResult

        mock_detect.return_value = DetectionResult("flatpak", "org.kde.kate", "Kate")
        wizard = UninstallWizard(desktop_file, mock_backends, test_config, test_paths)

        with patch.object(wizard, "_remove_flatpak") as mock_flatpak:
            wizard._on_remove()
            mock_flatpak.assert_called_once()


def test_pacman_user_with_restart_note(qapp_session, tmp_path, mock_backends, test_paths, test_config):
    """Test that pacman user removal shows restart note."""
    cache_dir = test_paths.cache_dir / "aurelis-software"
    cache_dir.mkdir(parents=True)
    user_packages = cache_dir / "user-packages.json"
    user_packages.write_text(json.dumps(["kate"]))

    file_path = tmp_path / "testfile"
    file_path.write_text("content")

    with patch("aurelis_software.wizards.uninstall_wizard.detect") as mock_detect:
        from aurelis_software.wizards.detect import DetectionResult

        mock_detect.return_value = DetectionResult("pacman-user", "kate", "kate")
        wizard = UninstallWizard(file_path, mock_backends, test_config, test_paths)

        # Simulate successful removal
        with patch.object(wizard, "pacman_process", create=True):
            wizard._on_remove()
            # Trigger finished signal
            wizard._on_pacman_finished(0, None)

            # Check for restart note in status
            assert "restart" in wizard.status_label.text().lower()


def test_unknown_file(qapp_session, tmp_path, mock_backends, test_paths, test_config):
    """Test that unknown files show explanation page."""
    unknown_file = tmp_path / "unknown.bin"
    unknown_file.write_text("content")

    with patch("aurelis_software.wizards.uninstall_wizard.detect") as mock_detect:
        from aurelis_software.wizards.detect import DetectionResult

        mock_detect.return_value = DetectionResult("unknown", "", "")
        wizard = UninstallWizard(unknown_file, mock_backends, test_config, test_paths)

        # Should not have stack (single page explanation)
        assert not hasattr(wizard, "stack")
