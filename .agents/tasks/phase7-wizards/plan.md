# Implementation Plan: Phase 7 — Wizards for Aurelis Software Center

## Overview

This plan implements installation and uninstallation wizards with file detection, PyQt6 dialogs, MIME integration, and comprehensive tests. All work follows the existing three-layer architecture and must pass `./check` (ruff + pytest).

**Workspace**: `/home/user/Projects/aurelis-software-center`

**Verification**: Run `./check` after each feature completes. All ruff checks and pytest tests must pass.

---

## Design Decisions

### Detection Logic (detect.py)

The detection order specified in the task is:

1. **AppImage in applications_dir**: Check if `path.parent == applications_dir` and `path.suffix == ".AppImage"`. Return `DetectionResult("appimage", path.stem, path.stem)`.

2. **Desktop entry with X-AppImage-Managed=true**: If `path.suffix == ".desktop"`, read the file, parse for `X-AppImage-Managed=true` key. Extract `Name` field and managed filename from desktop entry. Return `DetectionResult("appimage", managed_name, name)`.

3. **Desktop entry in Flatpak exports**: If `path.suffix == ".desktop"` and `path.parent` is in `flatpak_export_dirs`, parse desktop file for app ID (strip `.desktop` suffix from filename, e.g., `org.kde.kate.desktop` → `org.kde.kate`). Return `DetectionResult("flatpak", app_id, name_from_desktop)`.

4. **Pacman package in core-packages.json**: Run `list_runner(["pacman", "-Qo", str(path)])`, parse stdout for `is owned by <package>`. Load `core_packages_path` JSON file, check if package is in the list. Return `DetectionResult("pacman-system", package, package)`.

5. **Pacman package in user-packages.json**: Same as (4) but check `user_packages_path`. Return `DetectionResult("pacman-user", package, package)`.

6. **Unknown**: If none of the above match, return `DetectionResult("unknown", "", "")`.

**Rationale**: This ordering prioritizes managed AppImages (most common wizard use case), then desktop-based detection (Flatpak and AppImage), then filesystem ownership (Pacman), finally unknown fallback. All file I/O and subprocess calls are injected for testability (no `open()`, `Path.read_text()`, or `subprocess.run()` calls directly in detect.py).

### Wizard Architecture

**InstallWizard** and **UninstallWizard** are `QDialog` subclasses using `QStackedWidget` for multi-page flows. This matches the existing pattern in the codebase where settings and dialogs are standalone `QDialog` instances.

**InstallWizard routing**:
- On `__init__`, check if the AppImage is already in `applications_dir`. If yes, call `QProcess.startDetached("appimage", ["run", managed_name])` and set `accept()` to skip showing the dialog.
- Check "run without asking" list in config: compute SHA256 of file, check if `{"app_id": basename, "sha256": computed}` exists in `config["wizard"]["run_without_asking"]`. If match, execute file and skip UI.

**Page flow**:
- **InstallWizard Page 1**: Icon, name/version labels, "Install" button, "Just run" button with "Don't ask again" checkbox, "Cancel" button.
- **InstallWizard Page 2**: Status label, indeterminate progress bar, "Open" button (disabled until done), "Close" button.
- **UninstallWizard refusal page** (system packages): Single page with "Cannot remove system package" message and "Close" button only.
- **UninstallWizard Page 1** (confirm): Icon, name + type label, "Are you sure?" message, "Remove" button, "Cancel" button.
- **UninstallWizard Page 2**: Same as InstallWizard Page 2 (progress and result).

**Backend integration**:
- AppImage operations use `backend.install_async()` and `backend.remove_async()` with appropriate options.
- Flatpak operations use `QProcess` with `["flatpak", "install", "--user", path]` or `["flatpak", "uninstall", "--user", "-y", app_id]`.
- Pacman operations use `QProcess` with `["pkg", "remove", name]` and show "(applies after restart)" note.

**Rationale**: Reuses existing backend patterns (async for AppImage, QProcess for CLI tools). QStackedWidget allows smooth page transitions. Routing optimizations (already-installed check, run-without-asking) minimize friction for power users.

### CLI Integration (__main__.py)

The `wizard install <path>` and `wizard uninstall <path>` subcommands are lightweight entry points that:
- Build only the required backend(s) (AppImageBackend for install, all available backends for uninstall).
- Load `Paths` and `Config` from XDG defaults.
- Skip catalog loading and main window creation (performance requirement R23.1: < 500ms startup).
- Instantiate the wizard, call `exec()`, return 0 on accept, 2 on reject.

