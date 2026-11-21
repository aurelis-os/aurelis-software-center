"""Tests for desktop file validation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(
    shutil.which("desktop-file-validate") is None,
    reason="desktop-file-validate not in PATH",
)
def test_validate_install_desktop():
    """Test that aurelis-software-wizard-install.desktop is valid."""
    desktop_file = (
        Path(__file__).parent.parent.parent
        / "src"
        / "aurelis_software"
        / "resources"
        / "aurelis-software-wizard-install.desktop"
    )
    result = subprocess.run(
        ["desktop-file-validate", str(desktop_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Validation failed: {result.stderr}"


@pytest.mark.skipif(
    shutil.which("desktop-file-validate") is None,
    reason="desktop-file-validate not in PATH",
)
def test_validate_uninstall_desktop():
    """Test that aurelis-software-uninstall.desktop is valid."""
    desktop_file = (
        Path(__file__).parent.parent.parent
        / "src"
        / "aurelis_software"
        / "resources"
        / "aurelis-software-uninstall.desktop"
    )
    result = subprocess.run(
        ["desktop-file-validate", str(desktop_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Validation failed: {result.stderr}"
