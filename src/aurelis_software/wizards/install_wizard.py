"""Installation wizard for AppImages and Flatpak files."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from aurelis_software.backends.appimage import AppImageBackend
    from aurelis_software.core.config import Config
    from aurelis_software.core.paths import Paths


class InstallWizard(QDialog):
    """Installation wizard for AppImages and Flatpak files.

    Parameters
    ----------
    path : Path
        Path to the file to install
    backend : AppImageBackend
        Backend for AppImage operations
    config : Config
        Application configuration
    paths : Paths
        Filesystem paths
    """

    def __init__(
        self,
        path: Path,
        backend: AppImageBackend,
        config: Config,
        paths: Paths,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.path = path
        self.backend = backend
        self.config = config
        self.paths = paths
        self.setWindowTitle(self.tr("Install Application"))
        self.setMinimumWidth(480)

        # Routing: check if AppImage is already in applications_dir
        applications_dir = Path.home() / ".local" / "share" / "applications-managed"
        if path.suffix == ".AppImage" and path.parent == applications_dir:
            # Already installed, just run it
            QProcess.startDetached("appimage", ["run", path.stem])
            self.accept()
            return

        # Check "run without asking" list
        if self._should_run_without_asking():
            self._execute_file()
            self.accept()
            return

        # Build UI
        self._build_ui()
        self._load_app_info()

    def _should_run_without_asking(self) -> bool:
        """Check if this file is in the run-without-asking list."""
        try:
            sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError:
            return False

        run_list = self.config.get("wizard.run_without_asking", [])
        for entry in run_list:
            if (
                isinstance(entry, dict)
                and entry.get("app_id") == self.path.name
                and entry.get("sha256") == sha256
            ):
                return True
        return False

    def _build_ui(self) -> None:
        """Build the wizard UI with two pages."""
        self.stack = QStackedWidget()

        # Page 1: Action selection
        page1 = self._build_page1()
        self.stack.addWidget(page1)

        # Page 2: Progress and result
        page2 = self._build_page2()
        self.stack.addWidget(page2)

        layout = QVBoxLayout(self)
        layout.addWidget(self.stack)

    def _build_page1(self):
        """Build Page 1: action selection."""
        from PyQt6.QtWidgets import QWidget

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Icon
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        # Name and version
        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.name_label.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        self.name_label.setFont(font)
        layout.addWidget(self.name_label)

        self.version_label = QLabel()
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.version_label)

        # Relation wording
        self.relation_label = QLabel()
        self.relation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.relation_label)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()

        self.install_button = QPushButton(self.tr("Install"))
        self.install_button.setAccessibleName(self.tr("Install"))
        self.install_button.clicked.connect(self._on_install)
        button_layout.addWidget(self.install_button)

        just_run_layout = QVBoxLayout()
        self.just_run_button = QPushButton(self.tr("Just run"))
        self.just_run_button.setAccessibleName(self.tr("Just run"))
        self.just_run_button.clicked.connect(self._on_just_run)
        just_run_layout.addWidget(self.just_run_button)

        self.dont_ask_checkbox = QCheckBox(self.tr("Don't ask again"))
        self.dont_ask_checkbox.setAccessibleName(self.tr("Don't ask again for this application"))
        just_run_layout.addWidget(self.dont_ask_checkbox)
        button_layout.addLayout(just_run_layout)

        self.cancel_button = QPushButton(self.tr("Cancel"))
        self.cancel_button.setAccessibleName(self.tr("Cancel"))
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

        return widget

    def _build_page2(self):
        """Build Page 2: progress and result."""
        from PyQt6.QtWidgets import QWidget

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Status label
        self.status_label = QLabel(self.tr("Installing..."))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        layout.addWidget(self.progress_bar)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.open_button = QPushButton(self.tr("Open"))
        self.open_button.setAccessibleName(self.tr("Open"))
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._on_open)
        button_layout.addWidget(self.open_button)

        self.close_button = QPushButton(self.tr("Close"))
        self.close_button.setAccessibleName(self.tr("Close"))
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

        return widget

    def _load_app_info(self) -> None:
        """Load application info and update Page 1 labels."""
        # For AppImages, we could call backend.inspect_async
        # For simplicity, just show file name
        self.name_label.setText(self.path.stem)
        self.version_label.setText(self.tr("Version: Unknown"))
        self.relation_label.setText(self.tr("Not installed"))

        # Try to load icon
        if self.path.suffix == ".AppImage":
            self.icon_label.setText(self.tr("[AppImage icon]"))
        else:
            self.icon_label.setText(self.tr("[Icon]"))

    def _on_install(self) -> None:
        """Handle Install button click."""
        self.stack.setCurrentIndex(1)
        self.status_label.setText(self.tr("Installing..."))

        # For AppImages
        if self.path.suffix == ".AppImage":
            options = {"source_action": "copy", "conflict": "replace", "silent": True}
            self.backend.install_async(
                str(self.path),
                options,
                reply_cb=self._on_install_success,
                error_cb=self._on_install_error,
            )
        # For Flatpak files
        elif self.path.suffix in {".flatpakref", ".flatpak"}:
            self._install_flatpak()
        else:
            self._on_install_error(Exception("Unsupported file type"))

    def _install_flatpak(self) -> None:
        """Install Flatpak using QProcess."""
        self.flatpak_process = QProcess(self)
        self.flatpak_process.finished.connect(self._on_flatpak_finished)
        self.flatpak_process.start("flatpak", ["install", "--user", "-y", str(self.path)])

    def _on_flatpak_finished(self, exit_code: int, exit_status) -> None:
        """Handle Flatpak installation completion."""
        if exit_code == 0:
            self._on_install_success({})
        else:
            error_output = self.flatpak_process.readAllStandardError().data().decode()
            self._on_install_error(Exception(f"Flatpak install failed: {error_output}"))

    def _on_install_success(self, reply: dict) -> None:
        """Handle successful installation."""
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.status_label.setText(self.tr("Installation complete!"))
        self.open_button.setEnabled(True)
        self.installed_name = reply.get("name", self.path.stem)

    def _on_install_error(self, error: Exception) -> None:
        """Handle installation error."""
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label.setText(self.tr(f"Installation failed: {error}"))

    def _on_just_run(self) -> None:
        """Handle Just run button click."""
        if self.dont_ask_checkbox.isChecked():
            self._save_dont_ask_again()

        self._execute_file()
        self.accept()

    def _execute_file(self) -> None:
        """Execute the file directly."""
        if self.path.suffix == ".AppImage":
            # Make executable and run
            self.path.chmod(0o755)
            QProcess.startDetached(str(self.path), [])
        else:
            # For other file types, try to open with default handler
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

    def _save_dont_ask_again(self) -> None:
        """Save this file to the run-without-asking list."""
        try:
            sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError:
            return

        from aurelis_software.core.config import Config, save

        data = dict(self.config.data)
        data.setdefault("wizard", {})
        run_list = list(data["wizard"].get("run_without_asking", []))

        entry = {"app_id": self.path.name, "sha256": sha256}
        if entry not in run_list:
            run_list.append(entry)

        data["wizard"]["run_without_asking"] = run_list
        save(self.paths, Config(data))

    def _on_open(self) -> None:
        """Handle Open button click."""
        if hasattr(self, "installed_name"):
            QProcess.startDetached("appimage", ["run", self.installed_name])
        self.accept()
