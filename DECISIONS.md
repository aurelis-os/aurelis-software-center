# Decisions Log

## 2026-11-18: App Icons as Placeholders

**Decision**: App icons are currently placeholders until Phase 4.

**Reason**: Phase 3 focuses on UI flows, error states, and screenshot generation. Full icon handling (downloading, caching, fallback generation) is scheduled for Phase 4. Current screenshots use extracted icons from the test fixture `app-icons.tar.gz` which provides a limited set of icons for testing purposes.

**Impact**: Screenshots in `docs/screenshots/phase3/` show placeholder icons for apps not in the fixture. Phase 4 will implement proper icon downloading, caching, and fallback generation.

---