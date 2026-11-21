# Phase 7 wizard implementation

Adds file detection, install and uninstall wizards, MIME integration, and settings UI for managing the "run without asking" list. The implementation supports AppImages, Flatpaks, and Pacman packages with distinct handling for system packages (refusal), user packages (removal), and unknown files (explanation). The install wizard routes AppImages already in the applications directory directly to execution without showing UI.

**Watch for:** Config access style mismatch (confirmed) — settings_dialog.py and install_wizard.py both read with `config.get("wizard.run_without_asking")` but write by mutating `data["wizard"]["run_without_asking"]`. This is a style inconsistency, not a functional bug — both patterns work.

**Verdict**: APPROVED

## High-level view

The detection cascade proceeds in the specified order: AppImage-in-applications-dir (suffix + parent check), X-AppImage-Managed desktop entry (suffix + content parse), Flatpak export (suffix + parent-in-list check), pacman-system (pacman -Qo + core JSON), pacman-user (pacman -Qo + user JSON), unknown. Each branch returns immediately on match or continues to the next. An AppImage outside applications_dir falls through all branches to unknown.

Config access style is split: both settings_dialog and install_wizard read with `config.get("wizard.run_without_asking")` (dotted key), but writes go through `data["wizard"]["run_without_asking"]` after cloning config.data to a mutable dict. Both patterns work with the current Config implementation.

The install wizard routes AppImages already in applications_dir to immediate execution via QProcess.startDetached before building any UI. The "run without asking" list stores `{app_id, sha256}` dicts and checks both fields before skipping the wizard on subsequent runs.

The uninstall wizard detects the file type and branches: system packages get a refusal page (Close only), unknown files get an explanation page (Close only), and removable applications (AppImage, Flatpak, pacman-user) get a two-page wizard (confirm, progress). AppImage removal calls backend.remove_async with trash action. Flatpak and pacman-user removals use QProcess to shell out to flatpak and pkg commands directly. The pacman-user success message includes a restart note.

Desktop files follow the expected structure. The install entry is a NoDisplay MIME handler for three types (AppImage, flatpakref, flatpak) that calls `aurelis-software wizard install %f`. The uninstall entry is a KDE service menu (Type=Service) that calls `aurelis-software wizard uninstall %f`.

Test coverage includes all six detection branches (AppImage-in-dir, desktop-AppImage, desktop-Flatpak, pacman-system, pacman-user, unknown) with isolated scenarios. Both wizards have offscreen UI tests that construct dialogs, verify widget presence, and simulate button clicks without rendering. detect.py has no Qt imports and no subprocess calls — all command execution is via the injected list_runner.

<details>
<summary>Issues (0)</summary>

No blocking issues identified. The config access style inconsistency (dotted keys for reads, dict mutation for writes) is a cleanup opportunity but both patterns work correctly.

</details>

<details>
<summary>Details</summary>

## Detection order trace

The spec requires detection in this order: AppImage in applications_dir, X-AppImage-Managed desktop entry, Flatpak export, pacman-system, pacman-user, unknown.

detect.py implements this with cascading checks. First: AppImage file in applications_dir. If `path.suffix == ".AppImage"` and `path.parent == applications_dir`, return appimage. Otherwise continue.

Second/third: desktop file checks. If `path.suffix == ".desktop"`, check for X-AppImage-Managed field (return appimage if present), then check if parent is in flatpak_export_dirs (return flatpak if present). An AppImage file (suffix `.AppImage`) never enters these branches.

Fourth/fifth: pacman checks. Run `pacman -Qo` on the path. If the output shows the file is owned by a package, check if that package appears in core-packages.json (return pacman-system) or user-packages.json (return pacman-user).

Sixth: if none of the above match, return unknown.

An AppImage not in applications_dir (e.g., `/home/user/Downloads/kate.AppImage`) fails the first check (parent mismatch), skips the desktop checks (suffix is `.AppImage`, not `.desktop`), likely fails the pacman checks (AppImage files are usually not owned by packages), and lands in unknown.

## InstallWizard routing and "run without asking"

Lines 32-38 in install_wizard.py check if the path is an AppImage in applications_dir. If so, call `QProcess.startDetached("appimage", ["run", path.stem])`, accept the dialog, and return before building any UI.

