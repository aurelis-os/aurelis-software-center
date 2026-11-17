"""Entry point: ``python -m aurelis_software``.

No arguments (or ``--open``/``--search``) launches the GUI. ``cli <cmd>`` runs
the developer CLI (catalog refresh/list, search, show). ``wizard install|<path>``
and ``wizard uninstall <path>`` are Phase 7 entry points.
"""

from __future__ import annotations

import sys

from aurelis_software.cli import main as cli_main


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        from aurelis_software.ui.app import main as gui_main

        return gui_main(argv)
    if argv[0] == "cli":
        return cli_main(argv[1:])
    if argv[0] == "wizard":
        print("wizard install|uninstall are Phase 7; not yet implemented", file=sys.stderr)
        return 2
    # Anything else (--open=..., --search=..., bare flags) launches the GUI.
    from aurelis_software.ui.app import main as gui_main

    return gui_main(argv)


if __name__ == "__main__":
    sys.exit(main())
