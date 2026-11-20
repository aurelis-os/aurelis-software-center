# Requirements Document

## Introduction

This document specifies requirements for completing Phases 4 through 8 of the Aurelis Software Center — a GNOME-Software-style PyQt6 application center for Aurelis (immutable Arch Linux). The application manages three software sources: AppImages via D-Bus daemon (`appimage-launcher`), Flatpak apps via Flathub, and system packages via the `pkg` wrapper. Phases 4–8 deliver: AppImage updates (P4), the Flathub section (P5), the Pacman/pkg section (P6), install and uninstall wizards (P7), and a final polish and release pass (P8). Phase 4 begins with fixing two currently failing tests before any new feature work.

The implementation follows a strict three-layer architecture (core → services/backends → ui/wizards), never blocks the UI thread, and uses fake backends in all automated tests. Every phase ends with `./check` (ruff + mypy + pytest) green and a stop for owner review.

---

## Glossary

- **AppImageBackend**: The `backends/appimage.py` class that communicates with the `appimage-launcher` daemon over D-Bus using the `Manager1` interface.
- **CatalogEntry**: A single `App` object (model) loaded from `apps.db`, representing one application available in the Aurelis catalog.
- **CommandRunner**: An injectable abstraction over subprocess/QProcess used in `backends/flatpak.py` and `backends/pacman.py` to allow fake substitution in tests.
- **DbusClient**: The `services/qt_dbus.py` wrapper that makes asynchronous `QtDBus` calls and subscribes to D-Bus signals.
- **DetailPage**: The `ui/detail_page.py` widget that shows an individual app's information, action buttons, progress, and operation state.
- **FakeManager1**: An in-process scripted fake of the `Manager1` D-Bus interface used in automated tests; it records calls and emits signals on demand.
- **FlatpakBackend**: The `backends/flatpak.py` class that invokes `flatpak` CLI commands via a CommandRunner.
- **FlathubIndex**: The SQLite database (with FTS5) built from the local Flatpak AppStream XML, stored at `cache/flathub.sqlite`.
- **InstalledApp**: A dataclass (`core/models.py`) representing an application present on the system, including its `origin`, `update_policy`, `locked`, and `pending` fields.
- **MainWindow**: The `ui/main_window.py` QMainWindow that hosts all pages (Explore, Installed, Updates) and coordinates operations.
- **OperationQueue**: The `services/operations.py` FIFO queue that serializes mutating operations per backend.
- **Origin**: A dict persisted in the daemon recording catalog provenance: `{source, catalog_id, version, sha256, changed_at, url}`.
- **PacmanBackend**: The `backends/pacman.py` class that queries pacman for package data and routes install/remove changes through `PkgdClient`.
- **PacmanIndex**: The SQLite database (with FTS5) built from `pacman -Si` output, stored at `cache/pacman.sqlite`.
- **PkgdClient**: The `aurelis_common.rpc.PkgdClient` class that communicates with `aurelis-pkgd` over the Unix socket `/run/aurelis-pkgd.sock` using JSON-RPC 2.0.
- **pkg**: The Aurelis package management CLI (`/usr/bin/pkg`); changes only take effect after the next system reboot via `aurelis-pkg-apply.service`.
- **Sidebar**: The `ui/sidebar.py` widget with section buttons (Explore, Installed, Updates) and a numeric badge on Updates.
- **UpdateInfo**: A dataclass (`core/models.py`) representing an available update: `{app_key, installed_version, new_version, size, method}`.
- **UpdatesPage**: The `ui/updates_page.py` widget that lists all available updates grouped by source, with per-row progress and an "Update all" button.
- **Wizard**: Either the install wizard (`wizards/install_wizard.py`) or the uninstall wizard (`wizards/uninstall_wizard.py`), which are lightweight separate entry points of the same program that never load the catalog or the main window.
- **ZsyncDownloader**: The `services/zsync.py` QObject that runs `zsync` as a QProcess to perform delta updates, with automatic fallback to full download.
- **detect.py**: The `wizards/detect.py` module containing pure functions (with injected readers) that determine what kind of item a file or desktop entry is.
- **pkg-queue**: The JSON-RPC structure returned by `pkg.queue` RPC call: `{"queue": {"install": [...], "remove": [...]}}`.
- **pkg-status**: The JSON-RPC structure returned by `pkg.status` RPC call: `{active_slot, slot_a, slot_b, user_packages, pending, queue}`.
- **pending-reboot banner**: A persistent UI banner shown while `pkg.queue` has entries, informing the user that changes will apply after the next restart.
- **AppStream XML**: The local Flatpak AppStream metadata file at `~/.local/share/flatpak/appstream/flathub/<arch>/active/appstream.xml.gz`.

