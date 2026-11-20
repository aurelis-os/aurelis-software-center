# pkg: owner's answers for the Software Center GUI

> **⚠️ HISTORICAL DOCUMENT (November 2026)**
>
> This file documents the package manager behavior based on the original scattered
> implementation in `overlay/`. The pkg system has been **migrated to a standalone
> project** at `aurelis-pkg-app/` with comprehensive tests and documentation.
>
> **For current documentation, see:**
> - `aurelis-pkg-app/docs/README.md` — Developer guide and getting started
> - `aurelis-pkg-app/docs/architecture.md` — System design and components
> - `aurelis-pkg-app/docs/protocol.md` — Complete RPC protocol specification
>
> **The information below is preserved for historical reference.** It remains
> accurate for the behavior and API contract, but file paths have changed:
> source code is now in `aurelis-pkg-app/src/aurelis_pkg/`, built by the
> `step_build_pkg_app()` function in the build script.

---

Answers to section 9.2 of the Software Center spec. Every statement comes from the code in this repo.

**Verification status (read first).** The shell tool in the session that wrote this file returned no output for any command. So **no command was executed**: no `pkg --help`, no captured output, no test run, no `git status`. All examples below are *constructed from the `print()` calls and JSON handlers in the source*, not captured from a running system. Exit codes are derived from the code paths. Before Phase 6 ships, run the examples once on a preview VM to confirm them.

Source locations are cited as `file:line`. Paths are relative to the repo root. Line numbers are those at the time of writing.

| Short name | Original File (now migrated) | Current Source |
|---|---|---|
| CLI | `overlay/common/usr/bin/aurelis-pkg` | `aurelis-pkg-app/src/aurelis_pkg/cli.py` |
| Daemon | `overlay/common/usr/lib/aurelis/aurelis-pkgd` | `aurelis-pkg-app/src/aurelis_pkg/daemon.py` |
| RPC client | `aurelis-common/aurelis_common/rpc.py` (`PkgdClient`) | (unchanged) |
| Paths | `aurelis-common/aurelis_common/paths.py` | (unchanged) |
| Apply unit | `overlay/common/usr/lib/systemd/system/aurelis-pkg-apply.service` | `aurelis-pkg-app/systemd/aurelis-pkg-apply.service` |

---

## 0. What `pkg` is and how it works

`pkg` is **not** a wrapper that runs pacman directly. It is a thin client for a root daemon, `aurelis-pkgd`, which runs pacman.

- CLI → JSON-RPC 2.0 over the Unix socket `/run/aurelis-pkgd.sock` → daemon (CLI `_rpc`, line 41; `paths.py:82`).
- Package source is an Arch Linux Archive snapshot pinned at build time (`/usr/lib/aurelis/pacman-ala.conf`, rendered in `build:565-574`). pacman runs with `SigLevel = Never` (daemon `_build_pacman_conf_siglevel_never`).
- The root filesystem is A/B Btrfs (`@root_a`, `@root_b`). A package change never touches the running slot. It is applied to a clone of the active slot (the inactive slot), which then becomes the boot target.

**Model: queue, then apply during the next boot, then an automatic second reboot.**

1. `pkg add` / `pkg remove` only record the change in the queue (and `pkg add` pre-downloads the packages). Nothing is installed or removed yet.
2. The user reboots. Early in that boot, `aurelis-pkg-apply.service` runs `pkg apply` behind a full-screen splash. `pkg apply` clones the active slot, runs pacman in the clone, validates it, and marks the clone `trial` and active.
3. On success the splash runs `systemctl reboot` automatically. The new packages are live after this **second** boot.

So "takes effect on next reboot" means: the next reboot starts the apply, and the system reboots again by itself. The user sees one long boot with a splash and one extra reboot.

### State and files

