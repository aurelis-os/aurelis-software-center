# Implementation Plan: Phase 6 – Pacman Backend Integration

## Context

Phase 6 adds Pacman package management to Aurelis Software Center following the exact patterns established by FlatpakBackend and FlathubIndex. All package installs/removes go through `PkgdClient` RPC (never subprocess `pkg`). Read-only operations (`pacman -Si`, `-Qi`, `-Qq`) use the injected `runner`. The work decomposes into four independent features: parser, index, backend, and UI wiring.

## Design Decisions

1. **Parser location**: `core/pacman_parser.py` (pure Python, no Qt, mirrors catalog parsers in core/)
2. **Index implementation**: Sqlite3 + FTS5 following `FlathubIndex` pattern exactly, storing parsed `pacman -Si` output
3. **Backend RPC**: Import `PkgdClient` from `aurelis_common.rpc` inside functions (not module-level) for graceful degradation when `aurelis_common` unavailable
4. **Conflict detection**: `remove()` parses `pacman -Qi` output for `Required By` field and rejects removal if any reverse dep is in `user_packages`
5. **Reboot signaling**: Show `PendingRebootBanner` after successful install/remove and on startup if `pkg` queue non-empty
6. **Update support**: `list_updates()` returns `[]` and `update()` fails with `not-supported` (Aurelis repos are pinned)

## Implementation Plan

- [ ] 1. **Create pacman_parser.py with three parsers and fixture-backed tests**
      
      Create `src/aurelis_software/core/pacman_parser.py` with `parse_si_output(text) -> list[dict]`, `parse_qi_output(text) -> list[dict]`, `parse_qq_output(text) -> list[str]`. Records are separated by blank lines. Each line is `Key           : value`. Multi-value fields (Depends On, Required By, Groups, Replaces, Conflicts With, Provides, Optdepends) split on `  ` (two spaces) or return empty list if value is `None`. Return dicts with lowercase_underscore keys (e.g., `depends_on`, `required_by`).
      
      Create `tests/fixtures/pacman/` directory. Add `si_output.txt` (5+ packages including one with multi-value Depends On and Groups), `qi_output.txt` (3+ installed packages with Required By field), `qq_output.txt` (10+ package names, one per line).
      
      Create `tests/core/test_pacman_parser.py` with tests: `test_parse_si_handles_multi_value_fields`, `test_parse_qi_output`, `test_parse_qq_output`, `test_parse_si_handles_blank_lines_separator`, `test_parse_qi_handles_none_value`. Use fixture files. Assert record count, field types, and multi-value list contents.
      
      **Files**: `src/aurelis_software/core/pacman_parser.py`, `tests/fixtures/pacman/{si_output.txt,qi_output.txt,qq_output.txt}`, `tests/core/test_pacman_parser.py`
      
      **Verify**: `pytest tests/core/test_pacman_parser.py -v` passes, then `./check` passes (0 ruff violations, all tests pass)

- [ ] 2. **Create PacmanIndex with FTS5 search and add paths properties**
      
      Add `pacman_db` and `pacman_sync_dir` properties to `src/aurelis_software/core/paths.py`: `pacman_db = self.cache_dir / "aurelis-software" / "pacman_index.db"`, `pacman_sync_dir = Path("/var/lib/pacman/sync")`.
      
      Create `src/aurelis_software/services/pacman_index.py` with `PacmanIndex(db_path, sync_dir, runner=None)`. Schema: `packages(name TEXT PRIMARY KEY, version TEXT, description TEXT, repo TEXT, groups TEXT, installed_size TEXT, download_size TEXT, url TEXT, license TEXT, depends TEXT, raw TEXT)`, `packages_fts USING fts5(name, description)`, `meta(key TEXT PRIMARY KEY, value TEXT)`.
      
      Implement `needs_rebuild()`: return True if db missing, schema version changed, or max mtime of `sync_dir/*.db` files differs from stored `meta.max_sync_mtime`. Handle missing sync_dir gracefully (return False).
      
      Implement `rebuild(runner, progress_cb)`: call `runner(["pacman", "-Si"])`, parse stdout with `pacman_parser.parse_si_output`, insert in batches of 100 into `packages` and `packages_fts`, call `progress_cb(fraction)` every 100 entries, store max mtime of `sync_dir/*.db` in `meta.max_sync_mtime`. Whole operation in one transaction. Use `_default_runner = lambda cmd: subprocess.run(cmd, capture_output=True, text=True, check=False)` returning `(returncode, stdout, stderr)` if runner is None.
      
      Implement `search(query, limit, offset)`: use `_fts_query(query)` helper (same as FlathubIndex) to build FTS5 prefix-AND match expression, `SELECT FROM packages_fts JOIN packages ORDER BY rank LIMIT ? OFFSET ?`, return list[dict].
      
      Implement `get(name)`: `SELECT FROM packages WHERE name=?`, return dict or None.
      
      Implement `categories()`: return `[]` (pacman has groups, not categories).
      
      Create `tests/services/test_pacman_index.py` with `FakeRunner` class. Tests: `test_needs_rebuild_true_when_db_missing`, `test_needs_rebuild_false_when_mtime_unchanged`, `test_rebuild_creates_tables`, `test_rebuild_inserts_parsed_packages`, `test_rebuild_calls_progress_cb`, `test_search_returns_fts_results`, `test_get_returns_single_record`, `test_rebuild_idempotent`.
      
      **Files**: `src/aurelis_software/core/paths.py` (modify), `src/aurelis_software/services/pacman_index.py`, `tests/services/test_pacman_index.py`
      
      **Verify**: `pytest tests/services/test_pacman_index.py -v` passes, then `./check` passes