---

## Requirements

### Requirement 1: Fix failing P4.3 update tests (P4.0)

**User Story:** As the project owner, I want the two failing P4.3 tests to pass before any new Phase 4 work begins, so that the codebase is in a known-good state.

#### Acceptance Criteria

1. WHEN `pytest tests/ui/test_p43_update.py::test_update_failure_daemon_death` is run, THE test suite SHALL pass without modification to the test assertions.
2. WHEN `pytest tests/ui/test_p43_update.py::test_update_busy_state_disables_button` is run, THE test suite SHALL pass without modification to the test assertions.
3. THE fix SHALL NOT skip, xfail, weaken assertions in, or delete the failing tests.
4. WHEN `./check` is run after the fix, THE check script SHALL exit with code 0.

---

### Requirement 2: Update availability computation (P4.1)

**User Story:** As a user, I want the Updates badge to show the correct count of available updates so that I know when apps need updating.

#### Acceptance Criteria

1. WHEN a catalog refresh completes, THE MainWindow SHALL recompute update availability for all installed AppImages and update the Sidebar badge count.
2. WHEN `list_installed` returns a new list from the daemon, THE MainWindow SHALL recompute update availability and update the Sidebar badge count.
3. WHEN `update_available(entry, inst)` returns `True` for an installed AppImage (per spec 4.5), THE Sidebar badge SHALL increment by one for that app.
4. WHEN an installed AppImage has `update_policy == "pinned"`, THE UpdatesPage SHALL NOT list that app and the Sidebar badge SHALL NOT count it.
5. WHEN an installed AppImage has `update_policy == "manual"`, THE UpdatesPage SHALL list that app but THE UpdatesPage SHALL exclude it from the "Update all" action.
6. WHEN an installed AppImage has `self_managed == True` and the setting `updates.include_self_managed` is `False`, THE Sidebar badge SHALL NOT count that app.
7. WHEN the setting `updates.include_self_managed` is `True`, THE UpdatesPage SHALL include self-managing apps in the update list.

---

### Requirement 3: zsync delta update and full-download fallback (P4.2)

**User Story:** As a user, I want AppImage updates to use delta downloads when possible to reduce download time and bandwidth.

#### Acceptance Criteria

1. WHEN `can_delta(entry, installed_path)` is called with a CatalogEntry that has a `zsync_url`, AND `zsync` is present on PATH, AND `installed_path` is not None, AND the file at `installed_path` exists, THE ZsyncDownloader SHALL attempt a delta update using `zsync -i <installed_path> -o <dest.part> <zsync_url>`.
2. WHEN any of the four conditions for `can_delta` are not met, THE ZsyncDownloader SHALL fall back to a full download via Downloader.
3. WHEN the `zsync` process exits with non-zero code or crashes, THE ZsyncDownloader SHALL delete the `.part` file and start exactly one full-download fallback using the entry's `download_url`.
4. WHEN the zsync output file exists and passes `sha256` verification, THE ZsyncDownloader SHALL rename the `.part` file to its final name and emit `finished(path)`.
5. WHEN the zsync output file fails `sha256` verification, THE ZsyncDownloader SHALL delete the `.part` file and start one full-download fallback.
6. WHEN both the zsync attempt and the fallback fail, THE ZsyncDownloader SHALL emit `failed(error)` and leave no `.part` file on disk.
7. WHEN no `sha256` is present in the CatalogEntry, THE ZsyncDownloader SHALL accept the zsync output without hash verification.

---

### Requirement 4: AppImage update flow (P4.3)

**User Story:** As a user, I want to update an installed AppImage and be able to undo the update if something goes wrong.

#### Acceptance Criteria

