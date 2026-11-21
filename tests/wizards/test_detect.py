"""Tests for file detection logic."""

from __future__ import annotations

import json

from aurelis_software.wizards import detect


def test_appimage_in_applications_dir(tmp_path):
    """Test detection of AppImage in applications directory."""
    apps_dir = tmp_path / "applications"
    apps_dir.mkdir()
    appimage = apps_dir / "kate.AppImage"
    appimage.write_text("fake appimage")

    result = detect(
        appimage,
        applications_dir=apps_dir,
        flatpak_export_dirs=[],
        core_packages_path=tmp_path / "core.json",
        user_packages_path=tmp_path / "user.json",
        list_runner=lambda cmd: (1, "", ""),
    )

    assert result.kind == "appimage"
    assert result.id == "kate"
    assert result.name == "kate"


def test_desktop_entry_with_appimage_managed(tmp_path):
    """Test detection of desktop entry with X-AppImage-Managed=true."""
    desktop_file = tmp_path / "test.desktop"
    desktop_file.write_text(
        "[Desktop Entry]\nName=Kate Editor\nX-AppImage-Managed=true\nX-AppImage-Name=kate\n"
    )

    result = detect(
        desktop_file,
        applications_dir=tmp_path / "apps",
        flatpak_export_dirs=[],
        core_packages_path=tmp_path / "core.json",
        user_packages_path=tmp_path / "user.json",
        list_runner=lambda cmd: (1, "", ""),
    )

    assert result.kind == "appimage"
    assert result.id == "kate"
    assert result.name == "Kate Editor"


def test_desktop_entry_in_flatpak_exports(tmp_path):
    """Test detection of desktop entry in Flatpak export directories."""
    flatpak_dir = tmp_path / "flatpak" / "exports" / "share" / "applications"
    flatpak_dir.mkdir(parents=True)
    desktop_file = flatpak_dir / "org.kde.kate.desktop"
    desktop_file.write_text("[Desktop Entry]\nName=Kate\n")

    result = detect(
        desktop_file,
        applications_dir=tmp_path / "apps",
        flatpak_export_dirs=[flatpak_dir],
        core_packages_path=tmp_path / "core.json",
        user_packages_path=tmp_path / "user.json",
        list_runner=lambda cmd: (1, "", ""),
    )

    assert result.kind == "flatpak"
    assert result.id == "org.kde.kate"
    assert result.name == "Kate"


def test_pacman_core_package(tmp_path):
    """Test detection of pacman core package."""
    file_path = tmp_path / "some-file"
    file_path.write_text("content")

    core_packages = tmp_path / "core.json"
    core_packages.write_text(json.dumps(["bash", "systemd", "linux"]))

    def fake_runner(cmd):
        if cmd == ["pacman", "-Qo", str(file_path)]:
            return (0, "/some-file is owned by bash 5.2-1\n", "")
        return (1, "", "")

    result = detect(
        file_path,
        applications_dir=tmp_path / "apps",
        flatpak_export_dirs=[],
        core_packages_path=core_packages,
        user_packages_path=tmp_path / "user.json",
        list_runner=fake_runner,
    )

    assert result.kind == "pacman-system"
    assert result.id == "bash"
    assert result.name == "bash"


def test_pacman_user_package(tmp_path):
    """Test detection of pacman user package."""
    file_path = tmp_path / "some-file"
    file_path.write_text("content")

    core_packages = tmp_path / "core.json"
    core_packages.write_text(json.dumps(["bash", "systemd"]))

    user_packages = tmp_path / "user.json"
    user_packages.write_text(json.dumps(["kate", "firefox"]))

    def fake_runner(cmd):
        if cmd == ["pacman", "-Qo", str(file_path)]:
            return (0, "/some-file is owned by kate 23.08.4-1\n", "")
        return (1, "", "")

    result = detect(
        file_path,
        applications_dir=tmp_path / "apps",
        flatpak_export_dirs=[],
        core_packages_path=core_packages,
        user_packages_path=user_packages,
        list_runner=fake_runner,
    )

    assert result.kind == "pacman-user"
    assert result.id == "kate"
    assert result.name == "kate"


def test_unknown_file(tmp_path):
    """Test detection of unknown file."""
    file_path = tmp_path / "unknown.bin"
    file_path.write_text("content")

    result = detect(
        file_path,
        applications_dir=tmp_path / "apps",
        flatpak_export_dirs=[],
        core_packages_path=tmp_path / "core.json",
        user_packages_path=tmp_path / "user.json",
        list_runner=lambda cmd: (1, "", ""),
    )

    assert result.kind == "unknown"
    assert result.id == ""
    assert result.name == ""
