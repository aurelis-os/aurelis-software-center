# Changelog

All notable changes to the Aurelis Software Center will be documented in this file.

## [1.0.0] - 2025-01-XX

### Added

**Phase 4: AppImage Update Support**
- AppImage update support with zsync delta downloads
- Update policies: automatic, manual (ask me), and pinned
- Undo/revert functionality for AppImage updates
- Previous version management with cleanup

**Phase 5: Flathub Integration**
- Flathub integration with FTS5 full-text search
- Lazy pagination for large app catalogs
- Metadata refresh and remote configuration
- AppStream parsing and indexing

**Phase 6: Pacman Integration**
- Pacman package manager integration via pkg daemon
- Package classification: locked/user/dependency
- Reverse-dependency warnings before removal
- Pending reboot banner for queued operations

**Phase 7: Install and Uninstall Wizards**
- Install wizard for AppImage and Flatpak files
- File association handlers for .AppImage and .flatpakref
- Uninstall wizard with daemon detection
- Trash support for removed applications

**Phase 8: Polish and Release**
- Polished Explore page with "Recently updated" section
- Per-category horizontal scroll rows in Explore
- Greek translation (el) with language selector in Settings
- Accessibility names for all interactive UI elements
- WCAG AA contrast verification for badge colors
- Performance tests with sub-100ms budgets
- Arch Linux packaging (PKGBUILD with .desktop files)

### Changed
- Explore page layout now features distinct sections for discovery
- Settings dialog includes language selector

### Performance
- Catalog parse (500 apps): < 100 ms
- Search keystroke (500 apps): < 50 ms
- Flathub FTS search: < 100 ms
- Pacman FTS search: < 100 ms

## [0.1.0] - 2024-XX-XX

### Added
- Initial development versions (Phases 0-3)
- Basic catalog integration
- AppImage backend foundation
- Core UI structure with Explore, Installed, Updates pages
- Search functionality
- Detail page with install/remove actions

---

[1.0.0]: https://github.com/aurelis/aurelis-software-center/releases/tag/v1.0.0
[0.1.0]: https://github.com/aurelis/aurelis-software-center/releases/tag/v0.1.0
