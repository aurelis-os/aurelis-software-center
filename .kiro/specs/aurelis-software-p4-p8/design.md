# Design: Aurelis Software Center — Phase 4 through Phase 8

## Overview

This design covers the implementation plan for completing the Aurelis Software Center from Phase 4 (AppImage updates) through Phase 8 (Polish and release). The existing three-layer architecture (`core` → `services`/`backends` → `ui`/`wizards`) is extended with new backends, indexes, wizard entry points, and polish work.

Language: **Python 3.11+** with PyQt6, matching the existing codebase.

---

## Phase 4: AppImage Updates

### Fix 1 — `_call_update_install.on_error` ordering

**File**: `src/aurelis_software/ui/main_window.py`

```python
def on_error(err):
    _active_operations.pop(op_id, None)  # pop FIRST
    _recompute_updates()  # then recompute
    ...
```

The existing code calls `_recompute_updates()` before removing the entry, so the update stays in the badge count after a failure. Reversing the order fixes `test_update_failure_daemon_death`.

### Fix 2 — `_button_config_for_state` for Updating state

**File**: `src/aurelis_software/ui/main_window.py` (or wherever `_button_config_for_state` lives)

```python
"Updating": {"text": self.tr("Updating…"), "enabled": False},
```

The button must be disabled while an update is running to fix `test_update_busy_state_disables_button`.

### Fix 3 — `_start_update.on_finished` handoff progress

**File**: `src/aurelis_software/ui/main_window.py`

Emit `progress(step="handoff")` before the D-Bus `Install` call so the UI shows "Finishing…" during the atomic daemon phase.

### Updates page (`ui/updates_page.py`)

```python
class UpdatesPage(QWidget):
    update_requested = pyqtSignal(str)  # app_key
    update_all_requested = pyqtSignal()

    def populate(self, updates: list[UpdateInfo], installed: dict[str, InstalledApp]) -> None: ...
    def set_progress(self, app_key: str, event: OperationEvent) -> None: ...
    def set_result(self, app_key: str, success: bool, message: str) -> None: ...
```

Groups rows by `Source`. Each row: checkbox, icon, name, installed version → new version, source badge, per-row progress bar (hidden until operation starts), **Update** button. **Update all** button at top; executes only `auto`-policy rows in FIFO order. On completion, a non-modal summary dialog lists per-app results.

Pacman rows show "(applies after restart)" note next to the version.

### Policy selector (`detail_page.py`)

A `QComboBox` with options **Automatic** / **Ask me** / **Pinned** appears on the detail page when an installed AppImage is shown. Changes call `SetPolicy(managed_name, policy)` via the backend.

### Notifications

A `QSystemTrayIcon`-less desktop notification is sent via `QDBusMessage` to `org.freedesktop.Notifications` when update count increases and the setting is on.

---

## Phase 5: Flathub

### Flathub index (`services/flathub_index.py`)

```python
class FlathubIndex:
    def __init__(self, db_path: Path, appstream_path: Path, locale: str = "en") -> None: ...
    def needs_rebuild(self) -> bool: ...  # checks mtime
    def rebuild(self, progress_cb) -> None: ...  # runs in worker
    def search(self, query: str, limit: int, offset: int) -> list[dict]: ...
    def get(self, app_id: str) -> dict | None: ...
    def categories(self) -> list[str]: ...
```

SQLite schema:
```sql
CREATE TABLE apps (
    id TEXT PRIMARY KEY,
    name TEXT,
    summary TEXT,
    version TEXT,
    icon_name TEXT,
    categories TEXT,   -- JSON array
    raw TEXT           -- JSON of full record
);
CREATE VIRTUAL TABLE apps_fts USING fts5(
    id UNINDEXED, name, summary, keywords,
    content=apps, content_rowid=rowid
);
```

Parsing: `xml.etree.ElementTree` on the decompressed stream. For each `<component type="desktop-application">` extract id, name, summary, version, icon, categories, keywords, screenshots. Prefer `xml:lang` elements matching the requested locale, fall back to untagged.

### Flatpak backend (`backends/flatpak.py`)

```python
class FlatpakBackend(Backend):
    source = Source.FLATPAK

    def __init__(self, runner: CommandRunner) -> None: ...
```