**Rationale**: Minimal initialization reduces startup time. Backends are built on-demand (e.g., uninstall needs all backends to detect and route correctly; install only needs AppImageBackend and optionally FlatpakBackend).

### Settings UI Integration

The "run without asking" list is shown in a new "Wizards" section in `settings_dialog.py`:
- `QListWidget` displays entries from `config["wizard"]["run_without_asking"]`.
- Each list item has a "Remove" button in a custom item widget.
- Clicking "Remove" pops the entry, calls `save(paths, updated_config)`, and refreshes the list.

**Rationale**: Matches existing settings pattern (checkboxes, spinboxes, line edits for config values). Users can audit and clear the "run without asking" list from one place.

### Desktop Files and MIME Integration

Two desktop files are created in `src/aurelis_software/resources/`:

1. **aurelis-software-wizard-install.desktop**:
   - `NoDisplay=true` (not shown in application menu).
   - `MimeType=application/vnd.appimage;application/vnd.flatpak.ref;application/vnd.flatpak;`
   - `Exec=aurelis-software wizard install %f`
   - Triggered when user opens `.AppImage`, `.flatpakref`, or `.flatpak` files.

2. **aurelis-software-uninstall.desktop**:
   - Dolphin service menu (right-click context menu in file manager).
   - `ServiceTypes=KonqPopupMenu/Plugin`
   - `MimeType=application/x-desktop;application/vnd.appimage;`
   - `Exec=aurelis-software wizard uninstall %f`
   - Triggered when user right-clicks on desktop files or AppImages.

Both files are validated with `desktop-file-validate` in a test (FEAT-003).

**Rationale**: Integrates wizards into the desktop environment. Users can double-click AppImage files or Flatpak references to trigger installation. Right-click uninstall provides discoverability for removal.

### Testing Strategy

Tests are organized in `tests/wizards/`:
- **test_detect.py**: Table-driven tests for all six detection branches. Uses `tmp_path` fixture for file setup and fake `list_runner` that returns canned `pacman -Qo` output.
- **test_install_wizard.py**: Offscreen UI tests using `qtbot` fixture. Tests routing, Page 1 UI, Install action, Just run, "Don't ask again", Flatpak handling, and startup time (< 500ms).
- **test_uninstall_wizard.py**: Offscreen UI tests for system package refusal, AppImage removal, Flatpak uninstall, Pacman with restart note, unknown file explanation.
- **test_desktop_files.py**: Runs `desktop-file-validate` on both desktop files.

All tests use:
- `qapp_session` fixture from `tests/conftest.py` (shared QApplication instance).
- `qtbot` fixture from `pytest-qt` for widget interaction.
- `tmp_path` fixture for temporary file setup.
- `unittest.mock` for mocking backend methods and QProcess.

**Rationale**: Follows existing test patterns in `tests/backends/` and `tests/ui/`. Offscreen Qt testing (via `QT_QPA_PLATFORM=offscreen` in `./check` script) allows headless CI runs. Mocking prevents side effects on developer's system.

---

## Implementation Plan

### FEAT-001: File Detection Logic

**Description**: Create wizards module with pure-Python file detection.

- [ ] 1. Create `src/aurelis_software/wizards/` directory and `src/aurelis_software/wizards/__init__.py`.
      Files: src/aurelis_software/wizards/__init__.py
      Verify: `python -c "from aurelis_software.wizards import detect, DetectionResult"` succeeds (after step 5).

- [ ] 2. Create `src/aurelis_software/wizards/detect.py` with `DetectionResult` dataclass.
      Define `DetectionResult(kind: str, id: str, name: str)` where `kind` is one of `{"appimage", "flatpak", "pacman-system", "pacman-user", "unknown"}`.
      Files: src/aurelis_software/wizards/detect.py
      Verify: `python -c "from aurelis_software.wizards.detect import DetectionResult; print(DetectionResult('appimage', 'kate', 'Kate'))"` prints the dataclass instance.

- [ ] 3. Implement `detect()` function in `detect.py`.
      Signature: `detect(path, *, applications_dir, flatpak_export_dirs, core_packages_path, user_packages_path, list_runner) -> DetectionResult`.
      Detection order: (1) AppImage in applications_dir by filename match, (2) desktop entry with X-AppImage-Managed=true, (3) desktop entry in Flatpak exports, (4) pacman -Qo returns package in core-packages.json, (5) pacman -Qo returns package in user-packages.json, (6) unknown.
      All file I/O via Path methods passed as arguments (no direct `open()` calls). All subprocess via `list_runner` parameter (signature: `Callable[[list[str]], tuple[int, str, str]]`). Parse desktop files with configparser or simple line-by-line parsing. Load JSON files with `json.load(open(...))` only when passed paths are provided.
      Files: src/aurelis_software/wizards/detect.py
      Verify: `ruff check src/aurelis_software/wizards/detect.py` passes with no violations.

