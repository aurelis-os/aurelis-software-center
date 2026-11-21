# Implementation Plan: Aurelis Software Center — Phase 4 through Phase 8

## Overview

This plan completes the Aurelis Software Center PyQt6 application across five phases. Each phase ends with `./check` (ruff + pytest) passing and a stop for owner review before the next phase begins. All work is in Python using the existing three-layer architecture (`core` → `services`/`backends` → `ui`/`wizards`).

**Execution rule**: complete one numbered top-level task group (one phase) in full, run `./check`, paste the real output, and stop. Do not start the next phase until the owner approves.

---

## Tasks

- [x] 1. Phase 4 — Fix two failing tests and complete AppImage updates
  - [x] 1.1 Fix `_call_update_install.on_error`: pop `op_id` from `_active_operations` **before** calling `_recompute_updates()`
    - Locate `on_error` inside `_call_update_install` in `src/aurelis_software/ui/main_window.py`
    - Swap the order: `_active_operations.pop(op_id, None)` then `_recompute_updates()`
    - Verify `test_update_failure_daemon_death` passes after the fix
    - _Requirements: R1.1_

  - [x] 1.2 Fix `_button_config_for_state`: return `{"text": "Updating…", "enabled": False}` for the `"Updating"` state
    - Find `_button_config_for_state` (or its equivalent) in `src/aurelis_software/ui/main_window.py` or `detail_page.py`
    - Ensure the `"Updating"` branch sets `enabled=False`
    - Verify `test_update_busy_state_disables_button` passes after the fix
    - _Requirements: R1.2_

  - [x] 1.3 Fix `_start_update.on_finished`: emit `progress(step="handoff")` before the D-Bus `Install` call
    - Locate `on_finished` inside `_start_update` in `src/aurelis_software/ui/main_window.py`
    - Add `operation.event.emit(Progress(op_id=op_id, step="handoff", fraction=None, message=self.tr("Finishing…")))` before the `Install` D-Bus call
    - _Requirements: R1.3_

  - [ ]* 1.4 Add regression tests for the three fixes
    - Confirm `test_update_failure_daemon_death` and `test_update_busy_state_disables_button` now pass in `tests/ui/test_p43_update.py`
    - Add one focused unit test per fix to guard against regression
    - _Requirements: R1.1, R1.2, R1.3_

  - [x] 1.5 Implement update availability computation and badge wiring
    - After catalog refresh (`_on_catalog_loaded`) and after `list_installed` completes, call `_recompute_updates()` which applies `core/versions.py` rules across all installed AppImages
    - Wire the result count to `sidebar._updates_count`
    - Respect policies: `auto` and `manual` appear; `pinned` never; `self_managed` only when `updates.include_self_managed` is `True`
    - _Requirements: R2.1, R2.2_

  - [x] 1.6 Implement zsync delta update with fallback in `services/zsync.py`
    - `fetch_update(entry, installed_path, cache_dir, runner)` tries zsync when `entry.raw.get("zsync_url")` is set and `zsync` is on PATH, writing to `<cache_dir>/<id>-<version>.AppImage.part`
    - Falls back to `Downloader` when zsync is unavailable or its URL is absent
    - Verifies `sha256` after fetch when present; raises `ChecksumMismatch` and deletes `.part` on mismatch
    - _Requirements: R3.1, R3.2, R3.3_

  - [ ]* 1.7 Write property test for `fetch_update` fallback (Property 2)
    - **Property 2: zsync fallback** — for any entry, `fetch_update` returns a `.part` file regardless of zsync availability, as long as the download URL is reachable
    - **Validates: R3.1, R3.2**

  - [x] 1.8 Implement update flow in `main_window.py` (`_start_update`)
    - `_start_update(entry, installed)`: calls `fetch_update`, then `Install(newfile, {source_action:"move", conflict:"replace", silent:true, origin:build_origin(entry)})`
    - On success: emit toast with **Undo** button that calls `Revert(managed_name)`; show Undo only while `installed.previous` is non-empty; after Undo recompute badge
    - On failure at any stage: delete `.part` file, set detail page state to `"Failed"`, show Retry button, leave badge unchanged
    - _Requirements: R4.1, R4.2, R4.3, R4.4_

  - [ ]* 1.9 Write property test for origin correctness after update (Property 3)
    - **Property 3: Origin version after update** — `build_origin(entry).version == entry.version` and `build_origin(entry).sha256 == entry.sha256` for all entries
    - **Validates: R4.1, R2.3**

  - [x] 1.10 Create `ui/updates_page.py`
    - `UpdatesPage(QWidget)` with `populate(updates, installed)`, `set_progress(app_key, event)`, `set_result(app_key, success, message)`
    - Rows grouped by source; each row: checkbox, icon, name, version arrow, source badge, inline progress bar (hidden until running), **Update** button
    - **Update all** at top: runs only `auto`-policy rows in FIFO order through the operation queue
    - Summary dialog on completion listing per-app success/failure/skipped
    - Pacman rows include "(applies after restart)" note
    - Wire `updates_requested` signal from sidebar to show this page; wire `update_requested(app_key)` to `_on_update_requested`
    - _Requirements: R5.1, R5.2, R5.3, R5.4_

  - [x] 1.11 Add policy selector to `detail_page.py`
    - Add a `QComboBox` (Automatic / Ask me / Pinned) below the action buttons; visible only for installed AppImages
    - On change, call `backend.set_policy(installed.managed_name, policy)`; recompute updates
    - "Include self-updating apps" setting in `settings_dialog.py` wires to `updates.include_self_managed`; on change triggers `_recompute_updates()`
    - _Requirements: R6.1, R6.2_

  - [x] 1.12 Implement update notifications
    - After each `_recompute_updates()`, if the new count exceeds the previous count and `config["updates"]["notify"]` is `True` (default `False`), send a notification via `QDBusMessage` to `org.freedesktop.Notifications`
    - Exclude `manual`, `pinned`, and `self_managed` apps from the notification count
    - Add "Notify about updates" checkbox to `settings_dialog.py`
    - _Requirements: R7.1_

  - [ ]* 1.13 Write tests for Phase 4 UI (`tests/ui/test_p44_updates_page.py`, `tests/ui/test_p45_policy.py`)
    - `test_p44_updates_page.py`: populate with mixed-source updates; Update all skips `manual`; summary dialog shows; Pacman rows display restart note; inline progress shown during operation
    - `test_p45_policy.py`: policy selector visible for installed AppImage; calls `SetPolicy` with correct value; recompute triggered on setting change; `self_managed` excluded/included based on setting
    - _Requirements: R5.1–R5.4, R6.1, R6.2_

  - [x] 1.14 Phase 4 checkpoint — run `./check` and confirm all tests pass
    - Run `./check` (ruff + pytest); paste the real output
    - Verify 0 failures; list any skipped tests
    - **Stop here for owner review before starting Phase 5**

