"""QApplication setup, single instance, and GUI main (sections P2.1, 10.8)."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QTimer, QTranslator
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

from aurelis_software.core.config import load
from aurelis_software.core.paths import Paths
from aurelis_software.ui.main_window import MainWindow

SERVER_NAME = "aurelis-software"


def _single_instance() -> QLocalServer | None:
    """Ensure only one GUI instance runs per user. Returns the server or None."""
    server = QLocalServer()
    if server.listen(SERVER_NAME):
        return server
    # Another instance is running; tell it to raise its window.
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    socket.waitForConnected(500)
    return None


def main(argv: list[str] | None = None) -> int:
    """Launch the GUI. Returns the Qt exit code."""
    argv = list(argv or sys.argv[1:])
    # Forward any `--open` / `--search` target after the window is shown.
    target: str | None = None
    args = []
    for arg in argv:
        if arg.startswith("--open="):
            target = arg.split("=", 1)[1]
        elif arg == "--open" and len(argv) > argv.index(arg) + 1:
            target = argv[argv.index(arg) + 1]
        elif arg.startswith("--search="):
            target = arg.split("=", 1)[1]
        else:
            args.append(arg)

    app = QApplication.instance() or QApplication(args)
    app.setApplicationName("Aurelis Software")
    app.setApplicationDisplayName("Aurelis Software")

    _single_instance()

    paths = Paths.xdg()
    config = load(paths)

    # Load translator for configured language (R26.1)
    language = config.get("ui.language", "en")
    translator = None
    if language != "en":
        translator = QTranslator()
        qm_path = paths.data_dir / "resources" / "i18n" / f"{language}.qm"
        # Also check installed location
        if not qm_path.exists():
            import os

            import aurelis_software

            module_dir = os.path.dirname(aurelis_software.__file__)
            qm_path = os.path.join(module_dir, "resources", "i18n", f"{language}.qm")
        if translator.load(str(qm_path)):
            app.installTranslator(translator)
        # Keep reference to prevent garbage collection
        app._translator = translator

    window = MainWindow(paths, config)
    window.show()

    if target:
        # Defer until the event loop is running so the window is visible.
        QTimer.singleShot(0, lambda: _handle_target(window, target))

    return app.exec()


def _handle_target(window: MainWindow, target: str) -> None:
    # Placeholder for --open / --search wiring (Phase 2 keeps Explore open).
    window._search.setText(target)
