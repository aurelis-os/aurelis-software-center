"""Uninstallation wizard for managed applications."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
)

from aurelis_software.wizards.detect import detect

if TYPE_CHECKING:
    from aurelis_software.core.config import Config
    from aurelis_software.core.paths import Paths


class UninstallWizard(QDialog):
    """Uninstallation wizard for managed applications.

    Parameters
    ----------
    path_or_desktop_id : Path
        Path to the file or desktop entry to uninstall
    backends : dict
        Available backends (appimage, flatpak, pacman)
    config : Config
        Application configuration
    paths : Paths
        Filesystem paths
    """

    def __init__(
        self,
        path_or_desktop_id: Path,
        backends: dict,
        config: Config,
        paths: Paths,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.path = path_or_desktop_id
        self.backends = backends
        self.config = config
        self.paths = paths
        self.setWindowTitle(self.tr("Uninstall Application"))
        self.setMinimumWidth(480)

        # Detect the application type
        self.detection = self._detect_application()

        # Build UI based on detection
        self._build_ui()

    def _detect_application(self):
        """Detect the application type."""
        applications_dir = Path.home() / ".local" / "share" / "applications-managed"
        flatpak_exports = [
            Path.home() / ".local" / "share" / "flatpak" / "exports" / "share" / "applications"
        ]
        core_packages = self.paths.cache_dir / "aurelis-software" / "core-packages.json"
        user_packages = self.paths.cache_dir / "aurelis-software" / "user-packages.json"

        def list_runner(cmd):
            """Run command and return (returncode, stdout, stderr)."""
            import subprocess

            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=10, check=False
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return (1, "", "")
            else:
                return (result.returncode, result.stdout, result.stderr)

        return detect(
            self.path,
            applications_dir=applications_dir,
            flatpak_export_dirs=flatpak_exports,
            core_packages_path=core_packages,
            user_packages_path=user_packages,
            list_runner=list_runner,
        )

    def _build_ui(self) -> None:
        """Build UI based on detection result."""
        if self.detection.kind == "pacman-system":
            self._build_refusal_page()
        elif self.detection.kind == "unknown":
            self._build_unknown_page()
        else:
            self._build_wizard_pages()

    def _build_refusal_page(self) -> None:
        """Build single-page refusal for system packages."""
        layout = QVBoxLayout(self)

        message = QLabel(
            self.tr(
                f"Cannot remove system package: {self.detection.name}\n\n"
                "System packages are managed by your distribution and cannot be "
                "removed through Aurelis Software Center."
            )
        )
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(message)

        layout.addStretch()

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton(self.tr("Close"))
        close_button.setAccessibleName(self.tr("Close"))
        close_button.clicked.connect(self.reject)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

    def _build_unknown_page(self) -> None:
        """Build explanation page for unknown files."""
        layout = QVBoxLayout(self)

        message = QLabel(
            self.tr(
                "This file is not managed by Aurelis Software Center.\n\n"
                "Only applications installed through Aurelis can be uninstalled here."
            )
        )
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(message)

        layout.addStretch()

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton(self.tr("Close"))
        close_button.setAccessibleName(self.tr("Close"))
        close_button.clicked.connect(self.reject)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

    def _build_wizard_pages(self) -> None:
        """Build two-page wizard for removable applications."""
        self.stack = QStackedWidget()

        # Page 1: Confirm
        page1 = self._build_confirm_page()
        self.stack.addWidget(page1)

        # Page 2: Progress
        page2 = self._build_progress_page()
        self.stack.addWidget(page2)

        layout = QVBoxLayout(self)
        layout.addWidget(self.stack)

    def _build_confirm_page(self):
        """Build Page 1: confirmation."""
        from PyQt6.QtWidgets import QWidget

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Icon
        icon_label = QLabel(self.tr("[Icon]"))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        # Name and type
        name_label = QLabel(self.detection.name)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = name_label.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        name_label.setFont(font)
        layout.addWidget(name_label)

        type_map = {
            "appimage": "AppImage",
            "flatpak": "Flatpak",
            "pacman-user": "User Package",
        }
        type_label = QLabel(type_map.get(self.detection.kind, "Application"))
        type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(type_label)

        # Confirmation message
        message = QLabel(self.tr("Are you sure you want to remove this application?"))
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(message)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        remove_button = QPushButton(self.tr("Remove"))
        remove_button.setAccessibleName(self.tr("Remove"))
        remove_button.clicked.connect(self._on_remove)
        button_layout.addWidget(remove_button)

        cancel_button = QPushButton(self.tr("Cancel"))
        cancel_button.setAccessibleName(self.tr("Cancel"))
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

        return widget

    def _build_progress_page(self):
        """Build Page 2: progress and result."""
        from PyQt6.QtWidgets import QWidget

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Status label
        self.status_label = QLabel(self.tr("Removing..."))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        layout.addWidget(self.progress_bar)

        layout.addStretch()

        # Done button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.done_button = QPushButton(self.tr("Done"))
        self.done_button.setAccessibleName(self.tr("Done"))
        self.done_button.setEnabled(False)
        self.done_button.clicked.connect(self.accept)
        button_layout.addWidget(self.done_button)

        layout.addLayout(button_layout)

        return widget

    def _on_remove(self) -> None:
        """Handle Remove button click."""
        self.stack.setCurrentIndex(1)
        self.status_label.setText(self.tr("Removing..."))

        if self.detection.kind == "appimage":
            self._remove_appimage()
        elif self.detection.kind == "flatpak":
            self._remove_flatpak()
        elif self.detection.kind == "pacman-user":
            self._remove_pacman_user()

    def _remove_appimage(self) -> None:
        """Remove AppImage using backend."""
        backend = self.backends.get("appimage")
        if not backend:
            self._on_remove_error(Exception("AppImage backend not available"))
            return

        options = {"file_action": "trash", "silent": True}
        backend.remove_async(
            self.detection.id,
            options,
            reply_cb=self._on_remove_success,
            error_cb=self._on_remove_error,
        )

    def _remove_flatpak(self) -> None:
        """Remove Flatpak using QProcess."""
        self.flatpak_process = QProcess(self)
        self.flatpak_process.finished.connect(self._on_flatpak_finished)
        self.flatpak_process.start("flatpak", ["uninstall", "--user", "-y", self.detection.id])

    def _on_flatpak_finished(self, exit_code: int, exit_status) -> None:
        """Handle Flatpak uninstall completion."""
        if exit_code == 0:
            self._on_remove_success(True)
        else:
            error_output = self.flatpak_process.readAllStandardError().data().decode()
            self._on_remove_error(Exception(f"Flatpak uninstall failed: {error_output}"))

    def _remove_pacman_user(self) -> None:
        """Remove user package using pkg command."""
        self.pacman_process = QProcess(self)
        self.pacman_process.finished.connect(self._on_pacman_finished)
        self.pacman_process.start("pkg", ["remove", self.detection.id])

    def _on_pacman_finished(self, exit_code: int, exit_status) -> None:
        """Handle pacman removal completion."""
        if exit_code == 0:
            self.status_label.setText(self.tr("Removal complete!\n(applies after restart)"))
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
            self.done_button.setEnabled(True)
        else:
            error_output = self.pacman_process.readAllStandardError().data().decode()
            self._on_remove_error(Exception(f"Package removal failed: {error_output}"))

    def _on_remove_success(self, result) -> None:
        """Handle successful removal."""
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.status_label.setText(self.tr("Removal complete!"))
        self.done_button.setEnabled(True)

    def _on_remove_error(self, error: Exception) -> None:
        """Handle removal error."""
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label.setText(self.tr(f"Removal failed: {error}"))
        self.done_button.setEnabled(True)