- [ ] 2. Phase 5 — Flathub section

  - [x] 2.1 Create `core/pacman_parser.py` — no, create `services/flathub_index.py`
    - `FlathubIndex(db_path, appstream_path, locale)` backed by `sqlite3`
    - SQLite schema: `apps` table (id, name, summary, version, icon_name, categories JSON, raw JSON) + `apps_fts` FTS5 virtual table (id UNINDEXED, name, summary, keywords)
    - `needs_rebuild()` compares stored appstream mtime with current file mtime
    - `rebuild(progress_cb)` parses gzip-compressed AppStream XML using `xml.etree.ElementTree`; inserts in batches; calls `progress_cb(fraction)` every 500 entries
    - `search(query, limit, offset)` queries FTS5; returns list of dicts
    - `get(app_id)` returns single dict or `None`
    - Prefer `xml:lang` elements matching `locale`; fall back to untagged
    - _Requirements: R8.1, R8.2, R8.3, R8.4_

  - [ ]* 2.2 Write tests for `FlathubIndex` (`tests/services/test_flathub_index.py`)
    - Use fixture `tests/fixtures/flathub_appstream.xml` (small real XML with 10–20 entries)
    - Test: needs_rebuild True when file is newer; rebuild populates FTS; search returns ranked results; locale fallback; rebuild is idempotent (runs twice, same result); no entries loaded into RAM beyond the page
    - _Requirements: R8.1, R8.3, R8.4_

  - [x] 2.3 Create `backends/flatpak.py`
    - `FlatpakBackend(runner)` implementing `Backend` for `Source.FLATPAK`
    - Define command lists as module-level constants (no shell strings)
    - `available` property: check `flatpak` on PATH; False if missing
    - `list_installed()`: parse tab-separated output of `LIST_INSTALLED_CMD`
    - `list_updates()`: parse output of `LIST_UPDATES_CMD`
    - `install(app)`, `remove(installed)`, `update(app, installed)`: emit `Started`/`Progress`/`Finished`/`Failed` via `Operation` with indeterminate progress bar
    - `add_remote()`: run `ADD_REMOTE_CMD`
    - `refresh_appstream()`: run `REFRESH_APPSTREAM`
    - _Requirements: R10.1–R10.7_

  - [ ]* 2.4 Write property test for Flatpak command construction (Property 4)
    - **Property 4: Flatpak command construction** — for any valid app id, every command list contains no shell metacharacters introduced by the id
    - **Validates: R10.1–R10.6**

  - [ ]* 2.5 Write backend tests for `FlatpakBackend` (`tests/backends/test_flatpak.py`)
    - Use captured CLI output fixtures in `tests/fixtures/flatpak/`
    - Test: `list_installed` parses correctly; `list_updates` returns `UpdateInfo` objects; `install` emits correct events; `remove` emits correct events; `available=False` when flatpak missing; "Add Flathub" command issued correctly
    - _Requirements: R10.1–R10.7, R12.1_

  - [x] 2.6 Add paginated `FlathubModel` to `ui/app_model.py`
    - `FlathubModel(QAbstractListModel)` with `canFetchMore(parent)`/`fetchMore(parent)` using `FlathubIndex.search(query, limit=48, offset=len(self._rows))`
    - Expose same roles as the existing `AppModel` so `AppCardDelegate` renders without changes
    - Connect to the existing search bar via the same proxy interface
    - _Requirements: R9.1, R9.2_

  - [x] 2.7 Wire Flathub into the sidebar, Installed page, and Updates page
    - Add Flathub sidebar section and category sub-list; show "Flathub not available" empty state when `available=False`
    - `_refresh_installed()` aggregates Flatpak results alongside AppImage results
    - `_recompute_updates()` includes Flatpak update entries
    - "Also available as" on AppImage detail pages: query `FlathubIndex.get(entry.id)`; if found, show a "Also on Flathub" button
    - Show "Add Flathub" inline action if no Flathub remote; show "Refresh Flathub metadata" action in section header
    - _Requirements: R9.3, R12.1, R12.2, R12.3_

  - [x] 2.8 Wire `FlathubIndex` rebuild to a worker on startup and on metadata refresh
    - On startup: if `FlathubIndex.needs_rebuild()` is True, start a `QThreadPool` worker that calls `rebuild(progress_cb)`; show indeterminate progress banner in Flathub section until done
    - "Refresh Flathub metadata" action: run `flatpak update --appstream --user` via `QProcess`; on finish call `rebuild()` in worker
    - _Requirements: R8.2, R8.5, R12.2_

  - [ ]* 2.9 Write Phase 5 UI tests
    - Confirm Flathub section renders with fixture data; search returns results; detail page reuses `DetailPage`; "Add Flathub" action triggers correct command; section shows graceful empty state when `flatpak` missing
    - _Requirements: R9.1–R9.4, R11.1, R12.1–R12.3_

  - [x] 2.10 Phase 5 checkpoint — run `./check` and confirm all tests pass
    - Run `./check`; paste real output
    - **Stop here for owner review before starting Phase 6**

