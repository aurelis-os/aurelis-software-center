"""File detection for installation and uninstallation wizards."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DetectionResult:
    """Result of file detection.

    Attributes
    ----------
    kind : str
        One of: "appimage", "flatpak", "pacman-system", "pacman-user", "unknown"
    id : str
        Application identifier (basename for AppImage, app ID for Flatpak, package name for Pacman)
    name : str
        Human-readable name
    """

    kind: str
    id: str
    name: str


def detect(
    path: Path,
    *,
    applications_dir: Path,
    flatpak_export_dirs: list[Path],
    core_packages_path: Path,
    user_packages_path: Path,
    list_runner: Callable[[list[str]], tuple[int, str, str]],
) -> DetectionResult:
    """Detect the type and identity of a file.

    Detection order:
    1. AppImage in applications_dir (by filename match)
    2. Desktop entry with X-AppImage-Managed=true
    3. Desktop entry in Flatpak exports
    4. Pacman package in core-packages.json
    5. Pacman package in user-packages.json
    6. Unknown

    Parameters
    ----------
    path : Path
        Path to detect
    applications_dir : Path
        Directory where managed AppImages are stored
    flatpak_export_dirs : list[Path]
        Directories where Flatpak exports desktop files
    core_packages_path : Path
        Path to core-packages.json
    user_packages_path : Path
        Path to user-packages.json
    list_runner : Callable[[list[str]], tuple[int, str, str]]
        Function to run commands (for pacman -Qo)

    Returns
    -------
    DetectionResult
        Detected kind, id, and name
    """
    # (1) AppImage in applications_dir
    if path.suffix == ".AppImage" and path.parent == applications_dir:
        return DetectionResult("appimage", path.stem, path.stem)

    # (2) Desktop entry with X-AppImage-Managed=true
    if path.suffix == ".desktop":
        result = _check_desktop_appimage(path)
        if result:
            return result

        # (3) Desktop entry in Flatpak exports
        result = _check_desktop_flatpak(path, flatpak_export_dirs)
        if result:
            return result

    # (4) Pacman package in core-packages.json
    result = _check_pacman(path, core_packages_path, "pacman-system", list_runner)
    if result:
        return result

    # (5) Pacman package in user-packages.json
    result = _check_pacman(path, user_packages_path, "pacman-user", list_runner)
    if result:
        return result

    # (6) Unknown
    return DetectionResult("unknown", "", "")


def _check_desktop_appimage(path: Path) -> DetectionResult | None:
    """Check if desktop file is an AppImage-managed entry."""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    lines = content.splitlines()
    has_managed = False
    name = ""
    managed_name = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("X-AppImage-Managed="):
            value = stripped.split("=", 1)[1].strip()
            if value.lower() == "true":
                has_managed = True
        elif stripped.startswith("Name="):
            name = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("X-AppImage-Name="):
            managed_name = stripped.split("=", 1)[1].strip()

    if has_managed:
        # Use managed_name if available, otherwise fall back to Name or stem
        id_name = managed_name or name or path.stem
        display_name = name or managed_name or path.stem
        return DetectionResult("appimage", id_name, display_name)

    return None


def _check_desktop_flatpak(path: Path, flatpak_export_dirs: list[Path]) -> DetectionResult | None:
    """Check if desktop file is in Flatpak export directories."""
    if path.parent not in flatpak_export_dirs:
        return None

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    # Extract app ID from filename (strip .desktop suffix)
    app_id = path.stem

    # Extract Name from desktop file
    name = ""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("Name="):
            name = stripped.split("=", 1)[1].strip()
            break

    return DetectionResult("flatpak", app_id, name or app_id)


def _check_pacman(
    path: Path,
    packages_json: Path,
    kind: str,
    list_runner: Callable[[list[str]], tuple[int, str, str]],
) -> DetectionResult | None:
    """Check if file is owned by a Pacman package."""
    # Run pacman -Qo
    returncode, stdout, _stderr = list_runner(["pacman", "-Qo", str(path)])
    if returncode != 0:
        return None

    # Parse output: "file is owned by package version"
    # Example: "/usr/bin/kate is owned by kate 23.08.4-1"
    for line in stdout.splitlines():
        if " is owned by " in line:
            package_part = line.split(" is owned by ", 1)[1].strip()
            # Extract package name (first token before version)
            package_name = package_part.split()[0] if package_part else ""
            if not package_name:
                return None

            # Check if package is in the specified JSON file
            try:
                with packages_json.open("r", encoding="utf-8") as f:
                    packages = json.load(f)
                if package_name in packages:
                    return DetectionResult(kind, package_name, package_name)
            except (OSError, json.JSONDecodeError):
                return None

    return None