| What | Path | Notes |
|---|---|---|
| Queue document | `/var/lib/aurelis/pkg-queue.json` | `paths.py:67`. Absent when the queue is empty (daemon `_write_queue_doc`, `aurelis-pkgd:611`). Written by the daemon's `_atomic_write` (`aurelis-pkgd:348`) via `tempfile.mkstemp`, so mode 0600, root only. The GUI cannot read it directly. |
| Pre-downloaded packages | `/var/cache/aurelis/pkg/pending/` | `paths.py:77`. Deleted by `pkg queue clear`. |
| Apply resume downloads | `/var/cache/aurelis/pkg/resume-<hash>/` | Used only when the pending cache is incomplete at apply time. |
| Last-apply record | `/var/lib/aurelis/pkg-pending.json` | `paths.py:69`. **Not the queue.** See section 2. |
| User package selections | `/var/lib/aurelis/user-packages.json` | `paths.py:68`. Only these can be removed with `pkg remove`. |
| Slot state | `/var/lib/aurelis/slot-state.json` | `paths.py:66`. |
| Socket | `/run/aurelis-pkgd.sock` | Mode 0660, owner `root:wheel` (`aurelis-pkgd:2120-2125`). |
| Core package list | `/usr/lib/aurelis/core-packages.json` | Packages that `pkg` refuses to add or remove. |

### What applies the queue at boot

`aurelis-pkg-apply.service` (`aurelis-pkg-apply.service:1-33`):

- `ConditionPathExists=/var/lib/aurelis/pkg-queue.json`: the unit is skipped if no queue file exists.
- `Before=plasmalogin.service display-manager.service`, `Requires=aurelis-pkgd.service seatd.service`.
- `ExecStart=/usr/lib/aurelis/pkg-apply-with-splash`, `TimeoutStartSec=600`, `SuccessExitStatus=1`.
- Enabled through `graphical.target.wants` (`build:1046-1049`).

`pkg-apply-with-splash` (`overlay/common/usr/lib/aurelis/pkg-apply-with-splash`) runs the splash under `cage`. The splash (`pkg-apply-splash`) runs `/usr/bin/pkg apply`, then `systemctl reboot` on success. On failure it shows an error for 8 seconds and exits 1 without rebooting. If `cage` exits non-zero, the wrapper runs `/usr/bin/pkg apply` headless and then `pkg-apply-reboot-if-needed`, which reboots only if the queue file is gone.

---

## 1. Install / remove commands and exit codes

### Syntax

```
pkg add    PACKAGE...        # queue installs
pkg remove PACKAGE...        # queue removals
```

(There is no `pkg install`. `docs/user-guide.md` once documented it; that was defect R9.) No flags exist. An argument beginning with `-` is sent as a package name and rejected as invalid.

RPC equivalents: `pkg.install` and `pkg.remove`, params `{"packages": ["name", ...]}` (`aurelis-pkgd:1440`, `1506`).

### Exit codes (CLI)

The CLI has only two outcomes: 0, or 1 for every error (`_rpc` and `_die`, CLI lines 41-55).

| Exit | Meaning |
|---|---|
| 0 | The daemon accepted the request. This includes "nothing was queued" cases: package is core, already installed, already queued, or a removal was cancelled. Read stdout (or the RPC result) to see which. |
| 1 | No package arguments (`Usage: pkg add PACKAGE...`). |
| 1 | Daemon unreachable: `error: aurelis-pkgd is not running` / `refused connection` / `connection failed: ...` (`rpc.py:80-92`). A user outside `wheel` gets `connection failed: [Errno 13] Permission denied`. |
| 1 | The daemon returned a JSON-RPC error (table below). |
| 1 | Client timeout after 600 s (`PkgdClient` default, `rpc.py:62`): `connection failed: timed out`. **The daemon may still have queued the change.** See "Gotchas". |

Daemon errors that surface as exit 1 with `error: <message>` on stderr (`aurelis-pkgd` lines in brackets):

