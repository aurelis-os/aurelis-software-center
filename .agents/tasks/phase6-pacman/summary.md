# Phase 6: Pacman Integration - Implementation Summary

## Overview

Phase 6 successfully integrates Arch Linux package management (via pacman/pkgd) into the Aurelis Software Center. The implementation adds four core features (FEAT-001 through FEAT-004) that enable users to browse, search, install, and remove system packages through the GUI, with proper conflict detection and reboot notifications.

## Features Implemented

### FEAT-001: Pacman Output Parser (`pacman_parser`)
Pure Python parsers for pacman command output with no Qt or subprocess dependencies.

**Key capabilities:**
- `parse_si_output()`: Parses `pacman -Si` (package info from repos) into structured dicts
- `parse_qi_output()`: Parses `pacman -Qi` (installed package info) into structured dicts  
- `parse_qq_output()`: Parses `pacman -Qq` (installed package names list)
- Multi-value field handling: Properly splits fields like "Depends On", "Required By", "Provides" on double-space separators
- Handles "None" values and missing fields gracefully

**Files:**
- `src/aurelis_software/core/pacman_parser.py` (new, 169 lines)
- `tests/core/test_pacman_parser.py` (new, 127 lines)
- `tests/fixtures/pacman/si_output.txt` (new, fixture with 6 packages)
- `tests/fixtures/pacman/qi_output.txt` (new, fixture with 3 packages)
- `tests/fixtures/pacman/qq_output.txt` (new, fixture with 5 packages)

### FEAT-002: Pacman Package Index (`PacmanIndex`)
SQLite-backed search index with FTS5 (Full-Text Search) for fast package discovery.

**Key capabilities:**
- Builds index from `pacman -Si` output for all available packages
- FTS5 virtual table on `name` and `description` fields for prefix-based search
- Mtime-based rebuild detection: tracks `/var/lib/pacman/sync/*.db` modification times
- Batch insertion (100 records at a time) for performance
- Pure stdlib implementation (sqlite3, subprocess) - no Qt dependency
- Thread-safe: can run in worker thread without QApplication

**Files:**
- `src/aurelis_software/services/pacman_index.py` (new, 244 lines)
- `tests/services/test_pacman_index.py` (new, 206 lines)

### FEAT-003: PacmanBackend
Full Backend ABC implementation for Source.PACMAN following the established FlatpakBackend pattern.

**Key capabilities:**
- **Install/Remove operations**: All mutations via RPC to `aurelis-pkgd` daemon (never runs `pkg` as subprocess in production)
- **Package classification**: 
  - Locked: packages in `core-packages.json` (cannot be removed)
  - User: packages in `user-packages.json` (can be removed)
  - Dependency: installed but not in either list
- **Pending state tracking**: Detects packages queued for install/remove via pkgd queue
- **Conflict detection**: `remove()` checks "Required By" field via `pacman -Qi` and raises `ConflictPending` if user packages depend on the target
- **Graceful RPC fallback**: Imports `pacman_parser` inside functions, never at module level, so GUI loads even if RPC is unavailable
- **Operation lifecycle**: Returns Operations with progress reporting, follows Backend ABC contract

**Files:**
- `src/aurelis_software/backends/pacman.py` (new, 412 lines)
- `tests/backends/test_pacman.py` (new, 449 lines)

### FEAT-004: MainWindow Integration
Wires PacmanBackend and PacmanIndex into the existing GUI with proper user feedback.

**Key changes:**
- **Backend instantiation**: Creates `PacmanBackend` alongside `FlatpakBackend` in `__init__`
- **Index instantiation**: Creates `PacmanIndex` for package search
- **Installed app merging**: `_refresh_installed()` and `_refresh_pacman_installed()` merge pacman apps with flatpak apps
- **Pending reboot banner**: Shows `PendingRebootBanner` after successful pacman install/remove operations (queue changes take effect on next boot)
- **Conflict handling**: Catches `ConflictPending` errors and displays `QMessageBox.warning()` with package names that depend on the removal target
- **Error messages**: User-friendly explanations of pkgd queue semantics

**Files modified:**
- `src/aurelis_software/ui/main_window.py` (modified, +85 lines)
- `tests/ui/test_pacman_integration.py` (new, 137 lines)

## Architecture & Pattern Adherence

### Backend Pattern Match
PacmanBackend follows the established FlatpakBackend pattern:
- Same ABC contract (Backend interface)
- Same operation lifecycle (Operation class with work callback)
- Same error handling (ConflictPending for dependency conflicts)
- Same testability (injected CommandRunner and RPC client)

### Index Pattern Match
PacmanIndex follows the established FlathubIndex pattern:
- SQLite database with FTS5 search
- Incremental rebuild detection (FlathubIndex uses manifest hash, PacmanIndex uses sync .db mtimes)
- Pure stdlib, no Qt
- Thread-safe for background indexing

### RPC Safety (Critical)
All pacman_parser imports are **inside functions**, never at module level, ensuring graceful degradation when aurelis-pkgd is unavailable or user lacks wheel group membership. This prevents GUI crashes on systems where pkg/pkgd is not installed or accessible.

## Test Coverage

### New Test Files (4)
1. `tests/core/test_pacman_parser.py` - 11 test functions covering all parser functions
2. `tests/services/test_pacman_index.py` - 9 test functions covering index lifecycle
3. `tests/backends/test_pacman.py` - 15 test functions covering backend operations
4. `tests/ui/test_pacman_integration.py` - 3 integration tests covering MainWindow behavior