`CommandRunner` is the existing injection interface used by `qt_process.py`. All commands are argument lists, never shell strings.

```python
LIST_INSTALLED_CMD = ["flatpak", "list", "--user", "--app", "--columns=application,version,origin"]
LIST_UPDATES_CMD = [
    "flatpak",
    "remote-ls",
    "--user",
    "--updates",
    "--app",
    "--columns=application,version",
]
INSTALL_CMD = lambda app_id: [
    "flatpak",
    "install",
    "--user",
    "--noninteractive",
    "-y",
    "flathub",
    app_id,
]
REMOVE_CMD = lambda app_id: ["flatpak", "uninstall", "--user", "--noninteractive", "-y", app_id]
UPDATE_CMD = lambda app_id: ["flatpak", "update", "--user", "--noninteractive", "-y", app_id]
ADD_REMOTE_CMD = [
    "flatpak",
    "remote-add",
    "--user",
    "--if-not-exists",
    "flathub",
    "https://dl.flathub.org/repo/flathub.flatpakrepo",
]
REFRESH_APPSTREAM = ["flatpak", "update", "--appstream", "--user"]
```

Progress: indeterminate `QProgressBar` during any operation (the CLI output is too coarse for a fraction).

### Paginated model (`ui/app_model.py` extension)

Add `FlathubModel(QAbstractListModel)` with `canFetchMore`/`fetchMore` backed by `FlathubIndex.search`. The model fetches one page (48 items) per `fetchMore` call. The existing `AppCardDelegate` renders Flatpak rows unchanged.

### Installed / Updates integration

`MainWindow._refresh_installed` and `_recompute_updates` aggregate results from all three backends. Each backend is called in a worker; results are merged in the main thread.

---

## Phase 6: Pacman

### Pacman parser (`core/pacman_parser.py`)

```python
def parse_si_output(text: str) -> list[dict]: ...
def parse_qi_output(text: str) -> list[dict]: ...
def parse_qq_output(text: str) -> list[str]: ...
```

Pure Python, no Qt. Parses the tab-indented multi-line `pacman -Si` / `pacman -Qi` output into dicts. Handles multi-value fields (Depends On, Required By, etc.).

### Pacman index (`services/pacman_index.py`)

```python
class PacmanIndex:
    def __init__(self, db_path: Path, sync_dir: Path = Path("/var/lib/pacman/sync")) -> None: ...
    def needs_rebuild(self) -> bool: ...
    def rebuild(self, runner: CommandRunner, progress_cb) -> None: ...
    def search(self, query: str, limit: int, offset: int) -> list[dict]: ...
    def get(self, name: str) -> dict | None: ...
```

SQLite schema mirrors Flathub index with pacman-specific columns (repo, groups, installed_size, download_size, depends).

### Pacman backend (`backends/pacman.py`)

```python
class PacmanBackend(Backend):
    source = Source.PACMAN

    def __init__(
        self,
        runner: CommandRunner,
        core_packages_path: Path,
        user_packages_path: Path,
    ) -> None: ...
```

Pending state: call `pkg queue` (the RPC command returning JSON) after each `pkg add`/`pkg remove` to refresh the displayed pending set. Never read a GUI-owned file.

Reverse dependency check for `remove`: parse `pacman -Qi <name>` "Required By" field; intersect with user-installed packages. If non-empty, show a `QMessageBox` warning before proceeding.

### Pending-reboot banner

`ui/banners.py` already exists. Add a `PendingRebootBanner` that is shown while `pkg queue` returns a non-empty queue. The banner persists across restarts because `MainWindow.__init__` calls `pkg queue` during startup.

---

## Phase 7: Wizards

### Detection (`wizards/detect.py`)

```python
@dataclass
class DetectionResult:
    kind: Literal["appimage", "flatpak", "pacman-system", "pacman-user", "unknown"]
    id: str | None
    name: str | None


def detect(
    path: str,
    *,
    applications_dir: Path,
    flatpak_export_dirs: tuple[Path, ...],
    core_packages_path: Path,
    user_packages_path: Path,
    list_runner: Callable[[list[str]], str],  # injected; runs pacman -Qo etc.
) -> DetectionResult: ...
```

