# Requirements: Aurelis Software Center — Phase 4 through Phase 8

## Overview

Complete the Aurelis Software Center PyQt6 application from Phase 4 (AppImage updates) through Phase 8 (Polish and release). The application is a GNOME-Software-style center for Aurelis (immutable Arch Linux) managing three software sources: AppImages via D-Bus daemon, Flathub via flatpak CLI, and Pacman via `pkg` wrapper.

Phases 0–3 are complete. This specification covers Phase 4 (AppImage updates), Phase 5 (Flathub), Phase 6 (Pacman), Phase 7 (Wizards), and Phase 8 (Polish and release). **One phase at a time, stop for owner review after each phase.**

---

## R1 — Fix two failing Phase 4 tests (prerequisite, Phase 4 gate)

### R1.1
In `_call_update_install.on_error`, pop `op_id` from `_active_operations` **before** calling `_recompute_updates()`, so the badge does not show a stale update entry for an operation that already failed.

### R1.2
In `_button_config_for_state`, the `"Updating"` state must return `{"text": "Updating…", "enabled": False}` so the button is disabled while an update is in progress (`test_update_busy_state_disables_button`).

### R1.3
In `_start_update.on_finished`, emit `progress(step="handoff")` before the D-Bus `Install` call, so the UI transitions to the indeterminate "Finishing…" phase before handing off to the daemon.

---

## R2 — Update availability and badge (Phase 4.1)

### R2.1
After each catalog refresh and after each `list_installed` result, recompute the update list using `core/versions.py` rules (spec 4.5). The result must reflect policies: `auto` and `manual` apps appear; `pinned` apps never appear; `self_managed` apps appear only when "Include self-updating apps" is enabled.

### R2.2
The sidebar **Updates** badge must show the count of available updates. It increments when a catalog bump introduces new updates and decrements when an update completes or the app is removed.

