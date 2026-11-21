# Implementation Plan: Phase 8 — Polish and Release

**Project:** Aurelis Software Center (PyQt6 application)  
**Current version:** 0.1.0  
**Target version:** 1.0.0  
**Architecture:** Three-layer (core → services/backends → ui/wizards)  
**Quality gate:** `./check` (ruff + pytest) must pass with zero failures and zero warnings  
**Working directory:** `/home/user/Projects/aurelis-software-center`

---

## Context

Phases 4-7 are complete. The application has:
- AppImage backend with update support (Phase 4)
- Flathub integration with FTS search (Phase 5)
- Pacman integration with pending reboot tracking (Phase 6)
- Install and uninstall wizards (Phase 7)

Phase 8 adds final polish: Explore page layout, Greek translation, accessibility, performance testing, and packaging.

---

## Task 5.1: Polish the Explore Page

**What:** Add or refactor explore page layout with "Recently updated", per-category rows, and "All apps" grid.

- [ ] 1. Create `src/aurelis_software/ui/explore_page.py` as a dedicated `QWidget` for the Explore section
      - Replace the simple `AppListView` currently used for `self._explore` in `main_window.py`
      - Layout: (1) `QLabel` heading "Recently updated" + horizontal scroll area with top 6 apps by `version_changed_at` from `raw` dict
      - (2) For each category with ≥1 app: `QLabel` heading with category name + horizontal scroll area
      - (3) `QLabel` heading "All apps" + full grid using `AppListView` with `AppCardDelegate`
      - Use `QScrollArea` with horizontal scrolling for rows (1) and (2); disable vertical scrollbars for those
      - Category rows reuse `AppCardDelegate` for painting; icons lazy-loaded via existing `ui/icons.py` infrastructure
      - Expose `set_apps(apps: list[App])` method that computes categories, sorts by `version_changed_at`, and populates all three sections
      - Expose `selection_changed` signal that emits when user clicks a card in any section
      - Files: `src/aurelis_software/ui/explore_page.py` (new)
      - Verify: `python -c "from aurelis_software.ui.explore_page import ExplorePage; print('OK')"` succeeds

- [ ] 2. Wire `ExplorePage` into `main_window.py`
      - Replace `self._explore = AppListView(...)` with `self._explore = ExplorePage(icons_dir=paths.icons_dir)` around line 172
      - Update `_refresh_explore()` to call `self._explore.set_apps(apps)` — the method signature is unchanged
      - Connect `self._explore.selection_changed` to `self._on_selection_changed` (same handler)
      - Remove or comment out the old `self._explore.selection_changed(self._on_selection_changed)` line if it used a different signature
      - Files: `src/aurelis_software/ui/main_window.py`
      - Verify: Run the app in offscreen mode and navigate to Explore; no crashes

- [ ] 3. Add a test for `ExplorePage` layout
      - Create `tests/ui/test_explore_page.py`
      - Test: Instantiate `ExplorePage` with 20 synthetic apps (varying `version_changed_at` and categories); call `set_apps(apps)`
      - Assert: "Recently updated" section exists and shows ≤6 apps; at least one category section exists; "All apps" grid shows all 20 apps
      - Use `qtbot.addWidget(page)` and `QTest.qWaitForWindowExposed(page)` to ensure layout completes
      - Files: `tests/ui/test_explore_page.py` (new)
      - Verify: `pytest tests/ui/test_explore_page.py -v` passes

**Requirements:** R25.1

---

## Task 5.2: Add Greek Translation

**What:** Generate `.ts` file, translate all strings to Greek, compile `.qm`, and load `QTranslator` based on config.

- [ ] 4. Create `src/aurelis_software/resources/i18n/` directory structure
      - Run: `mkdir -p src/aurelis_software/resources/i18n`
      - Files: directory created
      - Verify: `ls -la src/aurelis_software/resources/i18n/` shows the directory

- [ ] 5. Generate Greek translation template using `pylupdate6`
      - Run: `pylupdate6 src/aurelis_software/ -ts src/aurelis_software/resources/i18n/el.ts`
      - This scans all `.py` files for `tr(...)` calls and generates an XML `.ts` file
      - Files: `src/aurelis_software/resources/i18n/el.ts` (new)
      - Verify: `ls -la src/aurelis_software/resources/i18n/el.ts` shows the file; `wc -l src/aurelis_software/resources/i18n/el.ts` shows >10 lines