Pure Python, no Qt, no subprocess side effects (all I/O injected).

### Install wizard (`wizards/install_wizard.py`)

```python
class InstallWizard(QDialog):
    def __init__(
        self, path: Path, backend: AppImageBackend | FlatpakBackend, config: Config, paths: Paths
    ) -> None: ...
```

Routing: if `Inspect(path).relation` is `"installed"` and the path is inside `applications_dir`, call `appimage run <managed_name>` via `QProcess.startDetached` and exit immediately with no UI.

Page 1: a `QStackedWidget` slide showing name/icon/version/relation text, **Install**, **Just run** + checkbox, **Cancel**.
Page 2: spinner + status label, non-interactive until done.

"Don't ask again" stores `{"app_id": ..., "sha256": ...}` in `config["wizard"]["run_without_asking"]` (a list).

### Uninstall wizard (`wizards/uninstall_wizard.py`)

```python
class UninstallWizard(QDialog):
    def __init__(
        self, path_or_desktop_id: str, backends: dict[Source, Backend], config: Config, paths: Paths
    ) -> None: ...
```

Calls `wizards/detect.py` first. System packages: static refusal page. Others: Page 1 (confirm) → Page 2 (progress).

### Entry point wiring (`__main__.py`)

```python
# Existing:
#   aurelis-software              -> main GUI
# New:
#   aurelis-software wizard install <path>
#   aurelis-software wizard uninstall <path-or-desktop-id>
```

Wizards do not load the catalog, do not open the main window, and do not build any search index.

---

## Phase 8: Polish

### Explore page

`ui/main_window.py` / `ui/explore_page.py`: build the Explore layout as:
1. "Recently updated" horizontal scroll row — top 6 apps by `version_changed_at`.
2. Per-category horizontal rows (only categories with ≥ 1 app).
3. "All apps" full grid.

### Greek translation

```
pylupdate6 src/aurelis_software/ -ts resources/i18n/el.ts
# Translate strings in el.ts
lrelease resources/i18n/el.ts -qm resources/i18n/el.qm
```

`app.py` installs a `QTranslator` for the configured locale at startup. The language selector in Settings calls `QApplication.instance().installTranslator(...)` and rebuilds the UI (or restarts; document the chosen approach).

### Accessibility

`theme.py` gains a `badge_contrast_check()` utility that asserts WCAG AA (4.5:1) for each badge color against system background. All new widgets set `setAccessibleName()`.

### PKGBUILD

`packaging/PKGBUILD` structure:
```
pkgname=aurelis-software
pkgver=...
depends=(python python-pyqt6 appimage-launcher)
makedepends=(python-build python-installer)
install -Dm644 resources/aurelis-software.desktop
install -Dm644 resources/icons/aurelis-software.png
```

---

## Correctness Properties

### Property 1: Update badge monotonicity after fix
After fixing R1.1, calling `_recompute_updates()` following a failed update operation must never increase the badge count above the count before the operation started.

**Validates: R1.1, R2.2**

### Property 2: zsync fallback
For any app entry, `fetch_update(entry, installed_path)` returns a file at a `.part` path regardless of whether zsync is available, as long as the download URL is reachable.

**Validates: R3.1, R3.2**

### Property 3: Origin version after update
After a successful update, `build_origin(entry).version == entry.version` and `build_origin(entry).sha256 == entry.sha256` for all catalog entries.

**Validates: R4.1, R2.3**

### Property 4: Flatpak command construction
For any valid app id string matching `^[A-Za-z0-9._+-]+$`, `FlatpakBackend` constructs commands as argument lists (no shell string). No element of any command contains shell metacharacters introduced by the app id.

**Validates: R10.1–R10.6**

### Property 5: Pacman parser round-trip
For any output from `pacman -Si`, `parse_si_output` produces a dict whose `name` field matches the "Name" line and whose `version` field matches the "Version" line.

**Validates: R13.1, R13.2**

### Property 6: Detection determinism
`detect(path, ...)` with the same inputs always returns the same `DetectionResult` regardless of call order.

**Validates: R19.1, R19.2**