- [ ] 3. **Create PacmanBackend with PkgdClient RPC and conflict detection**
      
      Create `src/aurelis_software/backends/pacman.py` with `PacmanBackend(runner=None, pkgd_client=None, core_packages_path=None, user_packages_path=None)`. Import `PkgdClient`, `PkgdError`, `PkgdDownError` from `aurelis_common.rpc` **inside methods** (not module-level) with `try/except ImportError` for graceful degradation. Load `core_packages_path` and `user_packages_path` as JSON `list[str]` with fallback to `[]`.
      
      Implement `available` property: `return shutil.which("pkg") is not None`. Add setter no-op (see FlatpakBackend pattern).
      
      Implement `capabilities()`: `return Capabilities(install=available and pkgd_client is not None, remove=available and pkgd_client is not None, update=False)`.
      
      Implement `list_installed()`: if `pkgd_client` is None, call `runner(["pacman", "-Qq"])` and return basic `InstalledApp` list. Otherwise: call `pkgd_client.list()` to get all packages, `pkgd_client.status()` to get `user_packages` and `queue`. For each package: `locked=True` if name in `core_packages`, else user if in `user_packages`, else dependency. `pending="install"` if in `queue["install"]`, `pending="remove"` if in `queue["remove"]`. Return `list[InstalledApp]` with `source=Source.PACMAN`.
      
      Implement `install(app)`: if `pkgd_client` is None, return Operation that immediately fails with `code="daemon-unavailable"`. Otherwise: return Operation whose work calls `pkgd_client.install([app.id])`, emits Started/Progress/Finished on success, Failed on `PkgdError`/`PkgdDownError`. After success, refresh queue state with `pkgd_client.queue()`.
      
      Implement `remove(installed)`: if `pkgd_client` is None, fail with `code="daemon-unavailable"`. First call `runner(["pacman", "-Qi", installed.id])` and parse output with `pacman_parser.parse_qi_output`. Extract `required_by` field (list). If any name in `required_by` is also in `user_packages`, return Operation that immediately fails with `code="ConflictPending"` and `details=f"Required by: {', '.join(dependent_names)}"`. Otherwise call `pkgd_client.remove([installed.id])`, emit events.
      
      Implement `list_updates()`: return `[]` (Aurelis has no pkg-level updates).
      
      Implement `update(app, installed)`: return Operation that immediately fails with `code="not-supported"` and `error="Pacman updates are not supported (repositories are pinned)"`.
      
      Implement `open(installed)`: no-op or pass (pacman apps have no single launch path).
      
      Check if `PendingRebootBanner` exists in `src/aurelis_software/ui/banners.py`. If missing, add: `class PendingRebootBanner(Banner)` with `text="Changes will take effect after reboot."` `kind="info"`.
      
      Create `tests/backends/test_pacman.py` with `FakePkgdClient` and `FakeRunner` classes. Tests: `test_list_installed_classifies_locked_user_dependency`, `test_list_installed_sets_pending_from_queue`, `test_install_calls_pkgd_client_install`, `test_install_fails_when_daemon_unavailable`, `test_remove_checks_required_by_and_fails_on_conflict`, `test_remove_succeeds_when_no_conflict`, `test_available_false_when_pkg_not_on_path`, `test_list_updates_always_empty`, `test_update_not_supported`.
      
      **Files**: `src/aurelis_software/backends/pacman.py`, `src/aurelis_software/ui/banners.py` (modify if needed), `tests/backends/test_pacman.py`
      
      **Verify**: `pytest tests/backends/test_pacman.py -v` passes, then `./check` passes