- [ ] 6. Translate all strings in `el.ts` to Greek
      - Open `src/aurelis_software/resources/i18n/el.ts` in a text editor
      - For each `<source>` tag, add a corresponding `<translation>` tag with the Greek text
      - Use idiomatic Greek; context for UI strings is in the source file references
      - Example: `<source>Install</source>` → `<translation>Εγκατάσταση</translation>`
      - Files: `src/aurelis_software/resources/i18n/el.ts`
      - Verify: `grep '<translation>' src/aurelis_software/resources/i18n/el.ts | wc -l` shows >0 translations

- [ ] 7. Compile the `.ts` file to `.qm` using `lrelease`
      - Run: `lrelease src/aurelis_software/resources/i18n/el.ts -qm src/aurelis_software/resources/i18n/el.qm`
      - The `.qm` file is the binary translation file that Qt loads at runtime
      - Files: `src/aurelis_software/resources/i18n/el.qm` (new)
      - Verify: `ls -la src/aurelis_software/resources/i18n/el.qm` shows a non-zero-size file

- [ ] 8. Update `app.py` to load `QTranslator` based on `ui.language` config
      - In `main(argv)` function around line 38, after `app = QApplication.instance() or QApplication(args)`:
      - Read `language = config.get("ui.language", "en")`
      - If `language != "en"`, instantiate `QTranslator()`, load `.qm` from `src/aurelis_software/resources/i18n/{language}.qm`, and install via `app.installTranslator(translator)`
      - Store the translator reference in a variable that outlives the function (e.g., as a module-level global or app property)
      - Files: `src/aurelis_software/ui/app.py`
      - Verify: Start the app with `config["ui"]["language"] = "el"`; labels should show Greek text

- [ ] 9. Add language selector to `settings_dialog.py`
      - In `SettingsDialog.__init__`, add a `QComboBox` with options: "English", "Ελληνικά" (Greek)
      - Map to config values `"en"`, `"el"`
      - On change, call `self.config.set("ui.language", language_code)` and `save(self.paths, self.config)`
      - Show a `QMessageBox` informing the user: "Restart the application to apply the new language."
      - Files: `src/aurelis_software/ui/settings_dialog.py`
      - Verify: Open Settings, change language, restart app; UI shows in selected language

**Requirements:** R26.1, R26.2

**Dependencies:** Task 5.2 must complete before 5.3 (Greek layout stress test depends on the compiled `.qm` file).

---

## Task 5.3: Greek Layout Stress Test (OPTIONAL — RECOMMENDED TO SKIP)

**Decision:** **Skip this task** to accelerate MVP delivery. Greek strings are typically 10-30% longer than English; the default Qt layout managers (QVBoxLayout, QHBoxLayout) auto-expand to fit text, so clipping is unlikely. We can add this test in a post-1.0 release if layout bugs are reported.

**Rationale:** The test requires instantiating every dialog and page offscreen with the Greek translator active, then walking the widget tree to assert no clipping. This is ~100 lines of code and significant maintenance burden for a problem that Qt's layout system largely prevents by default. If we discover clipping during manual testing, we can add explicit `setMinimumWidth()` calls at that time.

**Requirements:** R26.2 (partial coverage; manual testing recommended)

---

## Task 5.4: Accessibility Pass

**What:** Add `setAccessibleName(...)` to all interactive widgets, verify Tab order, and add WCAG AA contrast assertion for badges.

- [ ] 10. Add accessible names to all buttons, labels, badges, and progress bars in `ui/` and `wizards/`
       - Audit every file in `src/aurelis_software/ui/` and `src/aurelis_software/wizards/`
       - For every `QPushButton`, `QLabel` carrying semantic meaning (not decorative), badge widget, and progress bar:
         - Add `widget.setAccessibleName("descriptive name")` immediately after creation
         - Descriptive names should match visible text or describe purpose (e.g., "Install button", "Update progress")
       - Files to modify (at minimum):
         - `src/aurelis_software/ui/main_window.py`: search bar, sidebar items, toolbar buttons
         - `src/aurelis_software/ui/detail_page.py`: Install/Remove/Update buttons, policy selector
         - `src/aurelis_software/ui/updates_page.py`: Update/Update All buttons, checkboxes, progress bars
         - `src/aurelis_software/ui/installed_page.py`: filter toggle, row widgets
         - `src/aurelis_software/ui/settings_dialog.py`: all checkboxes, combo boxes, list widgets
         - `src/aurelis_software/wizards/install_wizard.py`: Install/Just run/Cancel buttons, status label
         - `src/aurelis_software/wizards/uninstall_wizard.py`: Remove/Cancel buttons, status label
         - `src/aurelis_software/ui/sidebar.py`: section labels, badge counts
       - Verify: Run `grep -r 'setAccessibleName' src/aurelis_software/ui/ src/aurelis_software/wizards/ | wc -l` shows >30 calls