1. WHEN a user triggers an update, THE MainWindow SHALL call `fetch_update(entry, installed_path, cache_dir, nam)` to obtain the new file, then call `Install(path, {source_action: "move", conflict: "replace", silent: true, origin: build_origin(entry)})` where `origin` contains the new version and sha256.
2. WHEN `Install` returns a result with `changed: true` and a non-empty `previous` list, THE MainWindow SHALL show a success toast with an "Undo" action button.
3. WHEN the user clicks "Undo" on the success toast and the daemon still holds a previous copy (non-empty `previous` in the installed record), THE MainWindow SHALL call `Revert(managed_name)` on the daemon.
4. WHEN `Revert` succeeds, THE MainWindow SHALL recompute the installed app's state from the daemon's reply and update the Sidebar badge to reflect that the update is available again.
5. WHEN any stage of an update fails (download error, checksum mismatch, `Install` error, or daemon unavailability), THE DetailPage SHALL transition to `Failed` state with a "Retry" button.
6. WHEN an update fails at any stage, THE previous version SHALL remain installed and working, and no `.part` or cache file SHALL remain in `cache_dir`.
7. WHILE an update operation is running for a given app, THE DetailPage SHALL display the button text "Updating…" and the action button SHALL be disabled.
8. WHILE an update operation is running for a given app, THE MainWindow SHALL refuse a second update request for the same app.

---

### Requirement 5: Updates page and "Update all" (P4.4)

**User Story:** As a user, I want a dedicated Updates page where I can see all available updates and trigger them individually or all at once.

#### Acceptance Criteria

1. THE UpdatesPage SHALL list all installed apps for which `update_available` returns `True`, grouped by source.
2. WHEN the user clicks "Update all", THE UpdatesPage SHALL run updates sequentially for all apps with `update_policy == "auto"` and SHALL exclude apps with `update_policy == "manual"` or `"pinned"`.
3. WHEN "Update all" is running, THE UpdatesPage SHALL show per-row progress for each app being updated.
4. WHEN "Update all" completes, THE UpdatesPage SHALL show a summary dialog listing which updates succeeded and which failed.
5. WHEN one app's update fails during "Update all", THE UpdatesPage SHALL continue processing the remaining apps and SHALL NOT abort the whole batch.

---

### Requirement 6: Per-app update policy control (P4.5)

**User Story:** As a user, I want to control how each AppImage is updated so that I can pin apps or manage their updates manually.

#### Acceptance Criteria

1. WHEN an installed AppImage's DetailPage is shown, THE DetailPage SHALL display a policy selector with options "Automatic", "Ask me", and "Pinned".
2. WHEN the user changes the policy selector, THE DetailPage SHALL call `SetPolicy(managed_name, policy)` on the daemon with the new policy string (`auto`, `manual`, or `pinned`).
3. WHEN `updates.include_self_managed` is `False` in config, THE UpdatesPage SHALL exclude apps with `self_managed == True` from all update lists.
4. WHEN `updates.include_self_managed` is `True` in config, THE UpdatesPage SHALL include self-managing apps in the update list.
5. THE SettingsDialog SHALL expose a toggle for "Include self-updating apps in Updates" that persists to `config.toml` as `updates.include_self_managed`.

---

### Requirement 7: Update notifications (P4.6)

**User Story:** As a user, I want an optional desktop notification when new updates become available so I do not have to check the app manually.

#### Acceptance Criteria

1. WHERE the setting `updates.notify` is `True`, WHEN the computed update count increases after a catalog refresh, THE MainWindow SHALL emit a desktop notification stating the number of new updates.
2. WHERE the setting `updates.notify` is `False`, THE MainWindow SHALL NOT emit any desktop notification.
3. THE update notification SHALL NOT count apps with `update_policy == "manual"` or `"pinned"` or `self_managed == True` (unless `updates.include_self_managed` is `True`).
4. THE SettingsDialog SHALL expose a toggle for update notifications that persists to `config.toml` as `updates.notify` with a default value of `False`.

---

### Requirement 8: Flathub AppStream index (P5.1)

**User Story:** As a user, I want to browse Flatpak apps from Flathub using locally cached metadata so that the catalog works offline.

#### Acceptance Criteria

1. THE FlatpakBackend SHALL build a SQLite FlathubIndex with an FTS5 table (name, summary, keywords) from the AppStream XML at `~/.local/share/flatpak/appstream/flathub/<arch>/active/appstream.xml.gz`, falling back to the system path if the user path is absent.
2. WHEN the AppStream XML file's mtime is unchanged since the last index build, THE FlatpakBackend SHALL skip rebuilding the FlathubIndex and use the cached version.
3. WHEN the AppStream XML file's mtime has changed, THE FlatpakBackend SHALL rebuild the FlathubIndex in a worker thread and display a progress indicator in the UI.
4. WHEN the first-run index build begins, THE MainWindow SHALL show a progress indicator labeled "Indexing Flathub apps…".
5. WHEN the AppStream XML contains entries with `xml:lang` variants matching the current locale, THE FlathubIndex SHALL store those translated name, summary, and keyword values alongside the base English values.
6. WHEN the AppStream XML file is absent or unreadable, THE FlatpakBackend SHALL set `available = False` and THE MainWindow SHALL show a banner explaining that the Flathub index is unavailable.

