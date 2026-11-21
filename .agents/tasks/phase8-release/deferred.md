# Deferred Items for Post-1.0 Release

## Task 5.3: Greek Layout Stress Test (OPTIONAL)

**Status:** DEFERRED

**Rationale:**  
Qt's layout managers (QVBoxLayout, QHBoxLayout) automatically expand to fit text content. Greek strings are typically 10-30% longer than English, which is well within the typical widget expansion range. Manual testing during the release cycle did not reveal any clipping issues.

**Risk Assessment:** Low  
- Qt layout system prevents most clipping by default
- Greek translation is complete and compiled
- Manual testing shows no visible layout problems

**Future Action:**  
If clipping issues are reported by users, we can:
1. Add explicit `setMinimumWidth()` calls to affected widgets
2. Implement the automated stress test for regression prevention
3. Add the test as part of a patch release (e.g., 1.0.1 or 1.1.0)

**Estimated Effort:** ~100 lines of test code + maintenance overhead

---

## Task 5.6: Application Icon File (PKGBUILD Installation)

**Status:** DEFERRED

**Rationale:**  
PKGBUILD includes commented-out icon installation line. Creating a proper application icon (aurelis-software.png or .svg) requires graphic design work, which is outside the scope of the coding-agent tasks. The .desktop file specifies `Icon=aurelis-software`, which will resolve to a system fallback icon (typically a generic application icon) until a branded icon is provided.

**Risk Assessment:** Low  
- Application is fully functional without a custom icon
- .desktop files are correctly installed and validated
- Icon field follows XDG Desktop Entry Specification
- System will show a fallback icon (no broken images)

**Future Action:**  
Once a proper icon file is created:
1. Place the icon file in `resources/` (128x128 PNG or scalable SVG)
2. Uncomment the icon installation line in PKGBUILD:
   ```bash
   install -Dm644 resources/aurelis-software.png \
       "$pkgdir/usr/share/icons/hicolor/128x128/apps/aurelis-software.png"
   ```
3. Optionally add icon to git repository
4. Release as patch or minor version update

**Estimated Effort:** Graphic design work (external) + ~5 minutes to uncomment PKGBUILD line

---

## Task 5.7: PKGBUILD Validation Test (OPTIONAL)

**Status:** DEFERRED

**Rationale:**  
The `makepkg --nobuild` step in Task 5.6 already validates PKGBUILD syntax. The proposed test would:
1. Run `desktop-file-validate` on .desktop files (already covered by makepkg warnings)
2. Compare `pkgver` in PKGBUILD to `__version__` in `__init__.py` (one-line manual check during release)

Automating this test requires pytest to invoke `makepkg`, which:
- Adds an external dependency (makepkg) to the test suite
- Complicates CI and local dev environments on non-Arch systems
- Provides minimal value over manual verification

**Risk Assessment:** Low  
- PKGBUILD syntax is validated by makepkg
- Version mismatch is easily caught during release preparation
- Manual grep check takes ~5 seconds

**Future Action:**  
If version mismatches become a recurring problem across multiple releases, we can:
1. Add a simple Python script to check version consistency
2. Run it as a pre-release checklist item
3. Optionally integrate into CI for Arch-based build environments

**Estimated Effort:** ~50 lines of test code + CI integration complexity

---

## Summary

All deferred items are **optional polish features** with **low risk** and **low user impact**. They were identified as "RECOMMENDED TO SKIP" or outside coding scope in the implementation plan to accelerate MVP delivery.

The core functionality they would test is already covered by:
- Manual testing (layout)
- Existing tooling validation (makepkg)
- Release process verification (version checks)
- System fallback icons (icon installation)

If user-reported issues or development experience suggests these items would provide value, they can be added in a future minor or patch release.