| Command | Message (starts with) | Cause |
|---|---|---|
| add / remove | `Invalid package name: ...` | Not matching `^[a-zA-Z0-9@._+][a-zA-Z0-9@._+\-]*$` [`_validate_packages`] |
| add / remove | `package name ... contains characters outside lowercase letters, ...` / `exceeds 64 characters` | Queue rule: `[a-z0-9+._-]+`, at most 64 chars [`_validate_queue_name`, 651] |
| add | `Package not found: <name>` | Not in the pinned repos (`pacman -Si` fails) [`_verify_package_exists`] |
| add | `queue is full (512 entries); ...` | `MAX_QUEUE_ENTRIES` [`_upsert_entry`, 727] |
| remove | `Package(s) not in user selections: <names>` | Package is not in `user-packages.json` and not queued for install [`_handle_remove`] |
| any | `legacy state/cache migration did not complete: ...` (code -32002) | Daemon start-up migration failed |

A request with several packages is **all or nothing**: validation errors are raised before the queue is written, so no entry is added if any name is rejected.

### stdout / stderr behaviour

- Errors go to stderr as `error: <message>`. **Colour codes are emitted unconditionally** (CLI constants at lines 21-26, no `isatty` check). Do not parse CLI output; use the RPC (section 6).
- `pkg add` prints one progress line to stderr first: `  … Resolving and downloading <names> (large packages can take several minutes)`.
- Result lines go to stdout.

### Result fields (RPC)

`pkg.install` result (`aurelis-pkgd:1496-1502`):

| Field | Meaning |
|---|---|
| `queued` | Names newly added to the queue by this call |
| `core` | Names refused because they are core system packages |
| `already_installed` | Names already installed in the active slot (not queued) |
| `removal_cancelled` | Names that were already installed and had a queued removal; the removal was dropped |
| `queue` | Whole queue after the call: `{"install": [...], "remove": [...]}` |

A requested name that is in none of the four lists was already queued (the CLI prints "is already queued").

`pkg.remove` result (`aurelis-pkgd:1537-1541`): `queued`, `install_cancelled`, `core`, `queue`. 
- `queued`: Names newly queued for removal by this call
- `install_cancelled`: Names that were queued for install and have been removed from the queue
- `core`: Names refused because they are core system packages
- `queue`: Whole queue after the call

A name not in any of these lists was already queued for removal. The CLI also checks the keys `not_installed` and `not_removable` (CLI lines 115-120), but **the daemon never returns them**; that CLI code is dead. A package that is neither installed nor queued for install is an error (exit 1), not a list entry.

### Example (constructed from the code, not captured)

```
$ pkg add htop
  … Resolving and downloading htop (large packages can take several minutes)     <- stderr
  +  htop queued.                                                                  <- stdout

  + add:    htop

  Changes will be applied automatically on next boot.
$ echo $?
0

$ pkg add nosuchpkg
error: Package not found: nosuchpkg                                                <- stderr
$ echo $?
1
```

### Behaviour the GUI must know

- `pkg add` for a package that is already installed does **not** queue it unless that package is queued for removal (in which case it cancels the removal).
- `pkg remove` cancels queued installs for not-yet-installed packages, or queues removal for installed packages. A base-system package that is not in the core list is still refused (`not in user selections`) unless it's queued for install.
- `pkg add` pre-downloads the package and dependencies before it replies. If that download fails, the failure is only logged (`aurelis-pkgd:1486-1488`): **the command still exits 0 and the package stays queued**. The boot-time apply then downloads it with a 300 s budget (`PAYLOAD_TIMEOUT_SEC`, line 94).
- Queue changes from `add` and `remove` are not serialized by a lock in the daemon (`_handle_install`/`_handle_remove` do not take `_op_lock`). The GUI should send queue-changing calls one at a time.

---

## 2. Machine-readable list of pending changes (install and remove)

### Command

There is **no CLI command that prints JSON.** `pkg queue` prints coloured human text only. The machine-readable source is the RPC method **`pkg.queue`** (or the `queue` field of `pkg.status`).

```python
from aurelis_common.rpc import PkgdClient

queue = PkgdClient().queue()["queue"]  # {"install": [...], "remove": [...]}
```