- [x] 3. Phase 6 — Pacman section

  - [x] 3.1 Create `core/pacman_parser.py`
    - `parse_si_output(text) -> list[dict]`: parses multi-line `pacman -Si` output; handles multi-value fields (`Depends On`, `Required By`, `Groups`, etc.) as lists
    - `parse_qi_output(text) -> list[dict]`: parses `pacman -Qi` output for installed packages
    - `parse_qq_output(text) -> list[str]`: parses `pacman -Qq` output (one name per line)
    - Pure Python, no Qt, no subprocess
    - _Requirements: R13.2_

  - [x]* 3.2 Write property test for pacman parser (Property 5)
    - **Property 5: Pacman parser round-trip** — for any `pacman -Si` output, `parse_si_output` produces dicts whose `name` and `version` fields match the "Name" and "Version" lines exactly
    - **Validates: R13.1, R13.2**

  - [x] 3.3 Create `services/pacman_index.py`
    - `PacmanIndex(db_path, sync_dir)` backed by `sqlite3`
    - SQLite schema: `packages` table (name, version, description, repo, groups JSON, installed_size, download_size, url, license, depends JSON, raw JSON) + `packages_fts` FTS5 on name + description
    - `needs_rebuild()`: compares max mtime of `sync_dir/*.db` with stored value
    - `rebuild(runner, progress_cb)`: runs `pacman -Si` via `runner`; parses with `pacman_parser`; inserts in batches
    - `search(query, limit, offset)`: FTS5 query
    - `get(name)`: single record or `None`
    - _Requirements: R13.1, R13.2, R13.3_

  - [x]* 3.4 Write tests for `PacmanIndex` (`tests/services/test_pacman_index.py`)
    - Use captured fixture `tests/fixtures/pacman/si_output.txt`
    - Test: needs_rebuild when sync db is newer; rebuild populates FTS; search returns correct results; rebuild is idempotent; worker thread does not block main thread
    - _Requirements: R13.1, R13.3_

  - [x] 3.5 Create `backends/pacman.py`
    - `PacmanBackend(runner, core_packages_path, user_packages_path)` implementing `Backend` for `Source.PACMAN`
    - `list_installed()`: runs `pacman -Qq` then `pacman -Qi <name>` for details; classifies as locked/user/dependency using the two JSON files
    - `install(app)`: runs `pkg add <name>`; on success calls `pkg queue` to refresh pending set; emits events
    - `remove(installed)`: check reverse deps via `pacman -Qi` "Required By"; if any user package depends on it, emit a warning payload in `Failed` event with `code="ConflictPending"` before the UI shows a confirmation; on user confirm, run `pkg remove <name>`
    - `list_updates()`: reads `pkg queue` JSON for pending installs where a newer version is available
    - `available` property: checks `pkg` on PATH
    - _Requirements: R15.1–R15.6_

  - [x]* 3.6 Write tests for `PacmanBackend` (`tests/backends/test_pacman.py`)
    - Use captured fixture outputs in `tests/fixtures/pacman/`
    - Test: `list_installed` classifies packages correctly; `install` calls `pkg add` and refreshes queue; `remove` warns on reverse deps; `available=False` when pkg missing; pending state persisted via `pkg queue` not GUI file
    - _Requirements: R15.1–R15.6, R18.1_

  - [x] 3.7 Wire Pacman into sidebar, Installed page, Updates page, and banners
    - Add Pacman sidebar section with category sub-list (using `PacmanIndex`)
    - Installed page: aggregate Pacman rows; show lock icon for locked packages; "Show dependencies" toggle; "Pending restart" tag
    - Updates page: Pacman update rows with "(applies after restart)" note
    - After `pkg add`/`pkg remove` success: show `PendingRebootBanner` in `banners.py`
    - On startup: query `pkg queue` to restore pending state; show banner if non-empty
    - _Requirements: R14.1–R14.3, R16.1–R16.3, R17.1_

  - [x] 3.8 Add pacman-specific UI: reverse-dependency warning and package detail
    - When `PacmanBackend.remove` signals a dependency conflict, show a `QMessageBox` warning listing the dependent packages before proceeding
    - Lazy detail via `PacmanIndex.get(name)` on detail page click
    - Paginated `PacmanModel` mirroring `FlathubModel` backed by `PacmanIndex.search`
    - _Requirements: R15.4, R14.3_

  - [x]* 3.9 Write failure tests for Pacman (`tests/backends/test_pacman.py` extension)
    - Package not found (exit 1): correct error message, no state change
    - Locked package removal: Remove action disabled in UI; direct `pkg remove` call rejected
    - `pkg` missing: section degrades with banner
    - Reverse-dep warning shown and dismissed correctly
    - _Requirements: R18.1_

  - [x] 3.10 Phase 6 checkpoint — run `./check` and confirm all tests pass
    - Run `./check`; paste real output
    - **Stop here for owner review before starting Phase 7**

