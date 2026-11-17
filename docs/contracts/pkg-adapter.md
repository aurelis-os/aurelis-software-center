# pkg adapter contract (spec 9.2)

STATUS: every item below is `OPEN`. The owner will answer 9.2 later (decision recorded in
`docs/DECISIONS.md`). This file is the placeholder adapter spec to be filled in with the owner
before Phase 6. Do not guess values.

`pkg` is the pacman wrapper; add/remove take effect on the next reboot (spec 8.3, 14).

## Needed by the GUI (all OPEN)

| # | Question | Status |
|---|----------|--------|
| 1 | install command and arguments (e.g. `pkg install <pkg>`)? | OPEN |
| 2 | remove command and arguments (e.g. `pkg remove <pkg>`)? | OPEN |
| 3 | install/remove exit codes and their meanings? | OPEN |
| 4 | machine-readable list of pending changes (installs and removals)? command + output format? | OPEN |
| 5 | way to cancel a pending change? command? | OPEN |
| 6 | does `pkg` need privileges (polkit/pkexec)? how should the GUI invoke it? | OPEN |
| 7 | is there `pkg update`? what does it list? how are updates staged? | OPEN |
| 8 | pending changes persist across reboot — where does `pkg` store them (GUI must not own a file)? | OPEN |
| 9 | error output format (stderr tail) for mapping to `core/errors.py`? | OPEN |

## Phase 6 entry point
Phase 6 starts by writing this adapter spec with the owner (P6.1), then implements
`backends/pacman.py` against it.