`aurelis_common` is importable system-wide through the image's `aurelis-common.pth` (comment at `aurelis-pkgd:34-37`). The RPC client's own docstring names the planned software GUI as an intended user (`rpc.py:3-7`).

### Raw wire format

One request per connection, newline-terminated, one newline-terminated reply, then the daemon closes the connection (`_handle_connection`, `aurelis-pkgd:2080`).

```
-> {"jsonrpc": "2.0", "id": 1, "method": "pkg.queue", "params": {}}\n
<- {"jsonrpc": "2.0", "id": 1, "result": {"queue": {"install": ["htop", "vim"], "remove": ["firefox"]}}}\n
```

### Schema of `pkg.queue` result

| Field | Type | Meaning |
|---|---|---|
| `queue.install` | array of string | Package names queued for install, in queue order |
| `queue.remove` | array of string | Package names queued for removal, in queue order |

Names only. No versions, sizes, or timestamps are exposed over RPC.

### Nothing pending

Both lists are empty (`aurelis-pkgd:1546-1548`, `_queue_summary` at 631):

```
<- {"jsonrpc": "2.0", "id": 1, "result": {"queue": {"install": [], "remove": []}}}
```

Detect with `not (q["install"] or q["remove"])`. On disk, an empty queue means the file `/var/lib/aurelis/pkg-queue.json` does not exist (`_write_queue_doc`, line 611).

### CLI text (for humans only)

```
$ pkg queue                       # items pending
Pending changes:
  + add:    htop, vim
  - remove: firefox

$ pkg queue                       # nothing pending
  No pending changes.
```

Both exit 0. The text carries ANSI colour codes.

### Do not confuse: `pkg pending` is not the queue

`pkg pending` (RPC `pkg.pending`) returns the record of the **last apply attempt**, not queued changes. Its name is misleading for a GUI.

- No apply in flight or failed: `{}`. CLI prints `No pending package operation.`
- Apply running, or the last apply failed (`aurelis-pkgd:514`, schema at 526-540):

```json
{
  "schema_version": 1,
  "op": "apply",
  "packages": ["htop", "firefox"],
  "started_at": "2026-11-12T09:30:00Z",
  "state": "failed",
  "target_slot": "b",
  "error": "core-guard: Transaction would affect protected core packages: ..."
}
```

`state` is `in_progress` while an apply runs and `failed` afterwards (the record is kept so `pkg status` can report it). `target_slot` and `error` (`<stage>: <message>`) are present on failure. The record is removed after a successful apply, and also when an apply finds nothing to do.

### Single call for a GUI poll: `pkg.status`

`pkg.status` (`aurelis-pkgd:1841`) returns everything the Software Center needs in one round trip:

```json
{
  "active_slot": "a",
  "slot_a": {"status": "good", "version": "2026.10.28", "boot_attempts": 0},
  "slot_b": {"status": "empty", "version": "", "boot_attempts": 0},
  "user_packages": ["htop", "vim"],
  "pending": {},
  "queue": {"install": ["gimp"], "remove": ["vim"]}
}
```

- `user_packages`: names of packages the user installed (the only ones removable).
- `pending`: the apply record described above (`{}` when none).
- `queue`: the queued changes.

Slot `status` values seen in code: `good`, `trial`, `empty`, `failed`.

---

## 3. Cancelling a pending change

### Commands

| Goal | Command | RPC |
|---|---|---|
| Cancel **everything** pending | `pkg queue clear` | `pkg.queue_clear` |
| Cancel one queued **removal** | `pkg add NAME` (for an installed package) | `pkg.install` → `removal_cancelled` |
| Cancel one queued **install** | `pkg remove NAME` (for a queued package) | `pkg.remove` → `install_cancelled` |

### `pkg queue clear`

