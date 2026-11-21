"""Settings dialog (section 10.6)."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from aurelis_software.core.config import Config, save
from aurelis_software.core.paths import Paths


class SettingsDialog(QDialog):
    """Settings: catalog, language, offline mode, and advanced URLs."""

    def __init__(self, paths: Paths, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.paths = paths
        self.config = config
        self.setWindowTitle(self.tr("Settings"))
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)

        catalog = QGroupBox(self.tr("Catalog"))
        catalog_layout = QGridLayout(catalog)
        row = 0
        self.refresh_hours = QSpinBox()
        self.refresh_hours.setRange(1, 720)
        self.refresh_hours.setValue(int(self.config.get("catalog.refresh_hours") or 24))
        catalog_layout.addWidget(QLabel(self.tr("Refresh every (hours):")), row, 0)
        catalog_layout.addWidget(self.refresh_hours, row, 1)
        row += 1
        self.refresh_now = QPushButton(self.tr("Refresh now"))
        catalog_layout.addWidget(self.refresh_now, row, 0, 1, 2)
        row += 1
        self.apps_url = QLineEdit(str(self.config.get("catalog.apps_url") or ""))
        self.apps_url.setPlaceholderText(self.tr("Catalog apps URL"))
        catalog_layout.addWidget(QLabel(self.tr("Catalog apps URL:")), row, 0)
        catalog_layout.addWidget(self.apps_url, row, 1)
        row += 1
        self.icons_url = QLineEdit(str(self.config.get("catalog.icons_url") or ""))
        self.icons_url.setPlaceholderText(self.tr("Catalog icons URL"))
        catalog_layout.addWidget(QLabel(self.tr("Catalog icons URL:")), row, 0)
        catalog_layout.addWidget(self.icons_url, row, 1)
        layout.addWidget(catalog)

        ui_box = QGroupBox(self.tr("Interface"))
        ui_layout = QVBoxLayout(ui_box)
        self.offline = QCheckBox(self.tr("Offline mode"))
        self.offline.setChecked(bool(self.config.get("network.offline")))
        ui_layout.addWidget(self.offline)
        self.show_proprietary = QCheckBox(self.tr("Show proprietary software"))
        self.show_proprietary.setChecked(bool(self.config.get("ui.show_proprietary")))
        ui_layout.addWidget(self.show_proprietary)
        self.hide_incompatible = QCheckBox(self.tr("Hide incompatible architecture"))
        self.hide_incompatible.setChecked(bool(self.config.get("ui.hide_incompatible")))
        ui_layout.addWidget(self.hide_incompatible)
        self.include_self_managed = QCheckBox(self.tr("Include self-updating apps in Updates"))
        self.include_self_managed.setChecked(bool(self.config.get("updates.include_self_managed")))
        ui_layout.addWidget(self.include_self_managed)
        self.notify_updates = QCheckBox(self.tr("Notify about updates"))
        self.notify_updates.setChecked(bool(self.config.get("updates.notify")))
        ui_layout.addWidget(self.notify_updates)
        layout.addWidget(ui_box)

        # Wizards section
        wizards_box = QGroupBox(self.tr("Wizards"))
        wizards_layout = QVBoxLayout(wizards_box)
        wizards_layout.addWidget(QLabel(self.tr("Run without asking:")))

        from PyQt6.QtWidgets import QListWidget

        self.run_without_asking_list = QListWidget()
        self._populate_run_without_asking()
        wizards_layout.addWidget(self.run_without_asking_list)
        layout.addWidget(wizards_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_run_without_asking(self) -> None:
        """Populate the run-without-asking list widget."""
        self.run_without_asking_list.clear()
        run_list = self.config.get("wizard.run_without_asking", [])

        for entry in run_list:
            if isinstance(entry, dict):
                app_id = entry.get("app_id", "")
                item_widget = self._create_list_item(app_id, entry)
                from PyQt6.QtWidgets import QListWidgetItem

                list_item = QListWidgetItem(self.run_without_asking_list)
                list_item.setSizeHint(item_widget.sizeHint())
                self.run_without_asking_list.addItem(list_item)
                self.run_without_asking_list.setItemWidget(list_item, item_widget)

    def _create_list_item(self, app_id: str, entry: dict):
        """Create a list item widget with Remove button."""
        from PyQt6.QtWidgets import QWidget

        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        label = QLabel(app_id)
        layout.addWidget(label)
        layout.addStretch()

        remove_btn = QPushButton(self.tr("Remove"))
        remove_btn.clicked.connect(lambda: self._remove_entry(entry))
        layout.addWidget(remove_btn)

        return widget

    def _remove_entry(self, entry: dict) -> None:
        """Remove an entry from the run-without-asking list."""
        data = dict(self.config.data)
        run_list = data.get("wizard", {}).get("run_without_asking", [])
        if entry in run_list:
            run_list.remove(entry)
            from aurelis_software.core.config import Config

            self.config = Config(data)
            save(self.paths, self.config)
            self._populate_run_without_asking()

    def _save(self) -> None:
        data = dict(self.config.data)
        data.setdefault("catalog", {})["refresh_hours"] = self.refresh_hours.value()
        data["catalog"]["apps_url"] = self.apps_url.text().strip() or None
        data["catalog"]["icons_url"] = self.icons_url.text().strip() or None
        data.setdefault("network", {})["offline"] = self.offline.isChecked()
        data.setdefault("ui", {})["show_proprietary"] = self.show_proprietary.isChecked()
        data["ui"]["hide_incompatible"] = self.hide_incompatible.isChecked()
        data.setdefault("updates", {})["include_self_managed"] = (
            self.include_self_managed.isChecked()
        )
        data["updates"]["notify"] = self.notify_updates.isChecked()
        save(self.paths, Config(data))
        self.accept()