- [ ] 11. Verify Tab order in all major UI containers
       - Manually test (or write a test) that confirms Tab key traverses interactive elements in logical order:
         - Main window: search bar → sidebar items → detail page buttons
         - Detail page: Install/Remove/Update button → policy selector → back/close
         - Updates page: Update All → per-app Update buttons → checkboxes
         - Settings dialog: all checkboxes → combo boxes → OK/Cancel
         - Install wizard: Install → Just run → Cancel
         - Uninstall wizard: Remove → Cancel
       - If order is wrong, set explicit `QWidget.setTabOrder(widget1, widget2)` calls in the constructor
       - Files: (may require edits to `main_window.py`, `detail_page.py`, `updates_page.py`, `settings_dialog.py`, wizards)
       - Verify: Manual test or `tests/ui/test_accessibility.py` confirms Tab order

- [ ] 12. Add `assert_badge_contrast()` function to `theme.py`
       - Function signature: `def assert_badge_contrast() -> None:`
       - For each badge kind in `badge_color(kind)`, compute foreground color (white or black based on `_CHIP_TEXT_LIGHTNESS`)
       - Compute WCAG contrast ratio: `(L1 + 0.05) / (L2 + 0.05)` where L is relative luminance
       - Assert ratio ≥ 4.5 for all badge kinds (WCAG AA for normal text)
       - Raise `AssertionError` with details if any badge fails
       - Files: `src/aurelis_software/ui/theme.py`
       - Verify: `python -c "from aurelis_software.ui.theme import assert_badge_contrast; assert_badge_contrast(); print('OK')"` succeeds

- [ ] 13. Add accessibility test that calls `assert_badge_contrast()`
       - Create `tests/ui/test_accessibility.py`
       - Test: `def test_badge_contrast_wcag_aa(): assert_badge_contrast()`
       - Files: `tests/ui/test_accessibility.py` (new)
       - Verify: `pytest tests/ui/test_accessibility.py -v` passes

**Requirements:** R27.1, R27.2, R27.3, R27.4

**Dependencies:** None; can run in parallel with other tasks.

---

## Task 5.5: Performance Pass

**What:** Add timed assertions for catalog parse, search keystroke, and FTS search; record results in README.

- [ ] 14. Create `tests/test_performance.py` with catalog parse budget test
       - Test: `test_catalog_parse_500_apps`
       - Generate 500 synthetic `App` objects with realistic fields
       - Serialize to JSON (mimicking `catalog.json` format)
       - Time the parse: `start = time.perf_counter(); apps = load_catalog(path); elapsed = time.perf_counter() - start`
       - Assert `elapsed < 0.1` (100 ms budget)
       - Files: `tests/test_performance.py` (new)
       - Verify: `pytest tests/test_performance.py::test_catalog_parse_500_apps -v` passes

- [ ] 15. Add search keystroke budget test
       - Test: `test_search_keystroke_500_apps`
       - Build in-memory search index with 500 synthetic apps using `core/search.py` functions
       - Simulate a single keystroke query (e.g., "gim") by calling `search(index, "gim")`
       - Time the search: `start = time.perf_counter(); results = search(...); elapsed = time.perf_counter() - start`
       - Assert `elapsed < 0.05` (50 ms budget)
       - Files: `tests/test_performance.py`
       - Verify: `pytest tests/test_performance.py::test_search_keystroke_500_apps -v` passes