### R2.3
After a successful update, `update_available` for that app must become `False` immediately (the new origin's version/sha256 matches the catalog entry).

---

## R3 — zsync delta update and fallback (Phase 4.2)

### R3.1
When a catalog entry has `zsync_url` and the `zsync` binary is present and the installed file path is known, use `zsync -i <installed_path> -o <cache/new.part> <zsync_url>` for the delta download.

### R3.2
When zsync is unavailable or its URL is absent, fall back to a full download via `services/downloader.py` (spec 7.4).

### R3.3
After either method, verify `sha256` when present. A mismatch must delete the `.part` file and surface `ChecksumMismatch`.

---

## R4 — Update flow and Undo (Phase 4.3)

### R4.1
The update calls `Install(newfile, {source_action: "move", conflict: "replace", silent: true, origin: <new origin>})`. The new origin must carry the new version and sha256 so that `update_available()` returns `False` after the operation.

### R4.2
On success, show a toast with an **Undo** button that calls `Revert(managed_name)`. The Undo button is only shown while the daemon reports a non-empty `previous` list for that app.

### R4.3
After a successful Undo, the installed version reverts to the previous one, `update_available` becomes `True` again, and the badge count increases by 1.

### R4.4
A failure at any stage (download, checksum, Install error, daemon death) must leave the previous version installed and working, delete any `.part` cache file, show the detail page in `Failed` state with a **Retry** button, and leave the badge count unchanged.

---

## R5 — Updates page and Update all (Phase 4.4)

### R5.1
`ui/updates_page.py` lists available updates grouped by source. Each row has a checkbox and a per-row **Update** button with inline progress.

### R5.2
**Update all** runs only the `auto`-policy apps sequentially through the operation queue. `manual`-policy apps are excluded.

### R5.3
When Update all finishes, show a summary dialog listing per-app results (success, failure, skipped).

### R5.4
Pacman rows in the Updates page must display the "applies after restart" note.

---

## R6 — Per-app update policy (Phase 4.5)

### R6.1
The detail page for installed AppImages shows a policy selector: **Automatic** / **Ask me** / **Pinned**. Changing it calls `SetPolicy(managed_name, policy)` over D-Bus.

### R6.2
The "Include self-updating apps" setting in Settings wires to `updates.include_self_managed` in config. Changing it immediately triggers a recompute of the update list.

---

## R7 — Update notifications (Phase 4.6)

### R7.1
When the update count increases after a catalog refresh, and the user has enabled "Notify about updates" in Settings (default off), emit a desktop notification. `manual`, `pinned`, and `self_managed` apps are excluded from the count used for notifications.

---

## R8 — Flathub AppStream index (Phase 5.1)

### R8.1
Parse the local Flatpak AppStream XML (gzip-compressed) into a SQLite database (`cache/flathub.sqlite`) with an FTS5 table on name, summary, and keywords. Use the stdlib `sqlite3` module only.

### R8.2
Parsing runs in a worker thread with a progress indicator visible in the UI. The main thread never blocks.

### R8.3
Rebuild the index only when the AppStream XML's mtime changes from the previously recorded value.

### R8.4
Use `xml:lang` variants for the current locale when present on `<name>`, `<summary>`, and `<keywords>` elements.

### R8.5
If the AppStream file does not exist at the expected path, offer a **Refresh Flathub metadata** action that runs `flatpak update --appstream --user`.

---

## R9 — Flathub browse, search, and detail (Phase 5.2)

### R9.1
The Flathub section uses a paginated model (`canFetchMore`/`fetchMore`) backed by FTS5 `LIMIT`/`OFFSET` queries. No more than a page of `App` objects is in memory at once.

### R9.2
Search in the Flathub section queries the FTS5 index. Results update within 100 ms of a keystroke (budget from spec 13).

### R9.3
The detail page reuses the existing `DetailPage` component with `source=flatpak`.

### R9.4
Icons are loaded from the AppStream `cached` icon paths under `.../active/icons/<size>/` with the theme fallback `application-x-executable`.

---

## R10 — Flatpak backend (Phase 5.3)

### R10.1
`backends/flatpak.py` implements the `Backend` ABC for `Source.FLATPAK` using `QProcess`-based command execution with an injected command runner.

### R10.2
`list_installed` runs `flatpak list --user --app --columns=application,version,origin`.

### R10.3
`list_updates` runs `flatpak remote-ls --user --updates --app --columns=application,version`.

### R10.4
`install` runs `flatpak install --user --noninteractive -y flathub <app-id>`.

### R10.5
`remove` runs `flatpak uninstall --user --noninteractive -y <app-id>`.

### R10.6
`update` runs `flatpak update --user --noninteractive -y <app-id>`.

### R10.7
If `flatpak` is not found, `available` is `False`, the section is hidden, and a banner explains the missing tool.

---

## R11 — Flatpak progress (Phase 5.4)

### R11.1
Progress is shown as an indeterminate bar when the `flatpak` CLI produces coarse non-TTY output. No PTY or PyGObject dependency.

---

## R12 — Flathub remote and integration (Phase 5.5, 5.6)

### R12.1
If no user Flathub remote is configured, show an **Add Flathub** inline action that runs `flatpak remote-add --user --if-not-exists flathub <flatpakrepo>`.

### R12.2
A **Refresh Flathub metadata** action in the Flathub section header runs `flatpak update --appstream --user` and rebuilds the index on completion.

### R12.3
Installed Flatpak apps appear in the **Installed** page. Updates appear in the **Updates** page. The `app_id` appears in "Also available as" on AppImage detail pages when a Flatpak with the same `id` is found in the index.

---

## R13 — Pacman index (Phase 6.2)

### R13.1
Build a SQLite index (`cache/pacman.sqlite`) from `pacman -Si` output with an FTS5 table on name and description. Rebuild when any file under `/var/lib/pacman/sync/` has an mtime newer than the index.

### R13.2
The index stores: name, version, description, repository, groups, installed size, download size, URL, license, and depends.

### R13.3
Index building runs in a worker thread. The main thread never blocks.

---

## R14 — Package classification (Phase 6.3)

### R14.1
Packages listed in `/usr/lib/aurelis/core-packages.json` are **locked** (shown with a lock icon, Remove action disabled, `InstalledApp.locked = True`).

### R14.2
Packages listed in `/var/lib/aurelis/user-packages.json` are user-installed and can be removed.

### R14.3
"Show dependencies" toggle in the Installed page reveals dependency packages not in either classification file.

---

## R15 — Pacman backend (Phase 6.4)

### R15.1
`backends/pacman.py` implements the `Backend` ABC for `Source.PACMAN`.

### R15.2
`list_installed` runs `pacman -Qq` / `pacman -Qi` with captured output parsed in `core/pacman_parser.py`.

### R15.3
`install` calls `pkg add <package>` via the injected command runner. Exit 0 = success; exit 1 = failure.

### R15.4
`remove` calls `pkg remove <package>`. Before calling, check reverse dependencies via `pacman -Qi` "Required By" and show a warning dialog when removing a package that other user packages depend on.

### R15.5
`pending` state comes from `pkg queue` (RPC method returning `{"queue": {"install": [...], "remove": [...]}}`). The backend exposes the pending state without reading any GUI-owned file.

### R15.6
If `pkg` is not installed, `available` is `False` and the Pacman section degrades gracefully with a banner.

---

## R16 — Pending-reboot banner (Phase 6.5)

### R16.1
After a `pkg add` or `pkg remove` succeeds, show the persistent **pending-reboot banner** ("Changes will take effect after restart").

### R16.2
On next GUI launch, query `pkg queue` to restore the pending state without reading any GUI-owned file.

### R16.3
The affected package rows show `InstalledApp.pending = "install"` or `"remove"` with the "Pending restart" tag in the Installed and Updates pages.

---

## R17 — Staged pacman updates (Phase 6.6)

### R17.1
The Updates page lists available pacman updates (from `pkg queue` pending install list when a newer version is available). Each row carries the "applies after restart" note.

---

## R18 — Pacman failure tests (Phase 6.7)

### R18.1
Tests cover: package not found, package conflicts, locked package removal attempt, `pkg` binary missing. Each scenario surfaces the correct error message and leaves no inconsistent state.

---

## R19 — Wizard detection (Phase 7.1)

### R19.1
`wizards/detect.py` contains pure functions with injected readers. No Qt, no subprocess.

### R19.2
Detection order:
1. AppImage inside `~/Applications` or desktop entry with `X-AppImage-Managed=true` → **appimage**
2. Desktop entry under a Flatpak exports directory → **flatpak** (id from filename)
3. `pacman -Qo <path>` returns a package → **pacman** (sub-type: system if in core-packages.json, user otherwise)
4. Otherwise → **unknown**

### R19.3
Table-driven tests for every detection branch must pass without Qt installed.

---

## R20 — Install wizard (Phase 7.2)

### R20.1
Entry point: `aurelis-software wizard install <path>`. Must show first page in under 500 ms (no catalog load).

### R20.2
Routing: if the file is an AppImage already inside `~/Applications` or `Inspect` reports it as the installed primary's path, **just launch it** (`appimage run <name>`) and show no UI.

### R20.3
Page 1 displays: name, icon, version from `Inspect`; wording for the `relation` field ("will be installed", "will update X → Y", "will downgrade Y → X", "same version already installed"). Controls: **Install**, **Just run** with "Don't ask again" checkbox, **Cancel**.

### R20.4
Page 2 (slide-in): "Installing…" spinner, then Done. For AppImages calls `Install(path, {source_action: "copy", conflict: "replace", silent: true})`. For Flatpak files calls `flatpak install --user <file>`.

### R20.5
**Just run** executes the file once without installing. If "Don't ask again" is checked, store `{app_id, sha256}` in `wizard.run_without_asking` in config. The next double-click with the same `app_id` and sha256 runs directly.

### R20.6
The Settings dialog lists entries in `wizard.run_without_asking` with a **Remove** button for each.

---

## R21 — Uninstall wizard (Phase 7.3)

### R21.1
Entry point: `aurelis-software wizard uninstall <path-or-desktop-id>`.

### R21.2
System packages show a refusal page ("Aurelis Software cannot remove this application") with only a **Close** button.

### R21.3
Page 1: name, icon, type label ("AppImage", "Flatpak", "Arch package"), confirmation message.

### R21.4
Page 2 (slide-in): progress and spinner. Calls the correct removal for each type:
- AppImage: `Remove(name, {file_action: "trash", silent: true})`
- Flatpak: `flatpak uninstall --user --noninteractive -y <app-id>`
- Pacman user package: `pkg remove <package>` with the "takes effect after restart" note

---

## R22 — MIME and desktop integration (Phase 7.4)

### R22.1
`aurelis-software-wizard-install.desktop` is a NoDisplay MIME handler for `application/vnd.appimage`, `application/vnd.flatpak.ref`, and `application/vnd.flatpak`.

### R22.2
A Dolphin service-menu file triggers the uninstall wizard on AppImage files in `~/Applications`.

### R22.3
Both `.desktop` files pass `desktop-file-validate`.

---

## R23 — Wizard fast start (Phase 7.5)

### R23.1
The wizard process must display its first page within 500 ms. No catalog loading, no main window, no AppStream index building occurs on wizard startup.

---

## R24 — Wizard UI tests (Phase 7.6)

### R24.1
Offscreen pytest-qt tests cover every page of both wizards and every error path, using fake backends.

---

## R25 — Explore page polish (Phase 8.1)

### R25.1
The Explore page shows a "Recently updated" row (top 6 apps by `version_changed_at`), one row per category with horizontally scrollable cards, and an "All apps" grid below.

---

## R26 — Greek translation (Phase 8.2)

### R26.1
Run `pylupdate6` to extract all `tr()` strings into a `.ts` file, translate all strings to Greek, compile to `.qm`, and wire the language switcher so selecting Greek loads the translation at runtime without restart.

### R26.2
Layouts must not break with Greek strings (which are typically longer than English).

---

## R27 — Accessibility (Phase 8.3)

### R27.1
Full keyboard navigation: every interactive element is reachable with Tab/Shift-Tab and activatable with Enter/Space.

### R27.2
All interactive elements have accessible names (`setAccessibleName` or labels associated via `setBuddy`).

### R27.3
Badge colors meet WCAG AA contrast in both light and dark system themes.

### R27.4
No information is conveyed by color alone.

---

## R28 — Performance pass (Phase 8.4)

### R28.1
All performance budgets from spec section 13 are met and recorded in the README:
- Window visible with cached catalog: < 1 s
- Wizard first page: < 500 ms
- Catalog parse (500 apps): < 100 ms (worker)
- Search keystroke to updated list (500 apps): < 50 ms
- Flathub/pacman FTS search: < 100 ms
- Folder change to GUI update: < 1 s
- Idle memory with catalog loaded: < 150 MB

---

## R29 — Packaging and release (Phase 8.5, 8.6)

### R29.1
`packaging/PKGBUILD` packages the application with correct depends (including `appimage-launcher`), installs `.desktop` files and icon, and builds without errors on a clean Arch system.

### R29.2
The release checklist includes: version bump, changelog entry, git tag, and CI build of the package.

### R29.3
Installing from the built package on a clean Aurelis VM must start the app offline from a pre-seeded cache.
