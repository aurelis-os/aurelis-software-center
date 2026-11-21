# Performance Test Results

## Test Environment
- Platform: Linux (Arch-based)
- Python: 3.11+
- PyQt6: 6.6+
- Date: 2025-01-XX

## Results

All performance budgets were met:

| Test | Result | Budget | Status |
|------|--------|--------|--------|
| Catalog parse (500 apps) | < 100 ms | 100 ms | ✓ PASS |
| Search keystroke (500 apps) | < 50 ms | 50 ms | ✓ PASS |
| Flathub FTS search | < 100 ms | 100 ms | ✓ PASS |
| Pacman FTS search | < 100 ms | 100 ms | ✓ PASS |

## Notes

- Tests run in offscreen Qt mode for consistency
- Catalog parse test uses synthetic JSON data
- FTS tests use minimal fixtures
- All tests include index building time where applicable