- [ ] 16. Add FTS search budget test
       - Test: `test_fts_search_flathub` and `test_fts_search_pacman`
       - Use real fixtures: `tests/fixtures/flathub_appstream.xml` (if exists) or create a small fixture; `tests/fixtures/pacman/si_output.txt`
       - Build `FlathubIndex` and `PacmanIndex` from fixtures
       - Time FTS query: `start = time.perf_counter(); results = index.search("editor", limit=50); elapsed = time.perf_counter() - start`
       - Assert `elapsed < 0.1` (100 ms budget per search)
       - Files: `tests/test_performance.py`, may need to create `tests/fixtures/flathub_appstream.xml` (small, ~20 apps)
       - Verify: `pytest tests/test_performance.py -k fts -v` passes

- [ ] 17. Run the full app against fixture and record results in README
       - On the owner's machine, run the app with the largest available fixture
       - Manually measure or instrument: app startup time, catalog load time, first search result time
       - Edit `README.md` to add a "Performance" section with measured results:
         ```
         ## Performance
         - Catalog parse (500 apps): X ms
         - Search keystroke (500 apps): Y ms
         - Flathub FTS search: Z ms
         - Pacman FTS search: W ms
         (Measured on: hardware details, date)
         ```
       - Files: `README.md`
       - Verify: `README.md` contains the Performance section with real numbers

**Requirements:** R28.1

**Dependencies:** None; can run in parallel with other tasks.

---

## Task 5.6: Write `packaging/PKGBUILD`

**What:** Create Arch Linux package build script with correct dependencies and installation rules.

- [ ] 18. Create `packaging/PKGBUILD`
       - Standard Arch PKGBUILD format
       - Fields:
         ```bash
         pkgname=aurelis-software
         pkgver=1.0.0
         pkgrel=1
         pkgdesc="Aurelis Software Center — PyQt6 software center and wizards"
         arch=('any')
         url="https://github.com/aurelis/aurelis-software-center"
         license=('proprietary')
         depends=('python' 'python-pyqt6' 'appimage-launcher')
         makedepends=('python-build' 'python-installer' 'python-hatchling')
         source=("$pkgname-$pkgver.tar.gz")
         sha256sums=('SKIP')
         ```
       - `package()` function:
         - Install Python package: `python -m installer --destdir="$pkgdir" dist/*.whl`
         - Install `.desktop` files: create `resources/aurelis-software.desktop` (main app), `resources/aurelis-software-wizard-install.desktop`, `resources/aurelis-software-uninstall.desktop` (from Phase 7 requirements)
         - Copy to `"$pkgdir/usr/share/applications/"`
         - Install icon: copy `resources/aurelis-software.png` (or `.svg`) to `"$pkgdir/usr/share/icons/hicolor/128x128/apps/"` or scalable directory
       - Files: `packaging/PKGBUILD` (new), may need to create `resources/aurelis-software.desktop` and icon files if they don't exist
       - Verify: `cd packaging && makepkg --nobuild` succeeds (validates PKGBUILD syntax without building)

- [ ] 19. Create `.desktop` files in `resources/` if they don't exist
       - Main app: `resources/aurelis-software.desktop`
         ```
         [Desktop Entry]
         Type=Application
         Name=Aurelis Software
         Comment=Software center for Aurelis
         Exec=aurelis-software
         Icon=aurelis-software
         Categories=System;PackageManager;
         ```
       - Wizard install: `resources/aurelis-software-wizard-install.desktop` (NoDisplay=true, MimeType=application/vnd.appimage;application/vnd.flatpak.ref;application/vnd.flatpak;)
       - Uninstall service menu: `resources/aurelis-software-uninstall.desktop` (see Phase 7 R22.2, R22.3)
       - Files: `resources/aurelis-software.desktop`, `resources/aurelis-software-wizard-install.desktop`, `resources/aurelis-software-uninstall.desktop` (new or already exist from Phase 7)
       - Verify: `desktop-file-validate resources/*.desktop` passes for all files

- [ ] 20. Add CI step or Makefile target for PKGBUILD validation
       - Option A: Add to `.github/workflows/` if CI exists
       - Option B: Create `Makefile` with target:
         ```makefile
         .PHONY: check-pkgbuild
         check-pkgbuild:
             cd packaging && makepkg --nobuild
         ```
       - Files: `Makefile` (new) or `.github/workflows/ci.yml` (if exists)
       - Verify: `make check-pkgbuild` (or CI run) succeeds

