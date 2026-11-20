# Decisions Log

## 2026-11-18: App Icons as Placeholders

**Decision**: App icons are currently placeholders until Phase 3.

**Reason**: Phase 3 focuses on UI flows, error states, and screenshot generation. Full icon handling (downloading, caching, fallback generation) was implemented in Phase 3 (P2.2). Current screenshots use extracted icons from the test fixture `app-icons.tar.gz` which provides a limited set of icons for testing purposes.

**Impact**: Screenshots in `docs/screenshots/phase3/` show placeholder icons for apps not in the fixture. Phase 4 implements updates.

---

## 2026-11-19: Missing Origin Version = Unknown

**Decision**: If an installed app's origin dict lacks a `version` key, treat it as "unknown" — do not report an update based on version comparison alone. However, sha256 differences and `version_changed_at` (for "latest" versions) still trigger updates.

**Reason**: The origin dict is written at install time and should always contain the version. If it's missing (e.g., manually linked apps, older daemon data), we cannot reliably compare versions. The spec says to "treat missing version as 'unknown', fall back to comparing with the installed version from the daemon" — in practice, we skip version comparison and only check sha256/changed_at.

**Impact**: `update_available()` in `core/versions.py` checks `origin_version is not None` before comparing. This prevents false positives when origin has no version.

---

## 2026-11-19: P4.2 Acceptance - Real Delta Update Test

**Decision**: run one real delta update against a real zsync_url on Aurelis

**Reason**: The P4.2 implementation of zsync delta downloads with stall timeout, cancel, and fallback to full download has been verified with comprehensive unit tests using a fake zsync. The acceptance criteria requires testing against a real zsync_url on the Aurelis infrastructure to validate the complete integration.

**Impact**: This will be performed as part of the P4.3 integration testing phase.