---

### Requirement 9: Flathub browse, search, and categories (P5.2)

**User Story:** As a user, I want to browse, search, and filter Flatpak apps by category without stalls in the UI.

#### Acceptance Criteria

1. THE FlathubModel SHALL implement `canFetchMore`/`fetchMore` pagination using `LIMIT`/`OFFSET` SQL queries against the FlathubIndex, never loading thousands of `App` objects into memory at once.
2. WHEN a search query is entered, THE FlathubModel SHALL query the FTS5 index for matching apps and update the view within 100 ms.
3. WHEN a category is selected in the Sidebar, THE FlathubModel SHALL filter results by that store category using the FlathubIndex.
4. WHEN a Flatpak app card is selected, THE DetailPage SHALL render the app using the existing detail page UI with `source = Source.FLATPAK`.
5. WHEN a Flatpak app has an `icon` available in the AppStream cached icons directory (`.../active/icons/<size>/`), THE DetailPage SHALL load and display that icon.

---

### Requirement 10: Flatpak backend operations (P5.3)

**User Story:** As a user, I want to install, remove, and update Flatpak apps from the GUI without using a terminal.

#### Acceptance Criteria

1. THE FlatpakBackend SHALL list installed user apps by running `flatpak list --user --app --columns=application,version,origin` via CommandRunner.
2. THE FlatpakBackend SHALL list available updates by running `flatpak remote-ls --user --updates --app --columns=application,version` via CommandRunner.
3. WHEN the user triggers install of a Flatpak app, THE FlatpakBackend SHALL run `flatpak install --user --noninteractive -y flathub <app-id>` via CommandRunner and emit `OperationEvent` signals.
4. WHEN the user triggers removal of a Flatpak app, THE FlatpakBackend SHALL run `flatpak uninstall --user --noninteractive -y <app-id>` via CommandRunner and emit `OperationEvent` signals.
5. WHEN the user triggers update of a Flatpak app, THE FlatpakBackend SHALL run `flatpak update --user --noninteractive -y <app-id>` via CommandRunner and emit `OperationEvent` signals.
6. THE CommandRunner injected into FlatpakBackend SHALL be replaceable with a fake for testing without touching the real `flatpak` binary.
7. IF the `flatpak` binary is not found on PATH, THEN THE FlatpakBackend SHALL set `available = False` and THE MainWindow SHALL show a banner explaining that Flatpak is unavailable.

---

### Requirement 11: Flatpak progress and "Add Flathub remote" (P5.4, P5.5)

**User Story:** As a user, I want to see progress during Flatpak operations and be guided to add Flathub if it is missing.

#### Acceptance Criteria

1. WHILE a Flatpak install, remove, or update operation is running and the CLI is not producing TTY progress, THE DetailPage SHALL show an indeterminate progress bar.
2. WHEN `flatpak remote-list --user` output does not contain `flathub`, THE FlatpakBackend SHALL set a flag `flathub_remote_missing = True`.
3. WHERE `flathub_remote_missing` is `True`, THE MainWindow SHALL show a banner offering to add the Flathub remote.
4. WHEN the user confirms adding the remote, THE FlatpakBackend SHALL run `flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo` via CommandRunner and then trigger an AppStream metadata refresh.
5. WHEN "Refresh Flathub metadata" is triggered by the user, THE FlatpakBackend SHALL run `flatpak update --appstream --user` via CommandRunner in a background QProcess, then rebuild the FlathubIndex.

---

### Requirement 12: Flathub integration into Installed, Updates, and cross-source view (P5.6)

**User Story:** As a user, I want to see my Flatpak apps alongside AppImage and Pacman apps in the unified Installed and Updates views.

#### Acceptance Criteria

1. THE InstalledPage SHALL display installed Flatpak apps in the Flatpak group with their name, version, and source tag.
2. THE UpdatesPage SHALL display available Flatpak updates in the Flatpak group.
3. WHEN both a Flatpak and an AppImage entry share the same `id`, THE DetailPage SHALL display an "Also available as" section with a button to switch to the other source.
4. WHEN the `flatpak` binary is absent, THE InstalledPage SHALL omit the Flatpak group without error.

