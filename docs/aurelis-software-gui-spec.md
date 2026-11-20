# Aurelis Software: PyQt6 Software Center and Wizards
## Architecture, Specification and Delivery Plan (v2)

Audience: a coding agent (Zoo Code in VS Code) working in the repository `aurelis-software`.
Owner: apapamarkou.

### Repositories and relationships

| Repository | Role | Relation to this project |
|---|---|---|
| `aurelis-software-database` | Builds the weekly catalog (`apps.db`, icons) | **Data source.** Consumed through the two release assets only. |
| `appimage-launcher` | Daemon, CLI, public D-Bus API `Manager1`; owns `~/Applications` | **Backend for AppImages.** Consumed only through D-Bus (section 9.1). |
| `aurelis-software` (this repo) | Software Center + install/uninstall wizards | Everything in this document. |
| `pkg` (existing tool) | Pacman wrapper, changes apply on next reboot | **Backend for pacman** (section 9.2). |

Changes in v2: `~/Applications` is AppImage-only; AppImage operations go through the launcher's D-Bus API (not an `app` CLI); catalog provenance via `origin`; update-authority rules; the wizards are part of this project (section 10.9, Phase 7).

---

## 0. Rules for the agent

1. Work phase by phase (section 12). Finish a phase, run the checks, report, then stop. Do not start the next phase unprompted.
2. **Three layers, strict direction:** `core` (pure Python, no Qt) <- `services`/`backends` (Qt allowed only in `services/qt_*.py`) <- `ui` and `wizards`. `core` must never import PyQt6. Tests for `core` run without Qt installed.
3. The UI thread never blocks: no `subprocess.run`, no `urllib`, no heavy file work on it. Everything slow runs in a worker, a `QProcess`, a `QNetworkAccessManager` request, or an asynchronous QtDBus call.
4. **This application never writes to `~/Applications`, the launcher's state, or the launcher's desktop entries.** All AppImage changes go through the `Manager1` D-Bus API. The only files this app creates are in its own cache and config directories.
5. Never use `shell=True`. Every external command is an argument list. Never execute a downloaded file (the wizard's explicit "Just run" action is the only exception, section 10.9).
6. Runtime dependencies: Python 3.11+, PyQt6 (including `QtDBus`), and the standard library. Anything else needs an entry in section 15 and the owner's approval. Dev dependencies: `pytest`, `pytest-qt`, `ruff`.
7. Use fully qualified PyQt6 enums (`Qt.AlignmentFlag.AlignCenter`).
8. Tests never touch the network, `pacman`, `flatpak`, the session bus of the developer, or the real home directory. Use fixtures and fakes (section 13).
9. If this spec conflicts with what you find, or a contract in section 9 is missing on the other side, stop and ask. Do not invent behaviour for `Manager1` or `pkg`.
10. Small commits, conventional messages (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`). `./check` must pass before each commit.
11. **Minimal scope.** Do only what the current phase lists. No extra features, abstractions or infrastructure beyond what this spec requires. Do not refactor unrelated code.
12. **Never game the checks.** No new ruff/mypy ignores, no skipped/xfailed/deleted tests, no weakened assertions, no mypy `exclude` for your own code. Fix the code, or stop and ask.
13. **Tests must be able to fail.** Each task needs a test that fails without the feature. No `pass` bodies, no "verified manually", no tests that only check a type or constant exists. Use real files and real Qt objects (pytest-qt) in preference to mocks. Do not call internal handlers by hand to simulate real events.
14. **Wire it in.** Every new class or function must be reachable from `main` (or the dev CLI). In the phase report, show the call path from the entry point to each new component. Code with tests but no caller is not done.
15. **Assert contracts exactly.** Where this spec names an identifier (D-Bus error, signal, field, config key, exit code), tests assert it exactly.
16. **Run it and report it.** Run `./check` and paste the real output. Do not claim results you did not see. List what is NOT done, what you could not verify, and any bug you found but did not fix. Never describe a stub or skipped code as complete.
17. **One task at a time**, in the order of the phase list. If a task turns out to be bigger or different than described, stop and ask.
18. **No silent failure.** No bare `except: pass`; no TODO standing in for a requirement. Log or raise with a reason.

---

## 1. Product

A GNOME-Software-style application center for Aurelis, an **immutable Arch Linux** distribution. One window, three software sources, plus two small wizards.

| Section | Source | Install / remove mechanism | Updates |
|---|---|---|---|
| **AppImage** | The Aurelis catalog `apps.db` (curated GitHub AppImages) | `appimage-launcher` daemon over D-Bus | Per app, catalog-driven (zsync delta when possible, else full download) |
| **Flathub** | Flathub remote (user installation) | `flatpak` CLI, `--user` | Flatpak updates |
| **Pacman** | Arch repositories | `pkg` wrapper (changes apply **on next reboot**) | Staged through `pkg` |

Cross-source views: **Explore**, **Installed**, **Updates**.
Wizards (entry points of the same program): **install wizard** (double-click on an AppImage or Flatpak file) and **uninstall wizard** (Dolphin custom action).

Goals:
- A non-technical user can find, install, update and remove software without a terminal.
- Honest about trust: shows who packaged an AppImage, its license, and whether the download is checksum-verified.
- Works offline from the last good catalog.
- Never leaves the system half-installed: every operation is atomic or rolls back.
- **Coexists with the folder.** Users also drop, delete and launch AppImages directly in `~/Applications`. The GUI reflects those changes live and never fights them (section 7.6).

Non-goals (v1): reviews or ratings, telemetry, system services, repository management, writing to `~/Applications`, replacing the launcher's own notifications for folder-originated events.

---

## 2. Context the agent must know

### 2.1 Platform and the `~/Applications` decision
- Aurelis is immutable. System software is read-only; user-level software lives in `$HOME`.
- **`~/Applications` contains AppImage files only**: one file per app with a clean name (for example `Kate`), managed by the `appimage-launcher` daemon (separate repository). Dropping a file installs it, deleting or Trashing it uninstalls it (the app's menu entry and icon; the file is untouched by observer-triggered uninstall). Desktop entries and icons go to `~/.local/share/applications` and `~/.local/share/icons`, written by the daemon.
- Flatpak and pacman applications are **not** in `~/Applications`. They appear in the application menu and in this app's **Installed** page. The Installed page is the unified view across all sources.
- Desktop: KDE Plasma 6 (Dolphin). Follow system theme, icons and fonts; no custom stylesheet for basics.

### 2.2 The catalog (`apps.db`, schema_version 1)
Built weekly by `aurelis-software-database`, published as the GitHub release `latest`. Two assets:
- `apps.db.tar.gz` -> contains `apps.db` (JSON)
- `app-icons.tar.gz` -> contains `<id>.png` files

URLs (configurable, see 15.1):
```
https://github.com/aurelis-os/aurelis-software-database/releases/download/latest/apps.db.tar.gz
https://github.com/aurelis-os/aurelis-software-database/releases/download/latest/app-icons.tar.gz
```

Envelope:
```json
{ "schema_version": 1, "generated_at": "2026-11-13T05:00:00Z", "count": 22, "apps": [ ... ] }
```

Entry fields the GUI uses (all others are ignored but kept in `App.raw`):

| Field | Type | Req. | Use in GUI |
|---|---|---|---|
| `id` | string | yes | Identity. Flathub-style id. Unique. Becomes `origin.catalog_id`. |
| `name` | string | yes | Title |
| `summary` | string | yes | One-line subtitle in cards |
| `description` | string | no | Detail page. Paragraphs separated by `\n`. |
| `repo` | `owner/name` | yes | "Packaged by `owner`" trust line, link to GitHub |
| `version` | string | yes | Shown; compared **by inequality only**, never ordered |
| `version_changed_at` | ISO-8601 UTC | yes | "Recently updated" sort and badge; `origin.changed_at` |
| `download_url` | https URL | yes | Install source |
| `size` | int bytes | no | Shown on Install button, free-space check |
| `sha256` | 64 hex | no | Mandatory verification when present |
| `zsync_url` | https URL | no | Delta update when present |
| `arch` | string or null | yes (may be null) | Compatibility filter |
| `developer` | string or null | no | Hidden when empty |
| `license` | SPDX string or null | no | License badge; `LicenseRef-proprietary*` -> "Proprietary" |
| `categories` | string[] | no | Mapped to store categories (Appendix B) |
| `keywords` | string[] | no | Search only |
| `urls` | object | no | Links row (Appendix C) |
| `icon` | `{type, name}` | yes | `name` is a file in the icons archive |
| `screenshots` | object[] | no | Detail carousel; sizes are ints; exactly one `default` |
| `i18n` | object | no | **Optional, future**: `{lang: {name, summary, keywords}}`. Use if present for the current locale. |

Tolerance rules (the DB evolves, the GUI must not break):
- Unknown fields: ignore. Missing optional fields: hide the UI element.
- `schema_version` higher than supported: refuse to load a *new* DB, keep the cached one, show a non-blocking "Update Aurelis Software to see the latest catalog" banner.
- An entry that fails basic checks (no `id`/`name`/`download_url`): skip it, log it, continue.

### 2.3 External tools and their status

| Tool | Status | Contract |
|---|---|---|
| `appimage-launcher` daemon | separate repo, spec v1.1 (API frozen in its Phase 3B) | D-Bus `Manager1` (section 9.1). Until then: a fake built from that section. |
| `appimage` CLI | part of the launcher | Used only for `appimage run <name>` (launch). Everything else via D-Bus. |
| `flatpak` | exists | Standard CLI (8.2) |
| `pacman` (read-only queries) | exists | Standard CLI (8.3) |
| `pkg` | **implemented, tested**; add/remove apply on next reboot | Interface contract needed (9.2) |
| `zsync` | optional | Feature-detected. Used by this app for catalog delta updates (the catalog's `zsync_url`). Not the same as the launcher's `appimageupdatetool`, which uses the AppImage's embedded update info. |

---

## 3. Architecture

### 3.1 Layers

```
 ui/ , wizards/   Widgets, models, delegates, dialogs, wizard pages. No business logic.
   |  signals / slots
 services/        SourceManager, OperationQueue, DatabaseUpdater, Downloader, workers.
   |              Qt glue: qt_dbus.py (QtDBus), qt_process.py (QProcess).
 backends/        One class per source implementing the Backend interface.
   |              AppImageBackend (D-Bus), FlatpakBackend, PacmanBackend (+ Fake*)
 core/            Pure Python: models, catalog parsing, normalisation, search, categories,
                  update logic, matching, config, paths, errors.  (no Qt, no subprocess)
```

### 3.2 Repository layout

```
aurelis-software/
  pyproject.toml
  README.md
  spec.md                     (this file)
  check                       lint + tests
  docs/
    contracts/
      manager1.xml            copy of the launcher's published introspection (contract)
      manager1-notes.md       what this app relies on (section 9.1)
      pkg-adapter.md          written in Phase 0/6 with the owner
    spikes/
  src/aurelis_software/
    __main__.py               entry point: GUI, `wizard install|uninstall`, `--open`, `--search`
    app.py                    QApplication setup, wiring, single instance
    core/
      models.py  catalog.py  search.py  categories.py  textfmt.py  versions.py
      matching.py             installed <-> catalog matching and origin building
      config.py  paths.py  errors.py  archive.py
    backends/
      base.py                 Backend ABC, OperationEvent types
      appimage.py             D-Bus client for Manager1
      flatpak.py              flatpak CLI
      pacman.py               pacman (queries) + pkg (changes)
      fake.py                 deterministic in-memory backends for tests/dev
    services/
      db_updater.py           ETag fetch, verify, extract, atomic swap
      downloader.py           resumable download + sha256 (QNetworkAccessManager)
      operations.py           OperationQueue, Operation state machine
      qt_dbus.py              async QtDBus wrapper (calls, signals, activation)
      qt_process.py           QProcess wrapper yielding OperationEvents
      settings_store.py
    ui/
      main_window.py  sidebar.py  app_list_view.py  app_model.py  app_card_delegate.py
      detail_page.py  screenshot_carousel.py  installed_page.py  updates_page.py
      settings_dialog.py  progress_widgets.py  banners.py  conflict_dialog.py
      icons.py  theme.py
    wizards/
      install_wizard.py       double-click wizard (10.9)
      uninstall_wizard.py     uninstall wizard (10.9)
      detect.py               what kind of thing is this file/desktop entry (pure logic in core where possible)
    resources/
      aurelis-software.desktop
      aurelis-software-wizard-install.desktop     (MIME handler, NoDisplay)
      aurelis-software-uninstall.desktop          (Dolphin service menu)
      icons/
  tests/
    core/  backends/  services/  ui/  wizards/  contract/
    fixtures/
      apps.db  icons/  flathub_appstream.xml  pacman/  flatpak/  manager1/ (JSON samples)
  packaging/
    PKGBUILD
```

### 3.3 Principles
- **One `App` model for every source**, with `source` and a `raw` dict for source-specific data. The UI renders `App`; it never branches on the catalog format.
- **The backend interface is the only thing the UI knows about installs.** Adding a source means adding a backend.
- **Event streams, not return values, for long operations** (`Started`, `Progress`, `Finished`, `Failed`).
- **State is derived, not stored.** Installed and update state come from asking the backend (`list_installed`), never from a GUI-owned file. The launcher's folder and state are the source of truth for AppImages.
- **Single writer.** For AppImages the daemon is the only writer. The GUI is one of several front-ends (folder, CLI, wizards, GUI).
- **Offline-first.** Every screen works from cache. Network features degrade with a calm message.
- **Deterministic and testable.** Time, filesystem roots, command runners and the D-Bus connection are injected.

### 3.4 Threading model
- Main thread: widgets only.
- Workers: catalog load/parse, search index build, hashing (if the GUI must hash), index builds for Flathub/pacman.
- `QProcess`: `flatpak`, `pacman`, `pkg`, `zsync`, `appimage run`.
- QtDBus: asynchronous calls (`QDBusPendingCall` + watcher) and signal subscriptions. **Never use blocking D-Bus calls on the UI thread.**
- Downloads: `QNetworkAccessManager`.
- Rule: one active **mutating** operation per backend at a time (FIFO). Reads run in parallel.
- Cancellation: possible while the GUI-owned download is running (it deletes its `.part`). Once an AppImage has been handed to the daemon (`Install`), the call is short and atomic and is **not cancellable**; the UI disables Cancel at that point and says "Finishing…".

---

## 4. Core domain

### 4.1 Models (`core/models.py`)

```python
class Source(StrEnum):
    APPIMAGE = "appimage"
    FLATPAK = "flatpak"
    PACMAN = "pacman"


@dataclass(slots=True)
class App:  # a catalog / index entry
    key: str  # f"{source}:{id}"
    id: str
    source: Source
    name: str
    summary: str
    version: str | None
    categories: tuple[str, ...]
    store_categories: tuple[str, ...]
    search_blob: str
    raw: dict

    def get(self, k, default=None): ...


@dataclass(slots=True)
class InstalledApp:  # something present on this system
    id: str  # AppImage: the launcher's app_id; others: their ids
    source: Source
    name: str
    version: str | None
    managed_name: str | None  # AppImage: file name in ~/Applications
    path: str | None  # AppImage: file path
    role: str  # "primary" | "kept"
    sha256: str | None  # AppImage: full-file hash if the daemon has it
    update_policy: str | None  # AppImage: auto | manual | pinned
    self_managed: bool  # AppImage: app updates itself
    origin: dict | None  # AppImage: provenance record (catalog link)
    locked: bool  # system package, cannot be removed
    pending: str | None  # "install" | "remove" | None (pacman via pkg)
    previous: tuple[dict, ...]  # AppImage: revertible versions


@dataclass(slots=True)
class UpdateInfo:
    app_key: str
    installed_version: str | None
    new_version: str | None
    size: int | None
    method: str  # "zsync" | "full" | "flatpak" | "pkg"
```

### 4.2 Catalog parsing (`core/catalog.py`)
- `load_catalog(path) -> CatalogResult(apps, skipped, schema_version, generated_at)`.
- `json.load` in a worker is fine at 500 apps (tens of ms).
- Dynamic fields: promote only what the UI queries; keep everything else in `raw`.
- Normalise defensively even though the DB builder already normalises: strip strings, coerce numeric strings to int for screenshot sizes, ignore malformed screenshots.
- Dedupe by `id` (keep the first), log duplicates.

### 4.3 Search (`core/search.py`)
- Build once per catalog load. Fold: `casefold()` + Unicode NFKD, strip combining marks (Greek search works without tonos, `é` matches `e`).
- Fields kept separate for ranking: name, keywords, summary, description (tail).
- Ranking (highest first): exact name, name prefix, name word prefix, name contains, keyword hit, summary contains, description contains. Ties: shorter name, then name.
- Query tokens are ANDed. Empty query = no filter.
- Budget: < 50 ms for 500 apps. Substring scan is sufficient. **No FTS for the AppImage catalog.** For Flathub and pacman see 8.2/8.3.

### 4.4 Categories (`core/categories.py`)
Ordered table, first match wins, defined in Appendix B. Unknown raw categories ignored. An app can belong to several store categories.

### 4.5 Update logic (`core/versions.py`)
Versions are **never ordered**. For an installed AppImage that is linked to a catalog entry through its `origin`:

```
update_available(entry, inst) =
    inst.origin is not None
    and inst.origin.catalog_id == entry.id
    and inst.update_policy != "pinned"
    and not (inst.self_managed and not settings.include_self_managed)
    and (   entry.version != inst.origin.version
         or (entry.sha256 and inst.origin.sha256 and entry.sha256 != inst.origin.sha256)
         or (entry.version == "latest" and entry.version_changed_at > inst.origin.changed_at))
```

Policy handling:
- `auto`: appears in Updates and in **Update all**.
- `manual`: appears in Updates with its own **Update** button, but is excluded from **Update all** and from update notifications (the user said "never start updates for me").
- `pinned`: never shown as updatable.
- `self_managed` apps (they update themselves): excluded unless the user turns on "Include self-updating apps" in Settings.

Flatpak and pacman updates come from their own backends (8.2, 8.3).

### 4.6 Matching installed apps to catalog entries (`core/matching.py`)
Applied to every installed AppImage, in order:
1. `origin.catalog_id` present -> linked to that entry. Done.
2. Full `sha256` equals a catalog entry's `sha256` (the installed file is byte-identical to a catalog release) -> **auto-link**: build an origin (below) and call `SetOrigin` silently. Logged. High confidence, no prompt.
3. `app_id == entry.id` but no hash match (an older version, or a different build) -> **suggest**: show "This looks like <entry name> from the catalog. Manage updates with Aurelis Software?" with a button. On confirm, call `SetOrigin` with `version` = the installed version and no `sha256`.
4. Otherwise **unmanaged**: shown as installed, no updates, can be removed and opened.

Hashes: the GUI asks the daemon for them (`List({hash:true})` in a background call after the first list; the daemon caches by inode and mtime). The GUI never hashes files in `~/Applications` itself.

Origin built by the GUI (omit null values):
```json
{ "source": "aurelis-catalog", "catalog_id": "<entry.id>", "version": "<entry.version>",
  "sha256": "<entry.sha256>", "changed_at": "<entry.version_changed_at>", "url": "<entry.download_url>" }
```

### 4.7 Config and paths
XDG-based, injected (never hard-coded in logic):

| Purpose | Path |
|---|---|
| Config | `$XDG_CONFIG_HOME/aurelis-software/config.toml` |
| Cache (catalog, icons, downloads, screenshots, indexes) | `$XDG_CACHE_HOME/aurelis-software/` |
| State / logs | `$XDG_STATE_HOME/aurelis-software/` |

Config keys: `catalog.apps_url`, `catalog.icons_url`, `catalog.refresh_hours` (24), `ui.language` (system), `ui.show_proprietary` (true), `ui.hide_incompatible` (true), `network.offline` (false), `flathub.enabled`, `pacman.enabled`, `updates.include_self_managed` (false), `downloads.allow_unverified` (`ask`), `wizard.run_without_asking` (list of `{app_id, sha256}`, default empty; manageable in Settings). Parsed with `tomllib` (read) and a tiny writer. Unknown keys preserved.

---

## 5. Catalog client (`services/db_updater.py`)

Downloads, verifies, extracts and atomically publishes the catalog and icons. Never leaves the cache in a broken state.

1. On startup load the cached catalog instantly (if any) and show the UI.
2. In the background, if `now - last_check > refresh_hours` or the user pressed Refresh: conditional `GET` of `apps.db.tar.gz` with `If-None-Match` (ETag) and `If-Modified-Since`.
3. `304` -> update `last_check`, done.
4. `200` -> write to `apps.db.tar.gz.part`, **safe extract** into a temp dir, parse and validate (`load_catalog`). Only on success: `os.replace` to `catalog/apps.db`, store ETag and `generated_at`. Keep the previous version as `apps.db.prev`.
5. Same for `app-icons.tar.gz`, only if the catalog changed. Extract only files matching `^[A-Za-z0-9._-]+\.png$`, each at most 2 MB, total at most 200 MB. Replace the icon directory atomically (build in `icons.new/`, swap).
6. Failure at any step: keep the current cache, log, show a calm banner ("Could not refresh the catalog. Showing the last saved version from <date>."). Never an error dialog.

Safe extraction (`core/archive.py`): reject absolute paths, `..`, symlinks, hard links, devices; allow only expected member names (`apps.db`; or `*.png`); enforce size limits; never use `tarfile.extractall` without a filter (`filter="data"` on 3.12+, manual checks on 3.11).
Downgrade protection: if the new `generated_at` is older than the cached one, ignore it.
Telemetry: none. The only requests are the two release downloads, screenshots, and downloads the user starts.

---

## 6. Backend interface (`backends/base.py`)

```python
class Backend(ABC):
    source: Source
    available: bool                      # tool/daemon present and usable
    def capabilities(self) -> Capabilities
    def list_installed(self) -> list[InstalledApp]            # async in practice (worker / D-Bus call)
    def list_updates(self) -> list[UpdateInfo]
    def install(self, app: App, **opts) -> Operation
    def remove(self, installed: InstalledApp) -> Operation
    def update(self, app: App, installed: InstalledApp) -> Operation
    def open(self, installed: InstalledApp) -> None           # launch
    # optional per backend:
    def revert(self, installed) -> Operation                  # AppImage
    def set_policy(self, installed, policy) -> None           # AppImage
    def set_origin(self, installed, origin: dict | None) -> None  # AppImage
```

`Operation`: QObject with signals `event(OperationEvent)`, `finished(OperationResult)`, and `cancel()`. A fake implementation drives the same signals from a script, so every UI state is testable.

Error taxonomy (`core/errors.py`): `NetworkError`, `ChecksumMismatch`, `DiskFull`, `PermissionDenied`, `ToolMissing`, `DaemonUnavailable`, `ApiTooOld`, `ToolFailed(exit_code, stderr_tail)`, `Cancelled`, `Incompatible(arch)`, `Locked`, `PendingReboot`, `ConflictPending(payload)`, `Busy`. Each maps to one user message and one "Details" text.

---

## 7. Operation flow and app state machine

### 7.1 Button states (detail page and card)

| State | Condition | Primary action | Secondary |
|---|---|---|---|
| NotInstalled | not installed, compatible | **Install** (shows size) | |
| Incompatible | `arch` set and != host arch | disabled "Not available for <host arch>" | |
| Installing | operation running | progress bar + Cancel (until handed to the daemon) | |
| Installed | installed, no update | **Open** | Remove |
| UpdateAvailable | update exists (4.5) | **Update** | Open, Remove |
| Updating | operation running | progress + Cancel (until handed to the daemon) | |
| Removing | operation running | spinner | |
| Failed | last op failed | **Retry** | Details |
| Locked | system package | disabled "Part of the system" | |
| PendingInstall / PendingRemove | pacman via `pkg`, applied on reboot | "Will be installed/removed after restart" | Undo (if `pkg` supports it) |
| Unmanaged | AppImage installed outside the catalog (4.6 rule 4) | **Open** | Remove, "Link to catalog" (if rule 3 suggests it) |

Host architecture comes from `platform.machine()` normalised to the catalog vocabulary (`x86_64`, `aarch64`, `armv7l`, `i686`). `arch: null` is treated as compatible but shows "Architecture not specified".

### 7.2 AppImage install (the GUI's responsibility)
1. Pre-checks: `Manager1` reachable (D-Bus activation starts the daemon) and capabilities present (9.1); free space in cache and home >= 2x `size` (if known); no running operation for this app.
2. Download `download_url` to `cache/downloads/<id>-<version>.AppImage.part` via the Downloader (7.4). **Never into `~/Applications`** (the observer would treat it as a user drop).
3. Verify `sha256` if present. Mismatch -> delete file, `ChecksumMismatch`. If absent: proceed only after the "no checksum" confirmation (setting `downloads.allow_unverified`, default `ask`), see 11.
4. Rename `.part` to its final name, then call `Install(path, options)` with:
   `source_action="move"`, `conflict="error"`, `silent=true`, `origin=<origin JSON, 4.6>`.
5. If the daemon raises `ConflictPending` (the user already has this app, for instance dropped by hand): show the in-GUI **conflict dialog** (old version -> new version, upgrade / downgrade / same, choices *Replace*, *Keep both*, *Cancel*), then call `Install` again with `conflict="replace" | "keep" | "cancel"`. No daemon notification appears, because of `conflict=error` and `silent`.
6. On success: the daemon returns `{app, changed, previous}`; refresh `list_installed()`; toast "Kate installed. Find it in your Applications." (offers **Open** and **Show in folder**). If `changed=false` (identical file already installed): toast "Already installed", and link the origin if missing.
7. On any failure: delete the cache file, report. The daemon rolls back its own partial work.
8. The cache file is deleted after `move` (it no longer exists) or after a failed `Install`. The cache directory is cleaned of stale `.part` files at startup.

### 7.3 AppImage remove
Confirmation dialog (name; "Your settings and data are kept"; "The program file is moved to the Trash"), then `Remove(name, {file_action: "trash", silent: true})`. If the user deletes the file in Dolphin instead, the daemon uninstalls the entry and the GUI follows through the `AppsChanged` signal (7.6). The GUI never deletes files itself.

### 7.4 Downloader (`services/downloader.py`)
- `QNetworkAccessManager`, `RedirectPolicy.NoLessSafeRedirectPolicy` (https only, no downgrade).
- Resumable: if `.part` exists and the server answers `206` to `Range`, continue; else restart.
- Emits `progress(received, total)`, `finished(path)`, `failed(NetworkError)`.
- Timeouts: connect 15 s, stall 30 s without bytes.
- Computes sha256 incrementally while writing.
- Never sends credentials or custom tokens.

### 7.5 AppImage update
Triggered by the user (Update, Update all). **The GUI never updates AppImages silently in the background in v1.**
1. Obtain the new file: if the entry has `zsync_url` and `zsync` is installed and the installed file path is known, run `zsync -i <installed path> -o <cache/new.part> <zsync_url>` (delta against the installed file); otherwise a full download (7.4). Verify `sha256` when present.
2. Call `Install(newfile, {source_action: "move", conflict: "replace", silent: true, origin: <new origin>})`. The daemon's **Replace operation** keeps the user-chosen name, moves the old file to `.previous`, swaps atomically and updates the entry. This is explicit, so it is not treated as a self-update.
3. Success toast with **Undo**, which calls `Revert(name)` (available as long as the daemon keeps the previous copy).
4. Failure at any point leaves the previous version installed and working.
5. "Update all" runs the `auto` updates sequentially in the queue; one failure does not stop the rest; a summary dialog lists results.

### 7.6 Two front doors: folder and GUI

Users act in `~/Applications` and in the GUI. The daemon is the single writer; the GUI follows.

| User action | Where | What happens | GUI reaction |
|---|---|---|---|
| Drops an AppImage in the folder | Dolphin | Daemon installs (name, entry, icon) and notifies | `AppsChanged(installed, source=observer)` -> refresh; match to catalog (4.6); new row in Installed |
| Deletes or Trashes it | Dolphin | Daemon removes entry and icon (file untouched), notifies | `AppsChanged(removed, observer)` -> row disappears; state returns to NotInstalled |
| Renames it | Dolphin | Daemon updates the entry, name becomes user-chosen | `AppsChanged(renamed)` -> row shows the new name |
| Clicks Install | GUI | Download, verify, `Install` (7.2) | Own progress and toast; the daemon stays silent |
| Clicks Remove | GUI | `Remove(file_action=trash)` | Own toast |
| Clicks Update | GUI | 7.5 | Own toast with Undo |
| An app updates itself | App | Daemon detects it (self-update flow) | `AppsChanged(updated, observer)` and `self_managed` set -> excluded from catalog updates (4.5) |
| Daemon not running | | D-Bus activation starts it | If it still fails: banner, Install disabled |

Rules:
- Refresh on `AppsChanged` is debounced (300 ms) and incremental: re-fetch `List`, diff, update the model.
- When the signal's `source` is `api` and the change came from this process's own operation, do not show a second toast.
- Races (the user drops the same app while the GUI installs it): the daemon serializes; a `Busy` error is retried once after 1 s; a `ConflictPending` goes to the conflict dialog.
- A **Rescan** button on the Installed page calls `Reindex()` (useful after copying files while the daemon was stopped).

---

## 8. Sources

### 8.1 AppImage section
- Browse: from the catalog (sections 2.2 and 4).
- Installed: `List({all: true})` over D-Bus, then `List({hash: true})` in the background for matching (4.6). Live updates through `AppsChanged`.
- Updates: 4.5, computed in `core` from catalog + installed list. No network beyond the catalog.
- Startup checks: `Manager1` reachable, `APIVersion >= 1`, capabilities `inspect`, `origin`, `install-options-v1`, `conflict-error`, `remove-file-action`, `list-hash` all present. Otherwise the AppImage section stays browsable, Install/Update/Remove are disabled, and a banner explains ("Update appimage-launcher" or "The AppImage service is not running").
- Optional tools: `zsync` (delta updates) is feature-detected.
- After each catalog refresh recompute updates and update the **Updates** badge. Optional desktop notification when the count increases (setting, default off; excludes `manual`, `pinned`, `self_managed`).
- **Open** launches with `appimage run <managed_name>` (`QProcess.startDetached`).

### 8.2 Flathub section

**Data source: the local Flatpak AppStream metadata**, not the web API. It works offline and matches what `flatpak install` can actually install.
- Path: `$HOME/.local/share/flatpak/appstream/flathub/<arch>/active/appstream.xml.gz` (user installation) with the system one as fallback. Refresh with `flatpak update --appstream --user` (a background operation offered in the UI).
- Parse once into a **SQLite index** (`cache/flathub.sqlite`, stdlib `sqlite3`, FTS5 table for name/summary/keywords). Rebuild only when the XML's mtime changes. First-run parsing happens in a worker with a progress indicator.
- Base index uses untranslated fields; use `xml:lang` variants for the current locale when present (they live on the `<keywords>`, `<name>`, `<summary>` blocks).
- Browse lists use the FTS index with pagination (`LIMIT/OFFSET`), never loading thousands of `App` objects.
- Icons: AppStream `cached` icons under `.../active/icons/<size>/`, generic fallback.
- Installed: `flatpak list --user --app --columns=application,version,origin`.
- Updates: `flatpak remote-ls --user --updates --app --columns=application,version`.
- Install: `flatpak install --user --noninteractive -y flathub <app-id>`. Remove: `flatpak uninstall --user --noninteractive -y <app-id>`. Update: `flatpak update --user --noninteractive -y <app-id>`.
- **Progress**: the Flatpak CLI prints rich progress only on a TTY. Phase 0 spike decides between (a) parsing non-TTY output (coarse), (b) a pseudo-terminal, (c) `libflatpak` through PyGObject. Default plan: (a) with an indeterminate bar (decision 15.4).
- User installation only. If there is no user remote, offer to add Flathub (`flatpak remote-add --user --if-not-exists flathub <flatpakrepo>`).

### 8.3 Pacman section

Constraint: Aurelis is immutable. **Package changes go only through `pkg`, which stages them for the next reboot.** The GUI must make that unmistakable. Detailed manual for pkg docs/how-pkg-works.md

- Browse/search (read only, no root): SQLite index from `pacman -Si` output (all repos), rebuilt when the sync database mtimes change (`/var/lib/pacman/sync/*.db`). Index name, version, description, repo, groups, sizes, URL, license, depends. FTS5 on name + description. Lazy detail via `pacman -Si <name>`.
- Installed: `pacman -Qq` / `pacman -Qi`. `/usr/lib/aurelis/core-packages.json` (system, **locked**) and `/var/lib/aurelis/user-packages.json` (user-installed) classify them. Locked packages show a lock and cannot be removed. Dependencies of user packages appear only with "Show dependencies".
- Updates: through `pkg` (9.2). Never run `pacman -Sy` from the GUI (partial upgrades).
- add/remove: `pkg` (9.2). After success the UI shows the **pending-reboot banner** and marks the package Pending. The banner persists across GUI restarts by asking `pkg` for pending changes, never from a GUI-owned file.
- Dangerous removals: warn when removing a package that other user packages depend on (reverse deps from `pacman -Qi` "Required By").
- Large lists: paginated model (6, 10.2), never the in-memory `App` list.

---

## 9. External contracts

### 9.1 `appimage-launcher` `Manager1` (consumed)

The authoritative description is the launcher repository's published introspection XML and `docs/API.md` (its spec section 8.1). This repo keeps a copy at `docs/contracts/manager1.xml` and a note `manager1-notes.md` listing what is relied on. Until the real daemon passes the launcher's contract suite (its Phase 3B, tag `api-v1`), develop against a fake built from the launcher spec.

Connection: session bus, service name `io.github.appimage_launcher.Manager` (from launcher's constants.py), object `/io/github/appimage_launcher/Manager`, interface `io.github.appimage_launcher.Manager1`. Use `QtDBus` asynchronously. Bus activation starts the daemon on first call.

Calls the GUI and wizards use:

| Call | Used for | Notes |
|---|---|---|
| property `APIVersion`, `Capabilities` | startup check | Require version >= 1 and the capabilities listed in 8.1 |
| `List({all, hash})` | Installed page, matching | `hash:true` only in a low-priority background call |
| `Info(name)` | detail of one app | includes `sha256` |
| `Inspect(path)` | wizards (name, icon, version, relation to installed) | never executes the file |
| `Install(path, options)` | install, update, wizard install | options: `source_action=move`, `conflict=error` then explicit retry, `silent=true`, `origin` |
| `Remove(name, options)` | remove | `file_action=trash`, `silent=true` |
| `Revert(name)` | Undo after an update, "Revert" on Installed | |
| `SetPolicy(name, policy)` | per-app update policy control | `auto`, `manual`, `pinned` |
| `SetOrigin(name, json)` | auto-link and "Link to catalog"; empty string unlinks | |
| `Reindex()` | Rescan button | |
| signal `AppsChanged(kind, app_id, source)` | live refresh | ignore unknown kinds |

Errors handled (`...Error.<Name>`): `NotFound`, `Ambiguous`, `NameCollision`, `ConflictPending` (payload with old/new meta and `relation`), `InvalidAppImage`, `UnsupportedType`, `InvalidArgument`, `PolicyForbids`, `Busy`, `Io`, `Aborted`. Each maps to a user message (6).

What the GUI must **not** do: write into `~/Applications`, read or write the launcher's SQLite file, edit its desktop entries, or call `Remove` with `file_action=purge`.

Contract test in this repo (`tests/contract/`): parse `docs/contracts/manager1.xml` and assert that every method, option name, property and signal used by `backends/appimage.py` exists with the right signature. A second, optional suite (`-m real_daemon`, skipped unless the launcher is installed) runs the same scenarios against the real daemon.

### 9.2 `pkg` (pacman wrapper): **needs confirmation from the owner**
Known: it wraps pacman and add/remove take effect on next reboot. Needed by the GUI (the agent must ask the owner before Phase 6 and must not guess):
- install / remove commands and exit codes,
- a machine-readable list of **pending** changes (install and remove),
- a way to cancel a pending change,
- whether it needs privileges (polkit/`pkexec`) and how the GUI should invoke it,
- how updates are staged (is there `pkg update`? what does it list?).

Answered by the user:

Commands:

pkg add PACKAGE... - Queue package installs (exit 0 on success, 1 on error)
pkg remove PACKAGE... - Queue package removals (exit 0 on success, 1 on error)
Machine-readable pending changes:

RPC method: pkg.queue returns {"queue": {"install": [...], "remove": [...]}}
Socket: 
aurelis-pkgd.sock
Cancel pending changes:

All: pkg queue clear
Single removal: pkg add PACKAGE (for installed packages)
Single install: pkg remove PACKAGE (for queued packages)
Privileges:

No polkit/pkexec - user must be in wheel group
GUI invokes directly as the user: /usr/bin/pkg add htop
Daemon socket is 0660 root:wheel
Updates:

No pkg update command - Arch packages update by the system not the user or software center.
pkg list shows installed user packages
pkg queue shows pending operations
pkg apply applies changes (normally automatic at boot)



Phase 6 starts with a short adapter spec written with the owner.

---

## 10. UI specification

### 10.1 Window and navigation
- `QMainWindow`: left **sidebar**, central **stacked pages**, top **search field**, **banner area**.
- Sidebar: **Explore**, **Installed**, **Updates** (numeric badge), separator, **AppImage**, **Flathub**, **Pacman** (each with a category sub-list), separator, **Settings**.
- Search is global to the current page. Enter opens a result. `Ctrl+F` focuses search, `Esc` clears, `Alt+Left` goes back.
- Window state persisted in config.

### 10.2 Lists
- `QListView` in icon-grid mode with `AppModel(QAbstractListModel)`, `QSortFilterProxyModel` and `AppCardDelegate`. **No per-app widget instances.** Flathub and pacman use a paginated model (`canFetchMore/fetchMore`).
- Card: icon (64 px), name, summary (2 lines), chips (source, "Proprietary", "Installed", "Update"). Hover shows Install/Open.
- Sorting: Relevance (when searching), Name, Recently updated (`version_changed_at`), Size.
- Icons lazy-loaded, `QPixmapCache`, theme fallback `application-x-executable`.
- Empty states with guidance (no results, offline with no cache, tool missing).
- Explore: "Recently updated" and per-category rows, then "All". A plain grid is enough in Phase 2; polish in Phase 8.

### 10.3 Detail page
Header: icon, name, summary, primary action (7.1), version, size.
Trust line (always visible for AppImage entries): **"Packaged by `<repo owner>` on GitHub"**, a link to the repo, license badge, verification note: "Checksum verified on install" (sha256 present) or "No checksum available" (warning). `developer` shown when present.
Body: screenshot carousel (default screenshot first, thumbnail closest to the view width), description (paragraphs from `\n`), links row (Appendix C). Keywords are not shown.
"Also available as": other sources with the same `id` (for example Flatpak) as buttons.
For an installed AppImage: policy selector (Automatic / Ask me / Pinned), "Revert to previous version" (if `previous` is non-empty), "Show in folder", and the catalog link state ("Managed by Aurelis Software" / "Not linked").
Unknown `urls` keys appear as title-cased labels.

### 10.4 Installed and Updates pages
- **Installed**: all sources in one list grouped by source, with a filter box. Rows show name, version, source, and tags: "Not linked" (AppImage unmanaged), "Updates itself" (`self_managed`), lock (system package), "Pending restart" (pacman). Actions per AppImage row: Open, Show in folder, Update policy, Revert, Remove, "Link to catalog" (if suggested). Kept versions (role `kept`) are listed under their app with a "Remove old version" action. **Rescan** button (7.6).
- **Updates**: grouped by source; checkboxes; **Update all** (respects policy, 4.5); per-row progress; result summary. Pacman updates show the pending-reboot note.

### 10.5 Progress and feedback
- Inline progress in card/detail; a global **operations tray** lists running and queued operations with Cancel (where allowed, 3.4).
- Success: non-modal toast. Failure: inline error with **Details** (stderr tail, log path, "Copy details"). Modal dialogs only for confirmations (remove, update all, unverified download) and the **conflict dialog** (7.2 step 5).
- Banners: offline, catalog refresh failed, schema too new, tool missing, launcher unavailable or too old, **pending reboot** (persistent while pending).

### 10.6 Settings dialog
Catalog refresh interval and "Refresh now", offline mode, language, show proprietary software, hide incompatible, include self-updating apps in Updates, allow unverified downloads (ask / never), enable Flathub / Pacman sections, **catalog URLs (advanced)**, "Always run without asking" list with Remove (from the install wizard), "Open log folder", "Clear cache" (with size). About box with version, catalog `generated_at` and count, launcher `Version` and `APIVersion`.

### 10.7 Look and accessibility
- System palette and font. Semantic badge colors only, in `theme.py`, with light and dark variants.
- Full keyboard navigation, visible focus, accessible names, no information by color alone.
- All user strings through `self.tr(...)` from day one. Greek translation delivered in Phase 8.

### 10.8 Single instance
`QLocalServer`/`QLocalSocket` per user. A second launch raises the first window and can pass a target: `aurelis-software --open org.kde.kate`, `--search kate`. Wizards are **separate lightweight processes** (they do not load the catalog or the main window).

### 10.9 Wizards

Both wizards are entry points of this program (`aurelis-software wizard install <path>`, `aurelis-software wizard uninstall <path-or-desktop-id>`), share the backends, and start fast (no catalog loading, no main window). Style: a small `QWizard`-like dialog with a slide-in second page.

**Install wizard** (MIME handler for AppImage files, `.flatpakref` and `.flatpak` bundles).

Routing rule (**important**): if the file is an AppImage that is already inside `~/Applications` (or `Inspect` reports it as the installed primary's path), the handler **just launches it** and shows no UI. Only files outside the folder get the wizard.

- Page 1: for AppImages call `Inspect(path)` (name, version, icon, `relation` to an installed version). Show: name and icon, version; if already installed: "Kate 26.08.1 is installed. This will update it to 26.08.2" (or downgrade / same-version wording). Controls: **Install**, **Just run** (AppImage only) with the checkbox "Don't ask again for this app", **Cancel**, **Next**.
- Page 2 (slide-in): "Installing…", spinner, then Done. Calls `Install(path, {source_action: "copy", conflict: "replace" when the user confirmed an update, silent: true})` for AppImages, or `flatpak install --user <file>` for Flatpak files. When done: tells the user where to find it ("Open it from your Applications folder or the menu; command line: `appimage run Kate`") and offers **Open**, **Close**.
- **Just run**: executes the file once without installing, an explicit user action (the only place where this program runs a file it did not build). If "Don't ask again" is ticked, store `{app_id, sha256}` in `wizard.run_without_asking`; the next double-click of the same app (same `app_id` and hash) runs it directly. The Settings dialog lists these entries so the user can undo the choice.
- Conflicts here use the same in-wizard confirmation as 7.2 step 5 (no daemon notification: `conflict` is passed explicitly).

**Uninstall wizard** (Dolphin custom action on an AppImage in `~/Applications`, or on a `.desktop` entry).

Detection order (`wizards/detect.py`, pure functions with injected readers):
1. The path is an AppImage inside `~/Applications` or a desktop entry with `X-AppImage-Managed=true` -> **AppImage** (find it through `List`).
2. The desktop entry lives under a Flatpak exports directory (`/var/lib/flatpak/exports/...` or `~/.local/share/flatpak/exports/...`) -> **Flatpak** (id from the file name).
3. `pacman -Qo <path>` returns a package -> **pacman**. If the package is listed in `/usr/lib/aurelis/core-packages.json` -> **system package**; if in `/var/lib/aurelis/user-packages.json` -> **user package**.
4. Otherwise: "Aurelis Software cannot remove this application" with Close.

- System package: tell the user it cannot be uninstalled; only **Close**.
- Page 1: name and icon, type ("AppImage", "Flatpak", "Arch package"), a confirmation message, **Next**, **Cancel**.
- Page 2 (slide-in): progress and spinner; call `Remove` (AppImage: `file_action=trash`), `flatpak uninstall`, or `pkg` remove. For user Arch packages say clearly "The change takes effect after restart". Done, **Close**.

Wizard tests are pure logic plus offscreen UI tests with the fake backends (Phase 7).

---

## 11. Security and trust

- **HTTPS only** for catalog, icons, screenshots and downloads. Redirects must not downgrade.
- **Checksum policy:** if `sha256` is present it is **mandatory**; a mismatch aborts and deletes the file. If absent, the GUI shows "No checksum available" and asks for confirmation once per install (`downloads.allow_unverified`).
- **Provenance is shown, not hidden**: "Packaged by <owner>" for every AppImage; proprietary software is labelled (the catalog contains community repackaging of proprietary apps).
- No shell, no `eval`, argument lists only. Ids and names passed to tools are validated against `^[A-Za-z0-9._+-]+$` first.
- D-Bus: session bus only. Paths passed to `Install` and `Inspect` are absolute, owned by the user, inside the cache directory or chosen by the user (double-click). `origin` JSON is built from catalog data and size-limited (the daemon also validates it).
- Safe archive extraction (section 5), size limits on every download, disk-space check before downloads.
- No elevated privileges in this process. Privileged actions only through `pkg` as agreed in 9.2.
- Logs never contain tokens. No telemetry. Screenshots are the only third-party requests, cached on disk, and can be disabled in Settings.
- Treat catalog content as untrusted text: render descriptions as **plain text**, open links with `QDesktopServices.openUrl` only for `https://` and only on user click.

---

## 12. Phases

Each phase ends with: acceptance criteria met, `./check` green, a short report (what was done, deviations, open questions). **Stop after each phase for the owner's review.**

### Phase 0: Contracts and spikes (about half a day)

- [ ] P0.1 Repo skeleton, `pyproject.toml` (PyQt6, dev deps), `check` script (ruff, pytest), CI workflow, README stub.
- [ ] P0.2 Copy a **real** `apps.db` (22 entries) and the icons archive into `tests/fixtures/`.
- [ ] P0.3 Copy the launcher's `Manager1` introspection XML (or, if it is not published yet, write `docs/contracts/manager1.xml` from the launcher spec section 8.1 and mark it "draft") and write `docs/contracts/manager1-notes.md` (section 9.1). List every call this app makes.
- [ ] P0.4 Ask the owner the `pkg` questions in 9.2 and record the answers in `docs/contracts/pkg-adapter.md`. Mark unanswered items as open.
- [ ] P0.5 Spike: Flatpak progress options (8.2). Capture output with and without a TTY for a small app and recommend (a), (b) or (c) in `docs/spikes/flatpak-progress.md`.
- [ ] P0.6 Spike: size and parse time of a full `pacman -Si` dump on the owner's machine; recommend the index strategy.
- [ ] P0.7 Confirm the catalog release URLs (the `aurelis-os` organization vs the current repository owner); make them configuration. Confirm the final D-Bus service name with the owner (decision 15.2).
- [ ] P0.8 Spike: QtDBus from PyQt6: async call, signal subscription, activation of a missing service, behaviour when the service disappears. Write findings in `docs/spikes/qtdbus.md`.

Done when: contract and spike documents exist and open questions are listed.

### Phase 1: Foundation and data layer (no UI)

- [ ] P1.1 `core/paths.py`, `core/config.py` (TOML load/save, defaults, unknown keys kept), `core/errors.py`.
- [ ] P1.2 `core/archive.py` safe extraction; tests for traversal, absolute paths, symlinks, oversized members.
- [ ] P1.3 `core/models.py`, `core/catalog.py` (4.2); tests: valid DB, unknown fields, missing optional fields, malformed entry skipped, duplicate ids, schema_version too new.
- [ ] P1.4 `core/search.py` (4.3): folding (Greek tonos, accents), ranking order, AND tokens, empty query. Benchmark test: 500 synthetic entries under 50 ms.
- [ ] P1.5 `core/categories.py`, `core/textfmt.py`: category table (Appendix B), URL labels (Appendix C), description to paragraphs.
- [ ] P1.6 `core/versions.py` (4.5) and `core/matching.py` (4.6): table-driven tests of every rule: policies, `latest`, equal versions with different sha256, self-managed, auto-link by hash, suggest by id, unmanaged, origin building.
- [ ] P1.7 `services/db_updater.py` (5) with a fake HTTP layer: 200, 304, corrupt archive, schema too new, older `generated_at`, partial download, icon swap atomicity (simulated crash between steps).
- [ ] P1.8 Dev CLI `python -m aurelis_software.cli`: `catalog refresh|list`, `search <q>`, `show <id>` (core and services only).
- [ ] P1.9 `backends/base.py`, `backends/fake.py`, `services/operations.py` (queue and state machine) with tests: FIFO, failure does not block the queue, cancel rules (3.4).

Acceptance: `python -m aurelis_software.cli search kate` works against the fixture; coverage of `core/` >= 90%; no PyQt6 import in `core/`.

### Phase 2: Shell and read-only Explore

- [ ] P2.1 `app.py`, `main_window.py`, `sidebar.py`, single instance, native look, `tr()` everywhere.
- [ ] P2.2 `AppModel` + proxy + `AppCardDelegate` + `AppListView` (10.2), lazy icons, fallback icon, sort modes.
- [ ] P2.3 Search wired to `core.search` (debounce 120 ms), category filter from the sidebar, empty states.
- [ ] P2.4 `DetailPage` (10.3) with trust line, license badge, links row, description, "Also available as" placeholder.
- [ ] P2.5 `ScreenshotCarousel` using `QNetworkAccessManager` + `QNetworkDiskCache`, thumbnail selection by width, graceful failure.
- [ ] P2.6 Background catalog refresh with banners; `Settings` dialog (catalog, language, advanced URLs).
- [ ] P2.7 Architecture filter (`hide_incompatible`).
- [ ] P2.8 pytest-qt tests: model roles, delegate with missing fields, detail page with and without optional fields, search updates the proxy.

Acceptance: cold start with cache shows the window in under 1 s; scrolling 500 cards smooth; no network on the UI thread (a test fails if sockets are used from the main thread); every optional field missing still renders.

### Phase 3: AppImage install and remove through the daemon, Installed page

Prerequisite for the final acceptance: the launcher's API v1 (Phase 3B, tag `api-v1`). Everything before the "real daemon" task works with the fake.

- [ ] P3.1 `services/downloader.py` (7.4): resume, incremental sha256, redirect policy, timeouts, free-space check. Tests with a local `http.server` for 200, 206, redirect, stall, mismatch.
- [ ] P3.2 `services/qt_dbus.py`: async calls, signal subscription with reconnect when the daemon restarts, activation, timeouts, mapping of D-Bus errors to `core/errors.py`.
- [ ] P3.3 `backends/appimage.py` over `qt_dbus` (9.1), plus `FakeManager1` (in-process, scripted) that reproduces `Install`, `Inspect`, `Remove`, `List`, `SetOrigin`, `Revert`, `ConflictPending`, `Busy` and `AppsChanged`. Contract test (9.1) parses the XML.
- [ ] P3.4 Operation UI: button state machine (7.1), progress in detail page and card, operations tray, Cancel rules, error dialog with Details, success toast.
- [ ] P3.5 Install flow (7.2) including the unverified-download confirmation and the in-GUI **conflict dialog**.
- [ ] P3.6 Remove flow (7.3).
- [ ] P3.7 Installed page for AppImages (10.4): live refresh from `AppsChanged` with debounce (7.6), tags, Open (`appimage run`), Show in folder, Rescan.
- [ ] P3.8 Matching in the UI (4.6): background `List({hash:true})`, silent auto-link, "Link to catalog" suggestion.
- [ ] P3.9 Failure-injection tests with the fake: download fails at 50%, checksum mismatch, `ConflictPending` then each decision, `Busy` retry, daemon vanishes mid-call, disk full. Each shows the right message and leaves no files in the cache.
- [ ] P3.10 Real-daemon integration run (marker `real_daemon`) once the launcher is tagged `api-v1`: the same scenarios against the installed daemon.

Acceptance: with the fake, install, remove, conflict resolution, cancel (before handoff) and retry work end to end; no `.part` or stray files after any failure; with the real daemon the integration suite passes; dropping or deleting a file in a test `~/Applications` is reflected in the GUI within 1 s. P3.10 must pass on real Aurelis, not only on the dev Arch.

### Phase 4: AppImage updates

- [ ] P4.1 Compute updates (4.5) after each catalog refresh and after `list_installed`; Updates badge.
- [ ] P4.2 `zsync` detection and delta update (7.5), fallback to full download.
- [ ] P4.3 Update flow through `Install(conflict="replace")` and **Undo** through `Revert` (7.5); failure leaves the old version.
- [ ] P4.4 Updates page, **Update all** honoring policy (4.5), summary dialog.
- [ ] P4.5 Policy control per app (`SetPolicy`), "Include self-updating apps" setting.
- [ ] P4.6 Optional notification when the update count increases (default off).

Acceptance: simulated catalog bump shows the badge; per-app update and Update all work; `manual`, `pinned` and `self_managed` apps behave as in 4.5; a failed update leaves the old version installed; Undo restores the previous file.

### Phase 5: Flathub section

- [ ] P5.1 AppStream parser to SQLite + FTS5 index (8.2) in a worker with progress; incremental rebuild by mtime; fixtures from a small real XML.
- [ ] P5.2 Paginated `FlathubModel`, search, categories, detail page reuse (`source=flatpak`).
- [ ] P5.3 `backends/flatpak.py`: list installed, list updates, install, remove, update via CLI, with command-runner injection and captured-output fixtures.
- [ ] P5.4 Progress approach per the Phase 0 spike; indeterminate fallback.
- [ ] P5.5 "Add Flathub remote" flow; "Refresh Flathub metadata" action.
- [ ] P5.6 Integrate Flathub into Installed, Updates and "Also available as".

Acceptance: browse and search thousands of apps without UI stalls; install, remove and update a real small Flatpak on the owner's machine; the section degrades cleanly if `flatpak` is missing.

### Phase 6: Pacman section (via `pkg`)

Prerequisite: the `pkg` contract (9.2). If still unknown, stop and ask.

- [ ] P6.1 Write the `pkg` adapter spec with the owner (`docs/contracts/pkg-adapter.md`).
- [ ] P6.2 Pacman index (8.3): `pacman -Si` parser, SQLite + FTS5, rebuild on sync DB mtime change; fixtures from captured output.
- [ ] P6.3 Installed packages: user vs core classification, lock icon, "Show dependencies".
- [ ] P6.4 `backends/pacman.py`: install/remove via `pkg`, pending state, reverse-dependency warning.
- [ ] P6.5 Pending-reboot banner and Pending states (7.1), restored on next launch from `pkg`'s own pending list.
- [ ] P6.6 Updates for pacman as staged through `pkg`; clear "applies after restart" text.
- [ ] P6.7 Failure tests: package not found, conflicts, locked package removal attempt, `pkg` missing.

Acceptance: install and remove a user package through the GUI, see it Pending, restart, see it applied; core packages can never be removed from the UI.

### Phase 7: Wizards

- [ ] P7.1 `wizards/detect.py` (10.9) as pure functions with injected readers; table-driven tests for every detection branch (AppImage in folder, managed desktop entry, Flatpak exports paths, pacman system vs user, unknown).
- [ ] P7.2 Install wizard: routing rule (inside `~/Applications` = just run, no UI), page 1 with `Inspect` data and relation wording, page 2 install flow, Flatpak file support, **Just run** with "Don't ask again" stored as `{app_id, sha256}`, Settings list to undo.
- [ ] P7.3 Uninstall wizard: system-package refusal, page 1 and 2, AppImage / Flatpak / user package flows, restart note.
- [ ] P7.4 MIME and desktop integration: `aurelis-software-wizard-install.desktop` (MIME handler for `application/vnd.appimage`, `application/vnd.flatpak.ref`, `application/vnd.flatpak`), Dolphin service-menu file for the uninstall action; `desktop-file-validate`.
- [ ] P7.5 Fast start: wizard process must show its first page in under 500 ms (no catalog load); measured in a test.
- [ ] P7.6 Offscreen UI tests with fake backends for every page and each error.

Acceptance: double-click on a file outside the folder opens the wizard; double-click on an installed AppImage inside the folder launches it directly; uninstall works for each type and refuses system packages; "Don't ask again" works and can be undone.

### Phase 8: Polish and release

- [ ] P8.1 Explore page: recently updated row, category rows, featured area (10.2).
- [ ] P8.2 Greek translation: `pylupdate6`, translate, compile `.qm`, language switch; verify layouts with long strings.
- [ ] P8.3 Accessibility pass (10.7): keyboard-only walkthrough, accessible names, badge contrast in light and dark.
- [ ] P8.4 Performance pass against the budgets in section 13.
- [ ] P8.5 Packaging: `PKGBUILD` (depends on `appimage-launcher`), `.desktop` files, icon, README with screenshots, `docs/architecture.md` updated to reality.
- [ ] P8.6 Release checklist: version bump, changelog, tag, CI build of the package.

Acceptance: budgets met; `./check` clean; installing from the built package on a clean Aurelis VM works, and the app starts offline from a pre-seeded cache.

---

## 13. Testing strategy

| Layer | Tooling | What |
|---|---|---|
| `core` | pytest, no Qt | Catalog parsing, search, categories, versions, matching, config, archive safety, wizard detection. Table-driven. Coverage >= 90%. |
| `services` | pytest + local `http.server` + fake runner | Downloader, catalog updater, operations queue |
| `backends` | pytest with a `CommandRunner` fake and `FakeManager1` | Flatpak, pacman, AppImage (D-Bus) |
| `contract` | pytest, XML parsing | The calls in 9.1 match `docs/contracts/manager1.xml`. Optional `real_daemon` suite. |
| `ui`, `wizards` | pytest-qt, `QT_QPA_PLATFORM=offscreen` | Models, delegates, pages, state machine, banners, wizard pages |
| Manual | Owner's machine | Real daemon, real Flatpak, real `pkg`, performance, Dolphin double-click and service menu |

Rules:
- `CommandRunner`, `Clock`, `Paths` and the D-Bus connection are injected everywhere. No test touches the real `$HOME`, network, `pacman`, `flatpak`, or the developer's session bus.
- **Fixtures are real**: captured outputs and the real 22-entry `apps.db`, plus handcrafted edge cases (null arch, `latest`, no checksum, no screenshots, huge keyword list, missing icon, Greek name). Sample JSON of `List`, `Inspect` and `Install` results go in `tests/fixtures/manager1/`.
- Every user-visible error path has a test (message and no leftover files).
- Add a regression test with every bug fix.

Performance budgets (measured on the owner's laptop, recorded in the README):

| Metric | Budget |
|---|---|
| Window visible with cached catalog | < 1 s |
| Wizard first page | < 500 ms |
| Catalog parse (500 apps) | < 100 ms (in a worker) |
| Search keystroke to updated list (500 apps) | < 50 ms |
| Flathub/pacman search (FTS) | < 100 ms |
| Folder change to GUI update | < 1 s |
| Scrolling the grid | no dropped frames at 500 cards |
| Idle memory | < 150 MB with catalog loaded |

---

## 14. Out of scope and integration points

- **`~/Applications` daemon, CLI, helper dialogs, Dolphin AppImage menu**: the `appimage-launcher` repository. This app uses only its D-Bus API (and `appimage run`).
- **`pkg`**: owned by the owner; this app depends only on the contract in 9.2.
- **The database project**: this app consumes its published artifacts only.
- Folder-originated events (drops, deletes, renames) are announced by the launcher's own notifications. This app shows no duplicate popups for them, only a refreshed list.

---

## 15. Decisions to confirm with the owner

1. **Catalog URLs**: the `aurelis-os` organization (as in the brief) vs the repository owner currently used for the database project. Configurable; confirm the final one.
2. **D-Bus service name** (launcher side): `io.github.appimage_launcher.Manager` (from launcher's constants.py; one constant in GUI: put it in core/ or backends/ constants, not repeated). **Resolved — no longer blocks Phase 3.**
3. **`pkg` interface (9.2)**: commands, pending-changes listing, cancel, privilege model, update staging. **Blocks Phase 6.**
4. **Flatpak progress** approach (8.2): CLI with indeterminate progress, PTY, or `libflatpak` via PyGObject (adds a dependency).
5. **Unverified downloads**: ask each time (default), or block entirely, for catalog entries without `sha256`.
6. **Screenshots**: load from the Flathub CDN (current data) or have the database project mirror them. Privacy vs size.
7. **Proprietary software** (Chrome, PhpStorm repacks): shown with a badge by default, or hidden unless enabled in Settings?
8. **Notifications** for updates and a **reboot action** for pending pacman changes: which command, if any.
9. **"Just run" policy** (10.9): confirm that remembered choices are keyed by `{app_id, sha256}` (a changed file asks again) and listed in Settings.
10. **Auto-link by hash** (4.6 rule 2) happens silently. Confirm, or require a one-time confirmation.

---

## Appendix A: Operation events

```python
@dataclass
class Started:
    op_id: str
    app_key: str
    kind: str  # install|remove|update|revert


@dataclass
class Progress:
    op_id: str
    step: str
    fraction: float | None
    message: str


@dataclass
class Finished:
    op_id: str
    app_key: str


@dataclass
class Failed:
    op_id: str
    code: str
    message: str
    details: str  # details = stderr tail / D-Bus message
```
`fraction=None` means indeterminate. Steps used in UI text: `download`, `verify`, `handoff` ("Finishing…"), `install`, `remove`, `update`.

## Appendix B: Category mapping (ordered, first match per store category)

| Store category | Raw freedesktop values (any match) |
|---|---|
| Graphics and Photography | `Graphics`, `2DGraphics`, `3DGraphics`, `RasterGraphics`, `VectorGraphics`, `Photography`, `Scanning`, `Viewer` |
| Audio and Video | `AudioVideo`, `Audio`, `Video`, `Player`, `Recorder`, `Music`, `AudioVideoEditing`, `Midi`, `Mixer`, `Sequencer`, `Tuner` |
| Games | `Game`, `ArcadeGame`, `BoardGame`, `CardGame`, `LogicGame`, `StrategyGame`, `Simulation`, `KidsGame` |
| Development | `Development`, `IDE`, `Debugger`, `Building`, `RevisionControl`, `WebDevelopment`, `GUIDesigner` |
| Internet | `Network`, `WebBrowser`, `Email`, `Chat`, `InstantMessaging`, `FileTransfer`, `P2P`, `RemoteAccess`, `News` |
| Office | `Office`, `WordProcessor`, `Spreadsheet`, `Presentation`, `Calendar`, `ContactManagement`, `Finance`, `Publishing` |
| Education and Science | `Education`, `Science`, `Astronomy`, `Math`, `Chemistry`, `Physics`, `Electronics`, `Engineering`, `Languages` |
| Security | `Security` |
| System | `System`, `Settings`, `Monitor`, `TerminalEmulator`, `FileManager`, `PackageManager` |
| Utilities | `Utility`, `Calculator`, `Archiving`, `Clock`, `TextEditor`, `Accessibility` |
| Other | fallback when nothing above matched |

Ignored (toolkit/desktop tags): `KDE`, `Qt`, `GNOME`, `GTK`, `X-*`. An app may have several store categories.

## Appendix C: URL key labels

| `urls` key | Label |
|---|---|
| `homepage` | Website |
| `bugtracker` | Report a problem |
| `help` | Help |
| `faq` | FAQ |
| `donation` | Donate |
| `translate` | Translate |
| `contact` | Contact |
| `vcs-browser` | Source code |
| `contribute` | Contribute |
| other | title-cased key with `-`/`_` replaced by a space |

Only `https://` links are shown as clickable.

## Appendix D: Test cases the agent must include (minimum)

- Search: `kate` ranks Kate first; `φωτο` matches an entry whose keyword is `φωτογραφία`; `cafe` matches `Café`; two tokens are ANDed; 500 entries under budget.
- Updates (4.5): same version same sha -> none; same version different sha -> update; `latest` with newer `version_changed_at` -> update; `pinned` never; `manual` listed but excluded from Update all; `self_managed` excluded unless the setting is on; no origin -> never.
- Matching (4.6): origin present -> linked; hash equals a catalog entry -> auto-link calls `SetOrigin`; only `app_id` equal -> suggestion, no call until confirmed; neither -> unmanaged.
- Install (7.2): `ConflictPending` then *Replace*, *Keep both*, *Cancel* each produce the right second call; `Busy` is retried once; cache file removed on every failure; `changed=false` shows "Already installed".
- Folder sync (7.6): `AppsChanged(installed, observer)` adds a row; `removed` removes it and returns the catalog entry to NotInstalled; own `api` operations do not toast twice.
- Catalog: entry without `download_url` skipped; `schema_version: 2` keeps the cache and shows the banner; older `generated_at` ignored.
- Downloader: sha mismatch deletes the file; resume continues a `.part`; redirect to `http://` refused.
- Archive: `../evil.png`, absolute path, symlink member and a 10 GB member are all rejected.
- Capabilities: missing capability disables the right actions and shows the banner; `APIVersion` 0 shows "Update appimage-launcher".
- Wizards (10.9): file inside `~/Applications` launches without UI; file outside shows page 1 with `Inspect` data; "Don't ask again" stores `{app_id, sha256}` and a changed hash asks again; system package refused; each detection branch.
- UI: entry with every optional field missing renders; each row of the button-state table; arch mismatch disables Install.
- Operations: two installs queue FIFO; cancel mid-download leaves no `.part`; cancel is disabled once handed to the daemon; a failed op does not block the queue.
