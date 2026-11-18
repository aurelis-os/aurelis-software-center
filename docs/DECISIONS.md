# Decisions Log

## 2026-11-17: D-Bus Service Name for appimage-launcher Manager1

**Decision**: The D-Bus service name is `io.github.appimage_launcher.Manager`, taken from the launcher's `constants.py` (`DBUS_SERVICE_NAME`). The object path is `/io/github/appimage_launcher/Manager` and the interface is `io.github.appimage_launcher.Manager1`.

**Rationale**: The launcher's source of truth is its `constants.py` which defines `DBUS_SERVICE_NAME = "io.github.appimage_launcher.Manager"`. This repository must use the same constant. In the GUI, define this constant once in `core/` or `backends/` constants module, not repeated across files.

**Files affected**:
- `tools/qtdbus_probe.py`: updated `SERVICE` constant
- `docs/contracts/manager1-notes.md`: updated service name, removed placeholder note
- `docs/contracts/manager1.xml`: updated comments, removed placeholder note
- `docs/spikes/qtdbus.md`: updated service name reference
- `docs/aurelis-software-gui-spec.md`: updated sections 9.1 and 15.2

**Alternative considered**: Keeping the placeholder `io.github.appimage_launcher` until owner confirmation. Rejected because the launcher's own source code already defines the final name.

## 2026-11-16: Qt Method Naming (N802 / ruff)

**Decision**: Allow Qt override methods (`rowCount`, `sizeHint`, `roleNames`, `closeEvent`) to retain their Qt-standard camelCase names rather than renaming to snake_case.

**Rationale**: These methods are part of the Qt public API and must match the exact signature expected by Qt's C++ meta-object system. Renaming them (e.g., `row_count`) would break the Qt signal/slot and model/view machinery because Qt looks for these specific method names via the meta-object compiler (moc) or Python's PyQt binding resolution.

**Files affected**:
- `src/aurelis_software/ui/app_model.py`: `rowCount`, `roleNames`
- `src/aurelis_software/ui/app_card_delegate.py`: `sizeHint`
- `src/aurelis_software/ui/screenshot_carousel.py`: `closeEvent`

**Suppression**: Each occurrence is marked with `# noqa: N802` inline rather than a broad per-file ignore, to keep the suppression minimal and auditable.

**Alternative considered**: Renaming methods and using Qt's `@pyqtSlot` / `@pyqtProperty` decorators with explicit names. Rejected because it adds boilerplate and doesn't work for virtual method overrides like `closeEvent` or `rowCount`.

**Review**: This decision should be revisited if a future version of PyQt6 provides a first-class way to register Python-style names for Qt virtual methods.

## Acceptance requires a run on real Aurelis

**Decision**: Phase 3 acceptance (and all subsequent phases) requires a run on real Aurelis, not only on the dev Arch machine.

**What the dev environment cannot prove:**
- The `appimage-launcher` daemon is not installed on the dev machine; the `real_daemon` marker tests (`-m real_daemon`) cannot run here.
- The dev machine is not immutable; `~/Applications` may not exist or may not be on the expected filesystem.
- `pkg` is not installed on the dev machine; Phase 6 cannot be fully validated here.
- KDE Plasma 6 / Dolphin integration (double-click MIME handler, service menu) cannot be tested without the real desktop.
- `appimage run <name>` is not available; the Open action cannot be exercised.
- xattr support on `~/Applications` is unverified on the dev machine.
- systemd user units and D-Bus activation via `.service` files behave differently on Aurelis.
- The `pkg` daemon socket (`aurelis-pkgd.sock`) is not present on the dev machine.

**Implication for the spec**: P3.10 must pass on real Aurelis, not only on the dev Arch. This note is added to the Phase 3 acceptance criteria in `docs/aurelis-software-gui-spec.md`.