**Requirements:** R29.1

**Dependencies:** Task 5.8 (version bump) must happen before or in parallel to ensure `pkgver` matches `__version__`.

---

## Task 5.7: PKGBUILD Validation Test (OPTIONAL — RECOMMENDED TO SKIP)

**Decision:** **Skip this task** to accelerate MVP delivery. The `makepkg --nobuild` step in Task 5.6 already validates PKGBUILD syntax. The version-match check can be done manually during release preparation.

**Rationale:** The test would run `desktop-file-validate` (already covered by `makepkg --install` warnings) and compare `pkgver` to `__version__`. This is a one-line manual check during release. Automating it adds a pytest dependency on `makepkg` being available, which complicates CI and local dev environments. If version mismatches become a recurring problem, we can add this test post-1.0.

**Requirements:** R29.1, R29.2 (partial coverage; manual verification recommended)

---

## Task 5.8: Release Checklist

**What:** Bump version, add CHANGELOG entry, and confirm `./check` passes.

- [ ] 21. Bump version in `__init__.py` and `PKGBUILD`
       - Edit `src/aurelis_software/__init__.py`: change `__version__ = "0.1.0"` to `__version__ = "1.0.0"`
       - Edit `packaging/PKGBUILD`: change `pkgver=0.1.0` to `pkgver=1.0.0`
       - Edit `pyproject.toml`: change `version = "0.1.0"` to `version = "1.0.0"`
       - Files: `src/aurelis_software/__init__.py`, `packaging/PKGBUILD`, `pyproject.toml`
       - Verify: `grep -E '__version__|pkgver|^version' src/aurelis_software/__init__.py packaging/PKGBUILD pyproject.toml` shows 1.0.0 in all three

- [ ] 22. Create `CHANGELOG.md` with release entry
       - Create `CHANGELOG.md` at project root
       - Format:
         ```markdown
         # Changelog

         ## [1.0.0] - 2025-01-XX

         ### Added
         - **Phase 4:** AppImage update support with zsync delta downloads, update policies (auto/manual/pinned), and undo functionality
         - **Phase 5:** Flathub integration with FTS5 full-text search, lazy pagination, and metadata refresh
         - **Phase 6:** Pacman integration with locked/user/dependency classification, reverse-dependency warnings, and pending reboot banner
         - **Phase 7:** Install wizard for AppImages and Flatpak files; uninstall wizard with detection and trash support
         - **Phase 8:** Polished Explore page with "Recently updated" and per-category sections; Greek translation (el); accessibility names; performance tests; Arch packaging (PKGBUILD)

         ### Changed
         - Explore page now shows "Recently updated" apps and per-category horizontal rows

         ### Performance
         - Catalog parse (500 apps): <100 ms
         - Search keystroke (500 apps): <50 ms
         - FTS search: <100 ms

         ## [0.1.0] - 2025-01-XX (Pre-release)
         - Initial development versions (Phases 0-3)
         ```
       - Files: `CHANGELOG.md` (new)
       - Verify: `cat CHANGELOG.md` shows the release entry

- [ ] 23. Run `./check` and confirm zero failures and zero warnings
       - Run: `cd /home/user/Projects/aurelis-software-center && ./check`
       - Paste the full output into the plan or checkpoint document
       - Confirm: `ruff check` reports 0 warnings, `ruff format --check` reports 0 files would be reformatted, `pytest` reports 0 failures
       - If any failures or warnings, fix them before proceeding
       - Files: none (verification step)
       - Verify: `./check` output ends with "==> check passed"

**Requirements:** R29.2

**Dependencies:** Must be the last task; all other tasks must pass their verifications before running the final `./check`.

---

## Task 5.9: Phase 8 Final Checkpoint

**What:** Run `./check`, list performance results, list deferred items, and stop for owner review.

- [ ] 24. Run final `./check` and paste complete output
       - Run: `cd /home/user/Projects/aurelis-software-center && ./check 2>&1 | tee check-output.txt`
       - Paste the full output into this plan document or a separate artifact
       - Files: none (verification step)
       - Verify: Output shows "==> check passed" with 0 failures and 0 warnings