- [ ] 4. Export `detect` and `DetectionResult` from `wizards/__init__.py`.
      Add `from .detect import DetectionResult, detect` and `__all__ = ["DetectionResult", "detect"]`.
      Files: src/aurelis_software/wizards/__init__.py
      Verify: `python -c "from aurelis_software.wizards import detect, DetectionResult"` succeeds.

- [ ] 5. Create `tests/wizards/` directory, `tests/wizards/__init__.py`, and `tests/wizards/test_detect.py`.
      Write table-driven tests covering all six branches: (1) AppImage in applications_dir, (2) desktop entry with X-AppImage-Managed, (3) desktop entry in Flatpak exports, (4) pacman -Qo returns core package, (5) pacman -Qo returns user package, (6) unknown file.
      Use `tmp_path` fixture for file setup. Create fake `list_runner` that returns canned `pacman -Qo` output for test cases 4-5. Each test asserts on `DetectionResult.kind`, `DetectionResult.id`, and `DetectionResult.name`.
      Files: tests/wizards/__init__.py, tests/wizards/test_detect.py
      Verify: `pytest tests/wizards/test_detect.py -v` passes with at least 6 tests.

---

### FEAT-002: InstallWizard and UninstallWizard Dialogs

**Description**: Create PyQt6 wizard dialogs with multi-page flows.

- [ ] 6. Create `src/aurelis_software/wizards/install_wizard.py` with `InstallWizard` class.
      `InstallWizard(path, backend, config, paths)` as `QDialog` subclass. Use `QStackedWidget` with two pages (Page 1: action selection, Page 2: progress/result). On `__init__`, implement routing: if AppImage in applications_dir, call `QProcess.startDetached("appimage", ["run", managed_name])`, set `accept()`, return without showing UI. Check "run without asking" list: compute SHA256 of path, check if entry exists in `config["wizard"]["run_without_asking"]`, if yes execute file and return.
      Files: src/aurelis_software/wizards/install_wizard.py
      Verify: `python -c "from aurelis_software.wizards.install_wizard import InstallWizard"` succeeds.

- [ ] 7. Implement InstallWizard Page 1 UI.
      QVBoxLayout with: QLabel for icon (set pixmap from `backend.inspect_async()` result if AppImage, else placeholder), QLabel for name/version, QLabel for relation wording ("not installed", "update available", etc.), QHBoxLayout with QPushButton "Install", QPushButton "Just run" + QCheckBox "Don't ask again", QPushButton "Cancel". Wire Cancel to `reject()`, Install to `_on_install()`, Just run to `_on_just_run()`.
      Files: src/aurelis_software/wizards/install_wizard.py
      Verify: `ruff check src/aurelis_software/wizards/install_wizard.py` passes.

- [ ] 8. Implement InstallWizard Page 2 UI and action handlers.
      Page 2: QVBoxLayout with QLabel status, QProgressBar (indeterminate), QHBoxLayout with QPushButton "Open" (disabled until done), QPushButton "Close" (wired to `accept()`). `_on_install()`: for AppImages, call `backend.install_async(path, {source_action: "copy", conflict: "replace", silent: True}, reply_cb, error_cb)` and switch to Page 2; for `.flatpakref`/`.flatpak`, run `QProcess(["flatpak", "install", "--user", path])`. `_on_just_run()`: call `QProcess.startDetached()` with appropriate command; if "Don't ask again" checked, append entry to `config["wizard"]["run_without_asking"]` and save.
      Files: src/aurelis_software/wizards/install_wizard.py
      Verify: `ruff check src/aurelis_software/wizards/install_wizard.py` passes.

- [ ] 9. Create `src/aurelis_software/wizards/uninstall_wizard.py` with `UninstallWizard` class.
      `UninstallWizard(path_or_desktop_id, backends, config, paths)` as `QDialog` subclass. On `__init__`, call `detect(path_or_desktop_id, ...)` to get `DetectionResult`. If `kind == "pacman-system"`, show single-page refusal ("Cannot remove system package") with Close button only. Otherwise, use `QStackedWidget` with two pages (Page 1: confirm, Page 2: progress/result).
      Files: src/aurelis_software/wizards/uninstall_wizard.py
      Verify: `python -c "from aurelis_software.wizards.uninstall_wizard import UninstallWizard"` succeeds.