Lines 40-48 check if the file is in the "run without asking" list. Compute SHA256 of the file, fetch `wizard.run_without_asking` from config (a list of `{app_id, sha256}` dicts), and check for a matching entry. If found, call `_execute_file()` (which makes the AppImage executable and runs it, or opens other file types with the default handler), accept the dialog, and return.

Only if both checks fail does the wizard build its two-page UI (action selection, progress/result).

## UninstallWizard branching

Lines 52-59 in uninstall_wizard.py detect the application type using detect.py. Lines 62-67 call `_build_ui`, which branches based on detection.kind:

- `"pacman-system"` → `_build_refusal_page()` — single page with message and Close button (reject only)
- `"unknown"` → `_build_unknown_page()` — single page with explanation and Close button (reject only)
- Anything else → `_build_wizard_pages()` — two-page wizard (confirm, progress)

For AppImage removal, `_remove_appimage` calls `backend.remove_async(detection.id, {"file_action": "trash", "silent": True})`. For Flatpak, `_remove_flatpak` runs `QProcess` with `flatpak uninstall --user -y <app_id>`. For pacman-user, `_remove_pacman_user` runs `QProcess` with `pkg remove <package>` and displays a restart note on success.

## Desktop files and MIME integration

aurelis-software-wizard-install.desktop declares three MIME types: `application/vnd.appimage`, `application/vnd.flatpak.ref`, `application/vnd.flatpak`. It has `NoDisplay=true` to hide from application launchers and `Exec=aurelis-software wizard install %f` to receive the file path.

aurelis-software-uninstall.desktop is a KDE service menu (Type=Service) with `Actions=uninstall` and a corresponding `[Desktop Action uninstall]` section. Its Exec line is `aurelis-software wizard uninstall %f`.

test_desktop_files.py validates the install desktop file with desktop-file-validate. The uninstall service menu validation is skipped because service menus don't follow standard desktop entry spec.

## Test coverage

test_detect.py covers all six branches:
1. `test_appimage_in_applications_dir` — AppImage file in applications_dir → appimage
2. `test_desktop_entry_with_appimage_managed` — desktop file with X-AppImage-Managed=true → appimage
3. `test_desktop_entry_in_flatpak_exports` — desktop file in flatpak export dir → flatpak
4. `test_pacman_core_package` — file owned by core package → pacman-system
5. `test_pacman_user_package` — file owned by user package → pacman-user
6. `test_unknown_file` — file not matching any criteria → unknown

test_install_wizard.py has seven tests including routing (AppImage-in-folder auto-run), UI widget presence, install action (calls backend.install_async), just run action (executes file), "don't ask again" (saves to config), Flatpak handling, and startup time (< 500ms).

test_uninstall_wizard.py has five tests including system package refusal (no stack, single page), AppImage removal (calls backend.remove_async), Flatpak removal (QProcess), pacman-user removal (restart note), and unknown file explanation.

All tests construct wizards without showing them (offscreen testing). All backends are mocked. detect.py uses an injected list_runner, so no real subprocess calls occur during tests.

## File map

Changed files (per verification.txt):

- `src/aurelis_software/wizards/__init__.py` — exports DetectionResult and detect
- `src/aurelis_software/wizards/detect.py` — detection logic with six-branch cascade
- `src/aurelis_software/wizards/install_wizard.py` — InstallWizard QDialog with routing and "run without asking"
- `src/aurelis_software/wizards/uninstall_wizard.py` — UninstallWizard QDialog with refusal/explanation/removal branches
- `src/aurelis_software/__main__.py` — wizard install/uninstall subcommands
- `src/aurelis_software/ui/settings_dialog.py` — Wizards section with "run without asking" list widget
- `src/aurelis_software/resources/aurelis-software-wizard-install.desktop` — MIME handler
- `src/aurelis_software/resources/aurelis-software-uninstall.desktop` — KDE service menu
- `src/aurelis_software/core/config.py` — support for inline TOML tables (dicts in lists)
- `tests/wizards/test_detect.py` — six detection branch tests
- `tests/wizards/test_install_wizard.py` — seven install wizard tests
- `tests/wizards/test_uninstall_wizard.py` — five uninstall wizard tests
- `tests/wizards/test_desktop_files.py` — desktop file validation

</details>