- [ ] 25. List every performance budget result measured
       - From Task 5.5 tests: catalog parse time, search keystroke time, Flathub FTS time, Pacman FTS time
       - Example:
         ```
         Performance Results:
         - Catalog parse (500 apps): 87 ms (budget: 100 ms) ✓
         - Search keystroke (500 apps): 42 ms (budget: 50 ms) ✓
         - Flathub FTS search: 89 ms (budget: 100 ms) ✓
         - Pacman FTS search: 76 ms (budget: 100 ms) ✓
         ```
       - Files: none (report in checkpoint output)
       - Verify: All budgets met

- [ ] 26. List any items deferred to a future release
       - Example:
         ```
         Deferred Items:
         - Task 5.3: Greek layout stress test (rationale: Qt layout managers auto-expand; manual testing sufficient for 1.0)
         - Task 5.7: PKGBUILD validation test (rationale: makepkg --nobuild already validates; version match check is manual)
         ```
       - Files: none (report in checkpoint output)
       - Verify: Rationale for each deferred item is documented

- [ ] 27. Stop for owner final review
       - Output: "Phase 8 complete. All tasks finished. Awaiting owner final review before tagging v1.0.0."
       - Files: none
       - Verify: No action; this is a workflow checkpoint

---

## Cross-File Dependencies

1. **5.2 → 5.3:** Greek `.qm` file must exist before running layout stress test (if not skipped).
2. **5.6 ↔ 5.8:** PKGBUILD `pkgver` must match `__version__` in `__init__.py` — can be done in parallel if coordinated, or 5.8 updates both.
3. **5.1-5.8 → 5.9:** All verification steps must pass before the final checkpoint.
4. **5.8 → 5.9:** Version bump and CHANGELOG must be committed before final `./check`.

---

## Verification Commands Summary

- **After each task:** Run the specific test or command listed in that task's "Verify:" line.
- **After all tasks:** Run `cd /home/user/Projects/aurelis-software-center && ./check` — must report 0 failures and 0 ruff warnings.
- **Manual verification:** Recommended to run the full app with Greek translation and manually test accessibility (Tab order, screen reader compatibility).

---

## Recommendations on Optional Tasks

- **Task 5.3 (Greek layout stress test):** **SKIP.** Qt's layout managers (QVBoxLayout, QHBoxLayout) automatically expand to fit text. Greek strings are ~10-30% longer than English, well within typical widget expansion. If clipping occurs during manual testing, we can add explicit `setMinimumWidth()` calls or add the stress test post-1.0. Skipping saves ~100 lines of test code and reduces maintenance burden.

- **Task 5.7 (PKGBUILD validation test):** **SKIP.** The `makepkg --nobuild` step in Task 5.6 already validates PKGBUILD syntax. The version-match assertion is a one-line manual check during release (`grep pkgver packaging/PKGBUILD` vs `grep __version__ src/aurelis_software/__init__.py`). Automating it requires pytest to invoke `makepkg`, which complicates CI. If version mismatches become a recurring problem, we can add the test in a patch release.

---

## Notes

- All file paths are absolute or relative to `/home/user/Projects/aurelis-software-center`.
- The `./check` script runs `ruff check`, `ruff format --check`, and `pytest` with `QT_QPA_PLATFORM=offscreen`.
- Ruff is configured in `pyproject.toml` with line-length 100 and strict linting rules; all warnings must be fixed.
- This is a **HEAVY** task spanning multiple subsystems (UI polish, i18n, a11y, performance, packaging). Estimated effort: 8-12 hours for a single developer.
- The plan is ordered by dependency; some tasks can run in parallel (5.2 + 5.4 + 5.5, for example).
- Greek translation (Task 5.2) requires fluency in Greek or access to a translation service; placeholder translations are acceptable for MVP if real translations are not feasible.

---

## Final Deliverable

When all tasks are complete:
1. `./check` passes with zero failures and zero warnings.
2. Version is bumped to `1.0.0` in all files.
3. `CHANGELOG.md` documents all phases 4-8.
4. Performance budgets are met and documented in `README.md`.
5. Greek translation is compiled and selectable in Settings.
6. Accessibility names are added to all interactive widgets.
7. PKGBUILD validates and installs `.desktop` files and icon.
8. Optional tasks (5.3, 5.7) are documented as deferred with rationale.
9. Owner reviews and approves for tagging v1.0.0.

---

**End of Plan**