---

### Requirement 13: Pacman index (P6.2)

**User Story:** As a user, I want to search and browse Arch Linux packages from the GUI without running terminal commands.

#### Acceptance Criteria

1. THE PacmanBackend SHALL build a SQLite PacmanIndex with an FTS5 table (name, description) from parsing `pacman -Si` output via CommandRunner.
2. WHEN the mtime of any file in `/var/lib/pacman/sync/*.db` is newer than the PacmanIndex's last-built timestamp, THE PacmanBackend SHALL rebuild the PacmanIndex in a worker thread.
3. WHEN a search query is entered on the Pacman page, THE PacmanBackend SHALL query the FTS5 index and return results within 100 ms.
4. THE PacmanIndex build SHALL use fixtures captured from real `pacman -Si` output in `tests/fixtures/pacman/` for all automated tests.
5. WHEN the PacmanIndex build encounters a malformed entry in the `pacman -Si` output, THE PacmanBackend SHALL skip that entry, log a warning, and continue.

---

### Requirement 14: Installed package classification and display (P6.3)

**User Story:** As a user, I want to see which packages I installed myself versus which are part of the system, and understand their dependencies.

#### Acceptance Criteria

1. THE PacmanBackend SHALL classify installed packages as "core" if listed in `/usr/lib/aurelis/core-packages.json` and as "user" if listed in `/var/lib/aurelis/user-packages.json`.
2. WHEN a core package is shown in the InstalledPage, THE InstalledPage SHALL display a lock icon and the text "Part of the system" and SHALL disable the Remove action.
3. WHEN the user clicks "Show dependencies" for a user package, THE InstalledPage SHALL display a list of that package's dependencies derived from `pacman -Qi` output.
4. THE InstalledPage SHALL display installed Pacman packages in the Pacman group with their name, version, and source tag.
5. WHEN a package is locked (core), THE InstalledPage's Remove action for that package SHALL be disabled regardless of any other state.

---

### Requirement 15: Pacman backend operations via pkg (P6.4)

**User Story:** As a user, I want to queue package installs and removals through the GUI and see them reflected as pending changes.

#### Acceptance Criteria

1. WHEN the user triggers install of a Pacman package, THE PacmanBackend SHALL call `PkgdClient().install([package_name])` and emit a `OperationEvent` sequence (Started, Finished or Failed).
2. WHEN the user triggers removal of a user Pacman package, THE PacmanBackend SHALL call `PkgdClient().remove([package_name])` and emit the corresponding `OperationEvent` sequence.
3. WHEN the user triggers removal of a core (locked) package, THE PacmanBackend SHALL emit `Failed` with a `Locked` error immediately without calling PkgdClient.
4. WHEN `PkgdClient` raises `PkgdDownError`, THE PacmanBackend SHALL emit `Failed` with a `DaemonUnavailable` error.
5. WHEN removing a user package that other user packages depend on, THE PacmanBackend SHALL show a reverse-dependency warning dialog before calling PkgdClient.
6. THE PkgdClient used by PacmanBackend SHALL be injectable with a fake for all automated tests; no test SHALL connect to the real `/run/aurelis-pkgd.sock`.

---

### Requirement 16: Pending-reboot banner and pending state (P6.5)

**User Story:** As a user, I want to know that my queued package changes will take effect after a restart, and I want that state to persist across GUI restarts.

#### Acceptance Criteria

1. WHEN `PkgdClient().queue()` returns a non-empty install or remove list, THE MainWindow SHALL display the pending-reboot banner.
2. WHEN the pending-reboot banner is visible, THE MainWindow SHALL display it persistently until the queue is empty.
3. WHEN the GUI starts, THE MainWindow SHALL query `PkgdClient().queue()` and restore the pending-reboot banner if the queue is non-empty.
4. WHEN a package has been queued for install or removal, THE InstalledPage SHALL show that package with a "Pending restart" tag.
5. WHEN the pending-reboot banner is active, THE MainWindow SHALL offer a "Cancel pending changes" action that calls `PkgdClient().queue_clear()`.

---

### Requirement 17: Pacman updates staged through pkg (P6.6)

**User Story:** As a user, I want the GUI to reflect that Pacman package updates apply only after a restart, with no ambiguity about timing.

#### Acceptance Criteria