- Deletes `/var/lib/aurelis/pkg-queue.json` and the whole `/var/cache/aurelis/pkg/pending/` directory (`_clear_queue`, `aurelis-pkgd:621`; `_handle_queue_clear`, 1550).
- Always succeeds when the daemon is reachable, **including when nothing was pending**. There is no "nothing to cancel" error and no way to distinguish the two cases from the exit code.
- stdout: `  ~  Queue cleared.` (carries colour codes). RPC result: `{"cleared": true}`.
- Does not touch `pkg-pending.json` (a failed-apply record stays).
- Does not take the apply lock. Do not call it while an apply is running.

| Exit | Meaning |
|---|---|
| 0 | Cleared (or was already empty) |
| 1 | Daemon unreachable, permission error, or daemon error (same table as section 1) |

### Cancelling a single queued removal

`pkg add firefox` where firefox is installed and has a queued removal drops the removal entry. The result lists it in `removal_cancelled`; the CLI prints `~  firefox removal cancelled (removed from queue).` (`_handle_install`, `aurelis-pkgd:1465-1471`). Exit 0.

### Cancelling a single queued install

`pkg remove firefox` where firefox is queued for install but not yet installed drops the install entry. The result lists it in `install_cancelled`; the CLI prints `~  firefox install cancelled (removed from queue).` (`_handle_remove`, `aurelis-pkgd:1519-1521`). Exit 0.

This allows users to change their mind before rebooting:
- `pkg add nnn && pkg add micro && pkg remove nnn` → only `micro` will be installed after reboot
- `pkg remove vim && pkg add vim` → `vim` removal is cancelled, stays installed after reboot

### Symmetry between add and remove

Both `pkg add` and `pkg remove` check the queue for opposing operations and cancel them:
- `pkg add` cancels queued **removals** (for installed packages)
- `pkg remove` cancels queued **installs** (for not-yet-installed packages)

This creates a draft-like workflow where queue changes can be undone before applying them at next boot.

---

## 4. Privileges and how the GUI should invoke `pkg`

### Short answer

**No `pkexec`, no polkit, no root needed.** Run `pkg` (or the RPC client) as the logged-in user. The user must be in the **`wheel`** group (or be root).

### How authorization works

1. The socket `/run/aurelis-pkgd.sock` is created `0660 root:wheel` (`aurelis-pkgd:2120-2125`). A user outside `wheel` cannot even `connect()` (error 13).
2. The daemon also checks the peer's credentials with `SO_PEERCRED` and accepts uid 0, primary group `wheel`, or `wheel` in the supplementary groups (`_is_authorised`, `aurelis-pkgd:2059-2077`). A refusal returns JSON-RPC code `-32001`, `Permission denied`. In practice the socket permissions stop a non-wheel user first.
3. The daemon itself runs as root (`aurelis-pkgd.service`; it exits with `aurelis-pkgd must run as root` otherwise).

`docs/user-guide.md:283` says the same ("requires membership of the `wheel` group (or root)"). The first user is created in `wheel` by `aurelis-postinstall-app/core/system.py:286`.

### Read-only commands

`pkg list`, `search`, `info`, `status`, `queue`, `pending` use the **same socket and the same authorization** as `add`/`remove`. They need `wheel` too. There is no unprivileged read path. The state files under `/var/lib/aurelis/` should not be read directly (queue file is 0600).

### polkit

No polkit action, `.policy` file, or `rules.d` rule for `pkg` exists in this repo (searched the whole tree, excluding `build-dir/`). polkit is installed only as a base package for the KDE auth agent (`packages.x86_64:73-75`). A GUI cannot ask for a polkit prompt to run `pkg`, because nothing is registered.

### Recommended GUI invocation

Preferred: use the RPC client directly (no subprocess, no ANSI parsing, structured errors):

```python
from aurelis_common.rpc import PkgdClient, PkgdError, PkgdDownError

c = PkgdClient()  # socket /run/aurelis-pkgd.sock, 600 s timeout
c.install(["htop"])  # pkg add
c.remove(["vim"])  # pkg remove
c.queue()  # {"queue": {...}}
c.queue_clear()  # pkg queue clear
c.status()  # pkg status data
```