- [ ] 10. Implement UninstallWizard Page 1 (confirm) and Page 2 (progress).
       Page 1: QVBoxLayout with QLabel icon, QLabel name + type label ("AppImage", "Flatpak", "User package"), QLabel "Are you sure you want to remove this application?", QHBoxLayout with QPushButton "Remove" (wired to `_on_remove()`), QPushButton "Cancel" (wired to `reject()`). Page 2: same layout as InstallWizard Page 2 (status, progress bar, Done button).
       Files: src/aurelis_software/wizards/uninstall_wizard.py
       Verify: `ruff check src/aurelis_software/wizards/uninstall_wizard.py` passes.

- [ ] 11. Implement UninstallWizard removal actions.
       `_on_remove()`: switch to Page 2, start progress bar. If `DetectionResult.kind == "appimage"`, call `backend.remove_async(name, {file_action: "trash", silent: True}, reply_cb, error_cb)`. If `"flatpak"`, run `QProcess(["flatpak", "uninstall", "--user", "-y", app_id])`. If `"pacman-user"`, run `QProcess(["pkg", "remove", name])` and append "(applies after restart)" to status label. If `"unknown"`, show explanation page with "This file is not managed by Aurelis Software Center" and Close button only (no Page 2).
       Files: src/aurelis_software/wizards/uninstall_wizard.py
       Verify: `ruff check src/aurelis_software/wizards/uninstall_wizard.py` passes.

- [ ] 12. Create `tests/wizards/test_install_wizard.py` with offscreen UI tests.
       Tests: `test_routing_appimage_in_folder` (verifies direct execution without UI), `test_page1_ui` (verifies Page 1 widgets), `test_install_action` (mocks backend.install_async, verifies call), `test_just_run` (mocks QProcess.startDetached), `test_dont_ask_again` (verifies config persistence), `test_flatpak_file` (verifies flatpak install command), `test_startup_time` (records time from __init__ to show, asserts < 500ms).
       Use `qapp_session` fixture, `qtbot` fixture, `tmp_path` for file setup, `unittest.mock` for mocking.
       Files: tests/wizards/test_install_wizard.py
       Verify: `pytest tests/wizards/test_install_wizard.py -v` passes with at least 7 tests.

- [ ] 13. Create `tests/wizards/test_uninstall_wizard.py` with offscreen UI tests.
       Tests: `test_system_package_refusal` (verifies refusal page), `test_appimage_removal` (mocks backend.remove_async), `test_flatpak_uninstall` (mocks QProcess, verifies command), `test_pacman_user_with_restart_note` (verifies restart note in status label), `test_unknown_file` (verifies explanation page).
       Files: tests/wizards/test_uninstall_wizard.py
       Verify: `pytest tests/wizards/test_uninstall_wizard.py -v` passes with at least 5 tests.

---

### FEAT-003: CLI Integration and Settings UI

**Description**: Wire wizards into __main__.py and settings_dialog.py, create desktop files.

- [ ] 14. Modify `src/aurelis_software/__main__.py` to handle `wizard install <path>` subcommand.
       Parse `argv[0] == "wizard"` and `argv[1] == "install"`, extract `path = argv[2]`. Build `AppImageBackend(DbusClient(QDBusConnection.sessionBus()))`, load `Paths.xdg()` and `config = load(paths)`. Instantiate `InstallWizard(path, backend, config, paths)`, call `wizard.exec()`, return 0 if `wizard.result() == QDialog.Accepted` else 2. Skip catalog loading and main window creation.
       Files: src/aurelis_software/__main__.py
       Verify: `python -m aurelis_software wizard install /tmp/test.AppImage` runs without error (may show wizard or route directly depending on file state).

- [ ] 15. Modify `src/aurelis_software/__main__.py` to handle `wizard uninstall <path>` subcommand.
       Parse `argv[1] == "uninstall"`, extract `path = argv[2]`. Build backends dict: `{"appimage": AppImageBackend(...), "flatpak": FlatpakBackend(...) if flatpak available, "pacman": PacmanBackend(...) if pkg available}`. Load `Paths` and `Config`. Instantiate `UninstallWizard(path, backends, config, paths)`, call `wizard.exec()`, return 0 if accepted else 2.
       Files: src/aurelis_software/__main__.py
       Verify: `python -m aurelis_software wizard uninstall /tmp/test.AppImage` runs without error.