1. THE UpdatesPage SHALL list available Pacman package updates in the Pacman group with the note "Applies after restart".
2. WHEN the user triggers a Pacman package update, THE PacmanBackend SHALL call `PkgdClient().install([package_name])` with the new version and show the pending-reboot banner.
3. THE UpdatesPage SHALL NOT display Pacman updates as immediately applied; the state after queuing SHALL be "Pending restart", not "Installed".
4. WHEN a Pacman update is queued, THE Sidebar badge SHALL decrement that package from the update count and show it in the Installed page as "Pending restart".

---

### Requirement 18: Pacman failure tests (P6.7)

**User Story:** As a developer, I want comprehensive failure tests for the Pacman backend so that edge cases are caught before release.

#### Acceptance Criteria

1. WHEN `PkgdClient` returns a `pkg` error with message starting "Package not found:", THE PacmanBackend SHALL emit `Failed` with a user-readable "Package not found" message.
2. WHEN `PkgdClient` raises an error indicating a package conflict, THE PacmanBackend SHALL emit `Failed` with a "Package conflict" message.
3. WHEN the user attempts to remove a locked package via the backend directly, THE PacmanBackend SHALL emit `Failed` with a `Locked` error.
4. WHEN `pkg` is not installed (PkgdClient cannot connect), THE PacmanBackend SHALL set `available = False` and THE MainWindow SHALL display a banner explaining that system package management is unavailable.
5. THE test suite SHALL contain at least one test for each of the four failure cases above, using injected fakes for PkgdClient.

---

### Requirement 19: Wizard detection logic (P7.1)

**User Story:** As a developer, I want the wizard detection logic to be pure functions with injected readers so that every branch can be tested without touching the filesystem.

#### Acceptance Criteria

1. THE `detect.py` module SHALL expose pure functions that accept filesystem readers as parameters and return the detection result without performing any direct I/O.
2. WHEN the path is an AppImage file inside `~/Applications` OR a `.desktop` file with `X-AppImage-Managed=true`, THE detection function SHALL return `("appimage", app_id)`.
3. WHEN the path is a `.desktop` file under a Flatpak exports directory (`/var/lib/flatpak/exports/` or `~/.local/share/flatpak/exports/`), THE detection function SHALL return `("flatpak", app_id)` where `app_id` is derived from the desktop file name.
4. WHEN `pacman -Qo <path>` (invoked via the injected reader) names a package listed in `/usr/lib/aurelis/core-packages.json`, THE detection function SHALL return `("pacman-core", package_name)`.
5. WHEN `pacman -Qo <path>` names a package listed in `/var/lib/aurelis/user-packages.json`, THE detection function SHALL return `("pacman-user", package_name)`.
6. WHEN no detection rule matches, THE detection function SHALL return `("unknown", None)`.
7. THE test suite SHALL contain at least one test for each of the six detection outcomes listed above, using injected fake readers.

---

### Requirement 20: Install wizard (P7.2)

**User Story:** As a user, I want double-clicking an AppImage or Flatpak file outside my Applications folder to open an install wizard.

#### Acceptance Criteria

1. WHEN the install wizard entry point is called with a path to an AppImage that is already inside `~/Applications` or whose `Inspect` result reports it is the installed primary's path, THE wizard SHALL launch that AppImage directly without showing any UI.
2. WHEN the install wizard entry point is called with a path to an AppImage outside `~/Applications`, THE wizard SHALL show Page 1 with the name, icon, and version from `Inspect(path)`, plus relation wording ("will update", "will downgrade", or "first install") if an existing installation is detected.
3. WHEN the user clicks "Install" on Page 1, THE wizard SHALL slide to Page 2 showing "Installing…" with a spinner, then call `Install(path, {source_action: "copy", conflict: "replace", silent: true})` via AppImageBackend.
4. WHEN the user clicks "Just run" on Page 1, THE wizard SHALL execute the AppImage file directly (the only place in the application where a file is executed) without installing it.
5. WHEN "Just run" is clicked and "Don't ask again" is checked, THE wizard SHALL store `{app_id, sha256}` in `config.wizard.run_without_asking`, and subsequent double-clicks with the same `app_id` and `sha256` SHALL skip Page 1 and run directly.
6. WHEN a Flatpak `.flatpakref` or `.flatpak` file is passed to the install wizard, THE wizard SHALL call `flatpak install --user <file>` on Page 2 instead of the D-Bus `Install` call.
7. WHEN the install wizard completes successfully, THE wizard SHALL show the message "Open it from your Applications folder or the menu" and offer "Open" and "Close" buttons on Page 2.
8. WHEN the wizard process starts, THE wizard SHALL display Page 1 within 500 ms without loading the main catalog or the main window.

