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

Both deferred items are **optional polish features** with **low risk** and **low user impact**. They were identified as "RECOMMENDED TO SKIP" in the implementation plan to accelerate MVP delivery.

The core functionality they would test is already covered by:
- Manual testing (layout)
- Existing tooling validation (makepkg)
- Release process verification (version checks)

If user-reported issues or development experience suggests these tests would provide value, they can be added in a future minor or patch release.
