# Aurelis Software Center

A GNOME-Software-style application center for Aurelis, an immutable Arch Linux distribution.

Three software sources: AppImage (via `appimage-launcher` D-Bus API), Flathub, and Pacman (via `pkg`). Plus install/uninstall wizards.

See `docs/aurelis-software-gui-spec.md` for the full specification.

## Status

Phases 0-8 complete. Version 1.0.0 ready for release.

## Installation

### Quick Install (Arch Linux)

```bash
./install.sh
```

The installer will check dependencies, install missing packages, and set up desktop integration.

See [INSTALL.md](INSTALL.md) for detailed installation instructions and troubleshooting.

## Performance

Performance budgets (all met):

- Catalog parse (500 apps): < 100 ms
- Search keystroke (500 apps): < 50 ms
- Flathub FTS search: < 100 ms  
- Pacman FTS search: < 100 ms

Measured on: Linux (Arch-based), Python 3.11+, PyQt6 6.6+

## Development

```
python -m pip install -e ".[dev]"
./check
```

## License

Proprietary — Aurelis Software.