---

### Requirement 21: Uninstall wizard (P7.3)

**User Story:** As a user, I want a guided uninstall experience that clearly explains what will happen and prevents accidental removal of system packages.

#### Acceptance Criteria

1. WHEN the uninstall wizard is called for a path detected as `("pacman-core", ...)`, THE wizard SHALL display a dialog saying the application cannot be uninstalled and offer only a "Close" button.
2. WHEN the uninstall wizard is called for a path detected as `("appimage", app_id)`, THE wizard SHALL show Page 1 with the app name, icon, type "AppImage", and a confirmation message.
3. WHEN the user proceeds from Page 1 for an AppImage, THE wizard SHALL call `Remove(managed_name, {file_action: "trash", silent: true})` on the daemon and show progress on Page 2.
4. WHEN the uninstall wizard is called for a path detected as `("flatpak", app_id)`, THE wizard SHALL call `flatpak uninstall --user --noninteractive -y <app-id>` and show progress on Page 2.
5. WHEN the uninstall wizard is called for a path detected as `("pacman-user", package_name)`, THE wizard SHALL call `PkgdClient().remove([package_name])` and display a note on Page 2 saying "The change takes effect after restart".
6. WHEN the uninstall wizard is called for a path detected as `("unknown", None)`, THE wizard SHALL display a dialog saying "Aurelis Software cannot remove this application" and offer only a "Close" button.

---

### Requirement 22: MIME and desktop integration (P7.4)

**User Story:** As a user, I want double-clicking an AppImage or Flatpak file in Dolphin to open the install wizard automatically.

#### Acceptance Criteria

1. THE `aurelis-software-wizard-install.desktop` file SHALL declare MIME type handlers for `application/vnd.appimage`, `application/vnd.flatpak.ref`, and `application/vnd.flatpak`.
2. THE `aurelis-software-uninstall.desktop` file SHALL be a Dolphin service-menu file providing an "Uninstall with Aurelis Software" action on AppImage files and `.desktop` entries.
3. WHEN `desktop-file-validate` is run on each `.desktop` file, THE validation SHALL exit with code 0.
4. THE PKGBUILD in `packaging/PKGBUILD` SHALL install both `.desktop` files to their correct system locations.

---

### Requirement 23: Wizard fast startup (P7.5)

**User Story:** As a user, I want the install wizard to appear quickly so that the double-click experience feels responsive.

#### Acceptance Criteria

1. WHEN the install wizard process is started, THE first wizard page SHALL be visible and interactive within 500 ms on the owner's machine.
2. THE wizard process SHALL NOT load the catalog (`apps.db`) or any FlathubIndex or PacmanIndex during startup.
3. THE test suite SHALL contain a startup-time test that measures the elapsed time from process start to `show()` and asserts it is under 500 ms.

---

### Requirement 24: Wizard offscreen UI tests (P7.6)

**User Story:** As a developer, I want automated UI tests for every wizard page and error state so that regressions are caught in CI.

#### Acceptance Criteria

1. THE test suite SHALL contain an offscreen UI test (`QT_QPA_PLATFORM=offscreen`) for every wizard page (install Page 1, install Page 2, uninstall Page 1, uninstall Page 2).
2. THE test suite SHALL contain offscreen UI tests for each error case: `Inspect` failure, install failure, removal of system package, `Busy` from daemon, and unrecognized file type.
3. ALL wizard UI tests SHALL use fake backends and SHALL NOT call the real D-Bus daemon, real `flatpak` binary, or real `PkgdClient`.

---

### Requirement 25: Explore page polish (P8.1)

**User Story:** As a user, I want the Explore page to highlight recently updated and featured apps so I can discover new software easily.

#### Acceptance Criteria

1. THE Explore page SHALL show a "Recently updated" row containing apps sorted descending by `version_changed_at` from the catalog.
2. THE Explore page SHALL show per-category rows for each store category that has at least one app in the catalog.
3. THE Explore page SHALL show a "Featured" area at the top using a list of app IDs declared in a config key `ui.featured_ids`.
4. WHEN the catalog has no apps, THE Explore page SHALL show an empty-state message with guidance.

---

### Requirement 26: Greek translation (P8.2)

**User Story:** As a Greek-speaking user, I want the application to be available in Greek so that I can use it in my native language.