`PkgdDownError` means the daemon could not be reached or the socket refused the connection. `PkgdError` carries the daemon's `code` and `message`.

Fallback: `argv = ["/usr/bin/pkg", "add", "htop"]` (no shell, no `pkexec`, no env vars required). Parse only the exit code and stderr text, and strip ANSI escapes.

### If someone wraps `pkg` in `pkexec` anyway

Not recommended, and not tested here. With no policy installed, `pkexec` would fall back to polkit's default `exec` action, which asks for an administrator password. General `pkexec(1)` behaviour (from its man page, not from this repo): exit 126 when the user dismissed the authentication dialog, 127 when not authorized or on error; otherwise the program's own exit code.

### Run-time environment

- No environment variables are read by `pkg` or `aurelis-pkgd` for configuration (paths are constants in `paths.py`; there is no queue-directory override).
- `aurelis-pkgd.service` must be running (enabled in `multi-user.target` by `build`).

---

## 5. How updates are staged

### Is there `pkg update`?

**No.** `pkg` has no `update`, `upgrade`, or `sync` command. The command table is `_COMMANDS` in the CLI (lines 260-270): `add`, `remove`, `queue`, `apply`, `list`, `search`, `info`, `status`, `pending`. There is no RPC method for it either (`_HANDLERS`, `aurelis-pkgd:2001-2013`).

### Why

All repositories are pinned to one Arch Linux Archive snapshot chosen at build time (`pacman-ala.conf`). Package versions for a given Aurelis release cannot change independently. Newer versions arrive only with a **new OS release**.

### What exists instead

| Mechanism | What it does | Staged for reboot? | Machine-readable? |
|---|---|---|---|
| `sysupdate ARCHIVE` (`overlay/common/usr/bin/sysupdate`; root only) and `aurelis-update-app` | Deploys a full OS image to the inactive slot, marks it `trial`, then calls `pkg.reapply_user_packages` to re-install the user's selections into it (`update_engine.py:895-910`, `967-991`). | Yes. Activated on the next reboot. | No. Text output; exit 0 / 1 / 2 (`sysupdate:136-152`). |
| `pkg.reapply_user_packages` (RPC, called by the update engine) | Returns `{"reapplied": [names], "skipped": [{"name", "reason"}], "inactive_slot": "a"\|"b"}` (`aurelis-pkgd:1945`). Skipped packages stay in the user's selection list. | Part of the OS update. | Yes, JSON, but meant for the update engine, not a GUI. |
| `sysupdate --status` | Prints both slots' status, version and boot attempts. | n/a | No. Text. |

An "updates available" list for user packages **does not exist**.

### The nearest equivalent for a GUI

- Installed packages and versions: `pkg list` (RPC `pkg.list`) returns `{"packages": [{"name": "htop", "version": "3.3.0-1"}, ...]}`. This is every package in the active root, **including core**. Filter with `user_packages` from `pkg.status` for the user's own.
- Slot and "update applied, reboot needed" indicators: `pkg.status` → `slot_*.status`.

---

## 6. Machine-readable output: summary

| Need | Source | Format |
|---|---|---|
| Queued installs and removals | RPC `pkg.queue` (or `pkg.status.queue`) | JSON object `{"queue": {"install": [...], "remove": [...]}}` |
| Nothing pending | Same call | Both arrays empty |
| Last apply failed / running | RPC `pkg.pending` (or `pkg.status.pending`) | JSON object, `{}` when none |
| User-installed packages | RPC `pkg.status.user_packages` | array of string |
| All installed packages | RPC `pkg.list` | `{"packages": [{"name", "version"}]}` |
| Search results | RPC `pkg.search` | `{"results": "<raw pacman -Ss text>"}`: a single text blob, not structured |
| Package details | RPC `pkg.info` | `{"info": "<raw pacman -Si text>"}`: a single text blob |
| CLI output | any `pkg` command | Human text with ANSI colour. **Not stable for parsing.** |