- [ ] 16. Modify `src/aurelis_software/ui/settings_dialog.py` to add "Wizards" section.
       Add new `QGroupBox("Wizards")` after existing groups. Add `QLabel("Run without asking:")` and `QListWidget` showing entries from `config.get("wizard.run_without_asking", [])`. Each list item displays `app_id` (filename) and has a `QPushButton("Remove")` in a custom item widget (using `QListWidget.setItemWidget()`). Wire Remove button to pop entry from config list, call `save(paths, updated_config)`, and refresh `QListWidget`.
       Files: src/aurelis_software/ui/settings_dialog.py
       Verify: `ruff check src/aurelis_software/ui/settings_dialog.py` passes. Manual UI test: open Settings, verify Wizards section appears (or add unit test to verify widget creation).

- [ ] 17. Create `src/aurelis_software/resources/` directory if it does not exist.
       Files: src/aurelis_software/resources/ (directory)
       Verify: `ls -ld src/aurelis_software/resources/` shows directory exists.

- [ ] 18. Create `src/aurelis_software/resources/aurelis-software-wizard-install.desktop`.
       Content: `[Desktop Entry]\nType=Application\nNoDisplay=true\nName=Aurelis Software Install Wizard\nExec=aurelis-software wizard install %f\nMimeType=application/vnd.appimage;application/vnd.flatpak.ref;application/vnd.flatpak;\nIcon=system-software-install`.
       Files: src/aurelis_software/resources/aurelis-software-wizard-install.desktop
       Verify: `desktop-file-validate src/aurelis_software/resources/aurelis-software-wizard-install.desktop` exits 0 (via test in step 20).

- [ ] 19. Create `src/aurelis_software/resources/aurelis-software-uninstall.desktop`.
       Content: `[Desktop Entry]\nType=Service\nServiceTypes=KonqPopupMenu/Plugin\nMimeType=application/x-desktop;application/vnd.appimage;\nActions=uninstall;\n\n[Desktop Action uninstall]\nName=Uninstall with Aurelis Software\nIcon=edit-delete\nExec=aurelis-software wizard uninstall %f`.
       Files: src/aurelis_software/resources/aurelis-software-uninstall.desktop
       Verify: `desktop-file-validate src/aurelis_software/resources/aurelis-software-uninstall.desktop` exits 0 (via test in step 20).

- [ ] 20. Create `tests/wizards/test_desktop_files.py` with desktop-file-validate test.
       Test: `test_validate_install_desktop` runs `subprocess.run(["desktop-file-validate", "src/aurelis_software/resources/aurelis-software-wizard-install.desktop"], check=False)` and asserts `returncode == 0`. Test: `test_validate_uninstall_desktop` does the same for uninstall desktop file.
       Files: tests/wizards/test_desktop_files.py
       Verify: `pytest tests/wizards/test_desktop_files.py -v` passes with 2 tests.

---

### FEAT-004: Comprehensive Tests and Performance

**Description**: Full test coverage for wizard UI and startup time.

All tests in this feature use:
- `qapp_session` fixture from `tests/conftest.py`.
- `qtbot` fixture from `pytest-qt`.
- `tmp_path` fixture for file setup.
- `unittest.mock.patch` or `unittest.mock.Mock` for mocking backend methods and `QProcess`.

Tests are already listed in steps 12-13 above (FEAT-002). This feature adds additional edge cases and the startup time test.

- [ ] 21. Run full test suite for wizards and verify all tests pass.
       Run `pytest tests/wizards/ -v`. Verify at least 20 tests pass (6 detection, 7 install wizard, 5 uninstall wizard, 2 desktop file validation).
       Verify: `pytest tests/wizards/ -v` shows all tests passed.

- [ ] 22. Run `./check` to confirm ruff and pytest pass for the entire project.
       Run `./check` from workspace root. Verify 0 ruff violations and 0 pytest failures.
       Verify: `./check` output ends with "==> check passed".

---

## Summary

This plan creates:
- **wizards module** with detection logic (detect.py)
- **InstallWizard and UninstallWizard** PyQt6 dialogs
- **CLI integration** in __main__.py
- **Settings UI** for "run without asking" list
- **Desktop files** for MIME and service menu integration
- **Comprehensive tests** covering all branches and UI flows

All work follows existing patterns:
- Injected dependencies (paths, config, backend, runner) for testability.
- QStackedWidget for multi-page dialogs.
- QProcess for CLI tool execution.
- pytest-qt for offscreen UI testing.
- Module-level command constants (never shell strings).

Verification after each feature: run `pytest tests/wizards/ -v` and `ruff check src/aurelis_software/wizards tests/wizards`.

Final verification: run `./check` from workspace root to confirm zero failures.
