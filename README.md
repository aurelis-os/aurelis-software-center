# Aurelis Software Center

A GNOME-Software-style application center for Aurelis, an immutable Arch Linux distribution.

Three software sources: AppImage (via `appimage-launcher` D-Bus API), Flathub, and Pacman (via `pkg`). Plus install/uninstall wizards.

See `docs/aurelis-software-gui-spec.md` for the full specification.

## Status

Phase 0 (contracts and spikes) in progress. See `docs/DECISIONS.md` and `docs/spikes/`.

## Development

```
python -m pip install -e ".[dev]"
./check
```

## License

Proprietary — Aurelis Software.