JSON-RPC error codes (`_dispatch`, `aurelis-pkgd:2020-2055`; `_is_authorised`):

| Code | Meaning |
|---|---|
| -32700 | Request is not valid JSON |
| -32601 | Unknown method |
| -32000 | Expected failure (`ValueError`/`RuntimeError`): bad name, not found, not a user selection, apply refused, and so on. `message` is the text shown by the CLI. |
| -32603 | Unexpected daemon exception |
| -32001 | Permission denied (peer not root/wheel) |
| -32002 | Start-up migration failed; all requests refused |

Other limits: request size is capped at 65536 bytes (`MAX_MSG_BYTES`); a larger request is closed with no reply, which `PkgdClient` reports as `PkgdDownError`.

### Other commands the GUI may use

| Command | RPC | Exit codes | Notes |
|---|---|---|---|
| `pkg apply` | `pkg.apply` | 0 on success, and also 0 with `queue is empty` or `all queued packages are already installed`; 1 on any error | Not listed in `pkg --help`, but implemented (`_COMMANDS`). Applies the queue **now** to the inactive slot (minutes). Does not reboot; the CLI prints `Reboot to activate changes.` Refused with `A previous transaction is pending reboot` while the active slot is `trial`, and with `An apply or update operation is already in progress` when the lock is held. Result: `{"applied": bool, "installed": [...], "removed": [...], "inactive_slot": "a"\|"b"}` or `{"applied": false, "reason": "..."}`. |
| `pkg status` | `pkg.status` | 0; **1** if the last apply failed or neither slot is bootable (output is still printed) | Via RPC you always get the data and decide yourself. |
| `pkg list`, `search`, `info`, `pending` | as named | 0, or 1 on error | |
| `pkg --help`, `pkg` with no args | n/a | 0 | Prints the usage docstring |
| `pkg <unknown>` | n/a | 1 | `error: Unknown command: '<x>'. Run pkg --help.` |

Extra arguments to `list`, `status`, `pending` and non-`clear` words after `queue` are silently ignored.

---

## 7. Gaps / not implemented

These do not exist today. Do not build against them.

| Wanted | Status | Closest workaround |
|---|---|---|
| JSON output from the `pkg` CLI (`--json` or similar) | **Does not exist.** CLI prints coloured text. | Use RPC via `aurelis_common.rpc.PkgdClient` (section 2). |
| "Nothing to cancel" signal from `queue clear` | **Does not exist.** Always exit 0. | Check `pkg.queue` first. |
| Queue entries with timestamps, sizes, versions over RPC | **Does not exist.** Only names are returned. | The data is in `pkg-queue.json` (`queued_at`, cache file sizes) but that file is root-only 0600. |
| Per-package queue status in one structure (op + name objects) | **Does not exist.** Two arrays. | Build it in the GUI. |
| `pkg update` / list of upgradable packages / staged package updates | **Does not exist.** Repositories are pinned to one snapshot. | OS update via `sysupdate` or `aurelis-update-app`. |
| Machine-readable `pkg search` / `pkg info` | **Does not exist.** Returns raw pacman text in one string. | Parse pacman's `-Ss` / `-Si` text, or call the RPC and split on blank lines. |
| polkit action / `pkexec` integration | **Does not exist.** | Not needed; use `wheel` membership. |
| Progress reporting for `pkg add` downloads | **Does not exist.** Request blocks until the download ends. | Run the call in a worker thread; show an indeterminate spinner. |
| Explicit "reboot required" flag | **Does not exist.** | After a manual `pkg apply`, `pkg.status` shows the new slot as `active_slot` with status `trial` (`activate_slot` writes `trial` with 0 attempts, `activation.py:128-144`). That is the only indicator. |
| Per-package result for a failed multi-package `add` | **Does not exist.** Whole request fails with one message. | Retry with fewer names. |
| Queue-directory or socket override via environment | **Does not exist.** Paths are constants. | Mock `PkgdClient` in GUI tests. |