- [x] 4. Phase 7 — Wizards

  - [x] 4.1 Create `wizards/__init__.py` and `wizards/detect.py`
    - `detect(path, *, applications_dir, flatpak_export_dirs, core_packages_path, user_packages_path, list_runner) -> DetectionResult`
    - `DetectionResult(kind, id, name)` where kind ∈ `{"appimage", "flatpak", "pacman-system", "pacman-user", "unknown"}`
    - Detection order per R19.2; all file I/O injected via `list_runner` and `Path` arguments
    - No Qt, no subprocess side effects
    - _Requirements: R19.1, R19.2_

  - [x]* 4.2 Write property test for detection determinism (Property 6)
    - **Property 6: Detection determinism** — `detect(path, ...)` with same inputs always returns the same `DetectionResult`
    - **Validates: R19.1, R19.2**

  - [x]* 4.3 Write table-driven tests for every detection branch (`tests/wizards/test_detect.py`)
    - AppImage in applications_dir → appimage
    - Desktop entry with `X-AppImage-Managed=true` → appimage
    - Desktop entry in Flatpak exports → flatpak
    - `pacman -Qo` returns package in core-packages.json → pacman-system
    - `pacman -Qo` returns package in user-packages.json → pacman-user
    - Unknown file → unknown
    - All six branches must have an assertion that fails without the feature
    - _Requirements: R19.2, R19.3_

  - [x] 4.4 Create `wizards/install_wizard.py`
    - `InstallWizard(path, backend, config, paths)` as a `QDialog`
    - Routing: if the AppImage is already in `applications_dir`, call `QProcess.startDetached("appimage", ["run", managed_name])` and return immediately with no UI
    - Page 1: name, icon, version, relation wording; **Install**, **Just run** + "Don't ask again" checkbox, **Cancel**
    - Page 2 (slide-in via `QStackedWidget`): spinner + status; on completion shows result with **Open** / **Close**
    - For AppImages: `Install(path, {source_action:"copy", conflict:"replace", silent:true})`
    - For `.flatpakref`/`.flatpak`: `flatpak install --user <file>`
    - "Don't ask again": stores `{"app_id": ..., "sha256": ...}` in `config["wizard"]["run_without_asking"]`
    - _Requirements: R20.1–R20.5_

  - [x] 4.5 Wire "run without asking" list into `settings_dialog.py`
    - Add a list widget in Settings showing entries in `wizard.run_without_asking`; each row has a **Remove** button that pops the entry from config and saves
    - _Requirements: R20.6_

  - [x] 4.6 Create `wizards/uninstall_wizard.py`
    - `UninstallWizard(path_or_desktop_id, backends, config, paths)` as a `QDialog`
    - Calls `detect()` on startup
    - System package → single page refusal with **Close** only
    - Others → Page 1 (confirm: name, icon, type label, message) + Page 2 (progress, then Done)
    - Page 2 calls: AppImage `Remove(name, {file_action:"trash", silent:true})`; Flatpak `flatpak uninstall --user -y <id>`; Pacman `pkg remove <name>` with restart note
    - _Requirements: R21.1–R21.4_

  - [x] 4.7 Wire wizard entry points into `__main__.py`
    - Parse `wizard install <path>` and `wizard uninstall <path>` subcommands
    - Build only the required backend(s), skip catalog loading and main window
    - _Requirements: R20.1, R21.1, R23.1_

  - [x] 4.8 Create MIME and desktop integration files
    - `resources/aurelis-software-wizard-install.desktop`: `NoDisplay=true`, `MimeType=application/vnd.appimage;application/vnd.flatpak.ref;application/vnd.flatpak;`, `Exec=aurelis-software wizard install %f`
    - `resources/aurelis-software-uninstall.desktop`: Dolphin service menu, `Exec=aurelis-software wizard uninstall %f`
    - Run `desktop-file-validate` on both in a test
    - _Requirements: R22.1, R22.2, R22.3_

  - [x] 4.9 Measure wizard startup time and add a timing test
    - In `tests/wizards/test_install_wizard.py`, record wall-clock time from `InstallWizard.__init__` to first page visible; assert < 500 ms
    - _Requirements: R23.1_

  - [x]* 4.10 Write offscreen UI tests for all wizard pages (`tests/wizards/test_install_wizard.py`, `tests/wizards/test_uninstall_wizard.py`)
    - Install wizard: routing (in-folder AppImage runs directly); Page 1 shows relation wording; Install triggers correct D-Bus call; Just run executes file; "Don't ask again" stores entry; Flatpak file path triggers flatpak command
    - Uninstall wizard: system package → refusal page only; AppImage → Remove with trash; Flatpak → flatpak uninstall; Pacman user → pkg remove with restart note; unknown → explanation page
    - _Requirements: R24.1_

  - [x] 4.11 Phase 7 checkpoint — run `./check` and confirm all tests pass
    - Run `./check`; paste real output
    - **Stop here for owner review before starting Phase 8**

