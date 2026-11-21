"""Entry point: ``python -m aurelis_software``.

No arguments (or ``--open``/``--search``) launches the GUI. ``cli <cmd>`` runs
the developer CLI (catalog refresh/list, search, show). ``wizard install|<path>``
and ``wizard uninstall <path>`` are Phase 7 entry points.
"""

from __future__ import annotations

import sys
from pathlib import Path

from aurelis_software.cli import main as cli_main


def _wizard_install(path_str: str) -> int:
    """Handle wizard install subcommand."""
    from PyQt6.QtDBus import QDBusConnection
    from PyQt6.QtWidgets import QApplication

    from aurelis_software.backends.appimage import AppImageBackend
    from aurelis_software.core.config import load
    from aurelis_software.core.paths import Paths
    from aurelis_software.services.qt_dbus import DbusClient
    from aurelis_software.wizards.install_wizard import InstallWizard

    _app = QApplication(sys.argv[:1])
    paths = Paths.xdg()
    config = load(paths)
    path = Path(path_str)

    # Build backend
    client = DbusClient(QDBusConnection.sessionBus())
    backend = AppImageBackend(client)

    wizard = InstallWizard(path, backend, config, paths)
    result = wizard.exec()

    return 0 if result == wizard.DialogCode.Accepted else 2


def _wizard_uninstall(path_str: str) -> int:
    """Handle wizard uninstall subcommand."""
    from PyQt6.QtDBus import QDBusConnection
    from PyQt6.QtWidgets import QApplication

    from aurelis_software.backends.appimage import AppImageBackend
    from aurelis_software.core.config import load
    from aurelis_software.core.paths import Paths
    from aurelis_software.services.qt_dbus import DbusClient
    from aurelis_software.wizards.uninstall_wizard import UninstallWizard

    _app = QApplication(sys.argv[:1])
    paths = Paths.xdg()
    config = load(paths)
    path = Path(path_str)

    # Build backends
    client = DbusClient(QDBusConnection.sessionBus())
    backends = {"appimage": AppImageBackend(client)}

    wizard = UninstallWizard(path, backends, config, paths)
    result = wizard.exec()

    return 0 if result == wizard.DialogCode.Accepted else 2


def main(argv=None) -> int:  # noqa: PLR0911
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        from aurelis_software.ui.app import main as gui_main

        return gui_main(argv)
    if argv[0] == "cli":
        return cli_main(argv[1:])
    if argv[0] == "wizard":
        MIN_WIZARD_ARGS = 3
        if len(argv) < MIN_WIZARD_ARGS:
            print("Usage: aurelis-software wizard install|uninstall <path>", file=sys.stderr)
            return 2
        subcommand = argv[1]
        if subcommand == "install":
            return _wizard_install(argv[2])
        if subcommand == "uninstall":
            return _wizard_uninstall(argv[2])
        print(f"Unknown wizard subcommand: {subcommand}", file=sys.stderr)
        return 2
    # Anything else (--open=..., --search=..., bare flags) launches the GUI.
    from aurelis_software.ui.app import main as gui_main

    return gui_main(argv)


if __name__ == "__main__":
    sys.exit(main())