### Gotchas that follow from the code

- **Timeout does not mean "not queued".** `pkg.install` writes the queue entry *before* pre-downloading (`aurelis-pkgd:1478-1484` then `1486`). If the client times out (600 s) or the user closes the GUI mid-call, the change may be queued. After any failure or timeout, call `pkg.queue` to see the real state.
- **Failed pre-download still exits 0.** Do not use the exit code as proof the package is cached.
- **Failed splash apply is probably retried once.** If the splash exits 1 after a failed apply, `pkg-apply-with-splash` sees a non-zero `cage` status and runs `pkg apply` again headless (assumes `cage` passes the child's exit status through; not verified). A failure can therefore run twice in one boot. The queue file is kept on failure, so `aurelis-pkg-apply.service` runs again on the next boot.
- **A failed apply deletes the cloned slot** and records it `empty` (`aurelis-pkgd:1722-1747`). The running system is unaffected; `pkg status` exits 1 and shows `Last apply failed`.

### Discrepancies between earlier notes and the code (the code is authoritative)

| Earlier note | Claim | Actual |
|---|---|---|
| `.agents/tasks/pkg-investigation.md` | The command is `pkg install` | It is `pkg add` (the CLI has no `install`). |
| same | `aurelis-pkg-apply.service` is `WantedBy=reboot.target halt.target poweroff.target`, runs `pkg apply` at **shutdown**, and is never enabled | It is `WantedBy=graphical.target`, runs at **boot** before the login screen, and is enabled (`build:1046-1049`). |
| same | Queue is a flat JSON array `[{"op","package"}]` | Schema-versioned document `{"schema_version": 1, "entries": [...], "cache": {...}}` (`aurelis-pkgd:_empty_queue_doc`). A legacy bare array is still read and migrated in memory. |
| same | `/usr/bin/pkg` and `aurelis-pkg` are identical copies | `pkg` is a symlink to `aurelis-pkg` (tasks.md 5.2; not confirmed with `ls -l` here). |
| same | Packages are downloaded to a temp cache at apply time | They are pre-downloaded at `pkg add` into `/var/cache/aurelis/pkg/pending/`; apply uses that cache and downloads only if it is incomplete. |
| same | `core-packages.json` is empty in the testing build, so all packages pass | Not verified for current builds. The daemon's apply-time core guard is fail-closed (a missing/invalid manifest refuses the transaction); the add/remove pre-check is fail-open (empty set). |
| `docs/user-guide.md` | Lists `pkg status`/`pkg pending` but not `pkg apply` | `pkg apply` exists. |
| CLI docstring / `pkg --help` | Omits `apply` and `pending` | Both are implemented. |
| `tests/unit/test_aurelis_pkg_cli.py` `TestCLIRemove` | Mocks a `pkg.remove` result of `{"removed": [...], "output": ""}` | The daemon returns `{"queued", "core", "queue"}`. The test does not match the daemon. |
| Task brief | Lists `.agents/tasks/pkg-queue-fix/` and `pkg-dryrun-fix/` | Neither directory exists in this repo. |
| `.agents/tasks/pkg-apply-design.md` | Mentions a "missing auto-reboot" | Auto-reboot exists now (splash `_reboot`, `pkg-apply-reboot-if-needed`). |

---

## 8. What was executed versus read

| Claim group | Basis |
|---|---|
| Everything in this file | **Code reading only.** No command could be run (shell tool returned no output). |
| Example outputs | Constructed from `print()` statements and handler return values; **not captured**. |
| Tests | **Not run.** `tests/unit/test_aurelis_pkg_cli.py` and `tests/unit/test_aurelis_pkgd.py` exist and were read, not executed. |
| `/usr/bin/pkg` being a symlink | From `tasks.md` and `docs/user-guide.md`; not checked on disk. |
| `pkexec` exit codes 126/127 | From general `pkexec(1)` knowledge; not from this repo. |