- [ ] 5. Phase 8 — Polish and release

  - [ ] 5.1 Polish the Explore page
    - Add or refactor `ui/explore_page.py` (or update `main_window.py`'s explore layout)
    - Layout: (1) "Recently updated" horizontal scroll row — top 6 by `version_changed_at`; (2) per-category horizontal scroll rows (only categories with ≥ 1 app); (3) "All apps" full grid
    - Category rows reuse `AppCardDelegate`; icons lazy-loaded
    - _Requirements: R25.1_

  - [ ] 5.2 Add Greek translation
    - Run `pylupdate6 src/aurelis_software/ -ts src/aurelis_software/resources/i18n/el.ts`
    - Translate all strings in `el.ts` to Greek
    - Compile: `lrelease src/aurelis_software/resources/i18n/el.ts -qm src/aurelis_software/resources/i18n/el.qm`
    - In `app.py`, load `QTranslator` for the configured `ui.language`; language selector in Settings triggers reload
    - _Requirements: R26.1, R26.2_

  - [ ]* 5.3 Write a layout stress test for Greek strings
    - For each dialog and page, instantiate offscreen with the Greek `QTranslator` active; assert no widget is clipped (width > 0, text not truncated by `elideMode`)
    - _Requirements: R26.2_

  - [ ] 5.4 Accessibility pass
    - Add `setAccessibleName(...)` to every button, label carrying semantic meaning, badge, and progress bar in `ui/` and `wizards/` that does not already have one
    - Verify Tab order traverses interactive elements without skipping in main window, detail page, updates page, settings dialog, install wizard, uninstall wizard
    - In `theme.py`, add `assert_badge_contrast()` that checks all badge foreground/background pairs against WCAG AA (4.5:1 ratio); call it from a test
    - _Requirements: R27.1, R27.2, R27.3, R27.4_

  - [ ] 5.5 Performance pass
    - Add `tests/test_performance.py` with timed assertions for each budget:
      - Catalog parse 500 synthetic apps < 100 ms
      - Search keystroke on 500 apps < 50 ms
      - FTS search (Flathub/pacman fixture) < 100 ms
    - Run the full app against the fixture on the owner's machine and record results in `README.md`
    - _Requirements: R28.1_

  - [ ] 5.6 Write `packaging/PKGBUILD`
    - Set `pkgname=aurelis-software`, `depends=(python python-pyqt6 appimage-launcher)`, `makedepends=(python-build python-installer)`
    - Install `.desktop` files from `resources/` and icon
    - Add a CI step (or Makefile target) that runs `makepkg --nobuild` to validate PKGBUILD syntax
    - _Requirements: R29.1_

  - [ ]* 5.7 Write a PKGBUILD validation test
    - In `tests/` add a test that runs `desktop-file-validate` on all installed `.desktop` files and checks PKGBUILD `pkgver` matches `src/aurelis_software/__init__.py` `__version__`
    - _Requirements: R29.1, R29.2_

  - [ ] 5.8 Release checklist tasks (coding-agent scope only)
    - Bump `__version__` in `src/aurelis_software/__init__.py` and `packaging/PKGBUILD` to match
    - Add a `CHANGELOG.md` entry for the release with phase summary
    - Confirm `./check` passes with zero failures and zero ruff warnings
    - _Requirements: R29.2_

  - [ ] 5.9 Phase 8 final checkpoint — run `./check` and confirm all tests pass
    - Run `./check`; paste real output
    - List every performance budget result measured
    - List any items deferred to a future release
    - **Stop here for owner final review**

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP, but must still be in the dependency graph
- Each task references specific requirements for traceability
- Checkpoints (1.14, 2.10, 3.10, 4.11, 5.9) enforce the "one phase at a time, stop for owner review" rule
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and error paths
- `./check` = `ruff check src/ tests/` + `pytest`; must pass with zero failures before each commit and before each checkpoint

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "1.5"] },
    { "id": 2, "tasks": ["1.6"] },
    { "id": 3, "tasks": ["1.7", "1.8"] },
    { "id": 4, "tasks": ["1.9", "1.10", "1.11"] },
    { "id": 5, "tasks": ["1.12", "1.13"] },
    { "id": 6, "tasks": ["1.14"] },
    { "id": 7, "tasks": ["2.1"] },
    { "id": 8, "tasks": ["2.2", "2.3"] },
    { "id": 9, "tasks": ["2.4", "2.5", "2.6"] },
    { "id": 10, "tasks": ["2.7", "2.8"] },
    { "id": 11, "tasks": ["2.9"] },
    { "id": 12, "tasks": ["2.10"] },
    { "id": 13, "tasks": ["3.1"] },
    { "id": 14, "tasks": ["3.2", "3.3"] },
    { "id": 15, "tasks": ["3.4", "3.5"] },
    { "id": 16, "tasks": ["3.6", "3.7"] },
    { "id": 17, "tasks": ["3.8", "3.9"] },
    { "id": 18, "tasks": ["3.10"] },
    { "id": 19, "tasks": ["4.1"] },
    { "id": 20, "tasks": ["4.2", "4.3"] },
    { "id": 21, "tasks": ["4.4"] },
    { "id": 22, "tasks": ["4.5", "4.6"] },
    { "id": 23, "tasks": ["4.7", "4.8"] },
    { "id": 24, "tasks": ["4.9", "4.10"] },
    { "id": 25, "tasks": ["4.11"] },
    { "id": 26, "tasks": ["5.1", "5.2", "5.4", "5.5"] },
    { "id": 27, "tasks": ["5.3", "5.6"] },
    { "id": 28, "tasks": ["5.7", "5.8"] },
    { "id": 29, "tasks": ["5.9"] }
  ]
}
```