### Test Results
```
302 passed, 1 skipped in 210.56s (0:03:30)
```
- **Total tests**: 302 (up from original count)
- **Phase 6 tests**: ~38 new tests across 4 files
- **Fixture files**: 3 new fixtures in `tests/fixtures/pacman/`
- **All tests pass** with 0 ruff violations

### Test Strategy
- **Unit tests**: Each component (parser, index, backend) tested in isolation with mocks
- **Integration tests**: MainWindow tested with fake PacmanBackend to verify GUI wiring
- **Fixture-based**: Real pacman output captured in fixtures for parser tests
- **RPC mocking**: FakePkgdClient for testing backend without daemon dependency

## Code Quality

### Linting
```
==> ruff check
All checks passed!

==> ruff format --check
88 files already formatted
```
- Zero ruff violations
- All files formatted per project style
- Type hints throughout (PEP 484)
- Docstrings on all public functions (Google style)

### Documentation
- Comprehensive module docstrings explaining purpose and patterns
- Function docstrings with Parameters/Returns sections
- Inline comments for complex logic (FTS5 query sanitization, multi-value field parsing)
- Links to specs in test file headers (e.g., "Phase 6, FEAT-002")

## Integration Points

### Backend Registry
PacmanBackend is instantiated in `MainWindow.__init__` alongside FlatpakBackend:
```python
self._pacman_backend = PacmanBackend(...)
self._backends = [self._flatpak_backend, self._pacman_backend]
```

### Search Integration
PacmanIndex is used in MainWindow for package search via `search_pacman()` method, results merged with Flathub results in the GUI.

### Install/Remove Flow
1. User clicks Install/Remove button
2. MainWindow calls `backend.install(app)` or `backend.remove(app)`
3. PacmanBackend sends RPC to pkgd daemon (adds to queue)
4. Operation completes successfully
5. `PendingRebootBanner` shown (changes take effect on next boot)
6. If conflict detected, `ConflictPending` raised → `QMessageBox.warning()` displayed

## Verification Commands

### Final Verification (all passed)
```bash
./check
```
Output:
- ✅ ruff check: All checks passed
- ✅ ruff format --check: 88 files already formatted  
- ✅ pytest: 302 passed, 1 skipped in 210.56s

### Individual Commands
```bash
ruff check src/ tests/
ruff format --check src/ tests/
pytest tests/core/test_pacman_parser.py -v
pytest tests/services/test_pacman_index.py -v
pytest tests/backends/test_pacman.py -v
pytest tests/ui/test_pacman_integration.py -v
```

## Known Limitations

### 1. No Update Support
- `list_updates()` returns empty list
- Pacman repositories are pinned to Arch Linux Archive snapshot at build time
- Package updates only arrive via full OS updates (sysupdate/aurelis-update-app)
- This is **by design** per the pkg system architecture (see `docs/how-pkg-works.md`)

### 2. Queue Semantics
- Install/remove operations only **queue** changes, they don't apply immediately
- Changes take effect on next reboot via `aurelis-pkg-apply.service`
- PendingRebootBanner informs users, but behavior differs from Flatpak instant operations
- Queue state persists across sessions in `/var/lib/aurelis/pkg-queue.json`

### 3. RPC Dependency
- All mutations require `aurelis-pkgd.service` running
- User must be in `wheel` group or root
- If pkgd unavailable, GUI shows "Service unavailable" errors
- Read-only fallback: GUI can still show installed packages via direct `pacman -Qq` calls

### 4. Search Limitations
- FTS5 search is prefix-based (e.g., "fire" matches "firefox" but not "campfire")
- No stemming or fuzzy matching
- Special characters stripped from queries to prevent FTS5 syntax errors
- Rebuilds on every sync DB change (could be optimized with more granular tracking)

### 5. Conflict Detection Scope
- Only checks "Required By" field for direct dependents
- Does not check optional dependencies or reverse provides
- Relies on pacman -Qi output parsing (not using libalpm directly)

## Follow-up Work

### Potential Enhancements (out of scope for Phase 6)
1. **Background indexing**: Run PacmanIndex rebuild in worker thread on app startup
2. **Search ranking**: Weight exact name matches higher than description matches
3. **Dependency visualization**: Show full dependency tree before removal
4. **Queue management UI**: Dedicated tab to view/modify pending changes before reboot
5. **Progress reporting**: Stream pacman output during apply for detailed progress
6. **Error recovery**: Automatic retry for failed pre-downloads with exponential backoff
7. **Offline mode**: Cache package info for search when network unavailable

### Testing Gaps (acceptable for Phase 6)
- No end-to-end tests with real pkgd daemon
- No performance tests for large package counts (10k+ packages)
- No tests for concurrent queue modifications
- No tests for partial pacman output (truncated/malformed)

## References

### Specifications
- `.kiro/specs/aurelis-software-p4-p8/phase6-pacman.md` - Phase 6 requirements
- `docs/how-pkg-works.md` - Comprehensive pkg/pkgd behavior documentation

### Design Documents
- `.agents/tasks/phase6-pacman/verdict.json` - Final review approval

### Key Dependencies
- `aurelis_common.rpc.PkgdClient` - RPC client for pkgd communication
- `aurelis_common.paths.Paths` - System path constants
- PyQt6 - GUI framework
- sqlite3 - FTS5 search index

---

**Implementation Date**: November 2024  
**Review Status**: APPROVED (verdict.json, iteration 1)  
**Final Verification**: ✅ All checks passed (./check)  
**Commit**: Ready for final commit with message "docs: add Phase 6 implementation summary"