#### Acceptance Criteria

1. THE build process SHALL produce a Greek `.qm` file from `.ts` source using `pylupdate6` and `lrelease`.
2. WHEN `ui.language` is set to `el` in config, THE MainWindow SHALL load the Greek `.qm` file and display all UI strings in Greek.
3. WHEN the Greek translation is loaded, all widget layouts SHALL remain visually correct with the translated (potentially longer) strings.
4. THE test suite SHALL contain a test that switches to the Greek locale and verifies no layout truncation or overflow.

---

### Requirement 27: Accessibility pass (P8.3)

**User Story:** As a user who relies on keyboard navigation or assistive technology, I want the application to be fully keyboard-navigable with accessible names.

#### Acceptance Criteria

1. THE MainWindow SHALL be fully navigable using only keyboard input (Tab, Shift+Tab, Enter, arrow keys, `Ctrl+F`, `Esc`, `Alt+Left`).
2. EVERY interactive widget (buttons, list items, combo boxes, checkboxes) SHALL have an accessible name set via `setAccessibleName()`.
3. EVERY status badge and icon-only button SHALL convey its information through both color and a text label or accessible name, not through color alone.
4. WHEN the application is viewed with a high-contrast or dark theme, ALL badge colors SHALL meet WCAG AA contrast ratio (4.5:1 minimum) with their background.

---

### Requirement 28: Performance pass (P8.4)

**User Story:** As a user, I want the application to start quickly and remain responsive so that it does not feel slow.

#### Acceptance Criteria

1. WHEN the application starts with a cached catalog, THE MainWindow SHALL be visible and interactive within 1000 ms.
2. WHEN the install wizard starts, THE first wizard page SHALL be visible within 500 ms.
3. WHEN `load_catalog` is called with a 500-entry catalog, THE parse SHALL complete within 100 ms in a worker thread.
4. WHEN a search query keystroke arrives with 500 catalog entries loaded, THE updated results SHALL appear within 50 ms.
5. WHEN FlatpakIndex or PacmanIndex is queried for a search with FTS5, THE results SHALL be returned within 100 ms.
6. WHEN the app list grid is scrolled with 500 visible cards, THE scrolling SHALL proceed without dropped frames.
7. WHEN the application is idle with the catalog loaded, process RSS memory SHALL not exceed 150 MB.

---

### Requirement 29: Packaging and release (P8.5, P8.6)

**User Story:** As the project owner, I want a complete PKGBUILD and release artifacts so the application can be installed on Aurelis.

#### Acceptance Criteria

1. THE `packaging/PKGBUILD` SHALL declare runtime dependencies on `python`, `python-pyqt6`, `appimage-launcher`, `flatpak`, and `aurelis-common`.
2. THE `packaging/PKGBUILD` SHALL install the application's `.desktop` files, icons, and `.qm` translation files to their correct system locations.
3. WHEN `makepkg` is run against the PKGBUILD on a clean Aurelis VM, THE build SHALL succeed and the installed package SHALL allow the application to start offline from a pre-seeded cache.
4. THE release checklist SHALL include: version bump in `pyproject.toml`, update of `CHANGELOG.md`, creation of a git tag in the form `v<version>`, and a CI build of the package.
5. THE `docs/architecture.md` file SHALL describe the final layer structure, threading model, and backend interface as implemented.

---

### Requirement 30: Architecture and testing invariants (cross-cutting)

**User Story:** As the project owner, I want the architecture rules and testing standards maintained throughout all phases so that the codebase remains correct and maintainable.

#### Acceptance Criteria

1. THE `core/` package SHALL NOT import `PyQt6` at any point; a test SHALL enforce this by asserting no `PyQt6` symbol appears in `core/` imports.
2. THE UI thread SHALL NOT call `subprocess.run`, `urllib`, or any blocking file I/O; operations SHALL be performed in workers, QProcess, QNetworkAccessManager, or asynchronous D-Bus calls.
3. WHEN `./check` is run (ruff + mypy + pytest), THE check script SHALL exit with code 0 before any commit.
4. THE test suite SHALL NOT add new ruff ignores, mypy excludes, skipped tests, xfailed tests, or weakened assertions to pass.
5. WHEN a new backend class is added, THE class SHALL be reachable from the `main` entry point; the phase report SHALL document the call path from entry point to each new component.
6. EVERY new user-visible error path SHALL have a test that verifies both the error message shown and that no leftover files exist in the cache after the failure.