- [ ] 4. **Wire PacmanBackend, PacmanIndex, and PacmanModel into MainWindow**
      
      Add `PacmanModel` class to `src/aurelis_software/ui/app_model.py` following `FlathubModel` pattern exactly. Same role constants as `AppModel`/`FlathubModel`. `__init__(index, parent=None)`, `set_index(index)`, `set_query(query)`, `canFetchMore`/`fetchMore` with `_PAGE_SIZE=48`, `data()` returns dict fields with `source=Source.PACMAN`, `row_at(row)`, `find_by_id(app_id)`.
      
      In `src/aurelis_software/ui/main_window.py` `__init__`: import `PacmanBackend` and `PacmanIndex`. Add `self._pacman_backend = PacmanBackend(runner=_default_runner)` (inject runner, `pkgd_client=None` for now). Add `self._pacman_index = PacmanIndex(db_path=paths.pacman_db, sync_dir=paths.pacman_sync_dir)`. Store references alongside `_flatpak_backend` and `_flathub_index`.
      
      In `main_window.py` `_refresh_installed()` method: after calling `self._flatpak_backend.list_installed()`, also call `self._pacman_backend.list_installed()` and append results to the installed apps list. Merge all sources before populating `_installed_apps` dict.
      
      In `main_window.py` `_recompute_updates()` method: after calling `self._flatpak_backend.list_updates()`, also call `self._pacman_backend.list_updates()` and append results (will be empty list, but follow the pattern).
      
      In `main_window.py`, add `_show_pending_reboot_banner()` method: check if `PendingRebootBanner` already exists in `_banner_layout` children; if not, create and add it. In `_on_operation_finished` handler: if the operation kind was `"install"` or `"remove"` and source was `Source.PACMAN`, call `_show_pending_reboot_banner()`.
      
      In `main_window.py` `__init__` after `_init_flatpak()`: call `_check_pending_pacman_operations()` which tries to import `PkgdClient`, calls `pkgd_client.status()["queue"]`, and if `queue["install"]` or `queue["remove"]` is non-empty, calls `_show_pending_reboot_banner()`. Gracefully handle import errors (skip if `aurelis_common` unavailable).
      
      In `main_window.py` `_on_remove_requested` or the operation failure handler: when a pacman remove operation fails and `result.error == "ConflictPending"`, show `QMessageBox.warning` with title=`"Cannot Remove Package"`, text=`"This package is required by other user-installed packages:"`, informativeText=`result.details` (the list of dependents). Do not proceed with removal.
      
      Add `SECTION_PACMAN` constant check in `main_window.py` `_on_section()` handler: when `section == "source:pacman"`, switch to a Pacman browse page (create `_pacman_page = AppListView` backed by `PacmanModel`, add to `_stack`). Wire similar to how Flathub section is handled.
      
      Create `tests/ui/test_pacman_integration.py` with tests: `test_main_window_loads_pacman_backend`, `test_refresh_installed_includes_pacman_apps`, `test_pacman_remove_conflict_shows_warning`, `test_pending_reboot_banner_shown_after_pacman_operation`. Use `FakePacmanBackend` and `FakePacmanIndex` fixtures.
      
      **Files**: `src/aurelis_software/ui/app_model.py` (modify), `src/aurelis_software/ui/main_window.py` (modify), `tests/ui/test_pacman_integration.py`
      
      **Verify**: `pytest tests/ui/test_pacman_integration.py -v` passes, then `./check` passes (all 302+ tests pass, 0 ruff violations)

## Integration Hazards

1. **PkgdClient import**: Must be inside functions, not module-level, with try/except for graceful degradation when `aurelis_common` unavailable
2. **Required By parsing**: `pacman -Qi` output may have `Required By : None` or multi-line dependencies; parser must handle both
3. **Mtime comparison**: `sync_dir/*.db` files may not exist on non-Arch systems; `needs_rebuild()` must handle gracefully
4. **Queue state refresh**: After `pkgd_client.install()` or `remove()`, call `pkgd_client.queue()` to update pending state before emitting Finished
5. **Banner lifecycle**: Only create one `PendingRebootBanner` instance; check `_banner_layout` children before adding

## Final Verification

After all steps:
```bash
./check
```

Expected: `All checks passed!` with 302+ tests passing, 0 ruff violations.

Manually verify (if Aurelis system available):
- MainWindow opens without import errors
- Pacman sidebar section shows packages from `pacman -Si`
- Install queues a package via `pkg add` and shows reboot banner
- Remove with conflicts shows warning dialog
- Remove without conflicts succeeds and shows reboot banner
