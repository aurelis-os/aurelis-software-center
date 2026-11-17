# Manager1 contract notes (spec 9.1)

This file lists every D-Bus call this app makes against `appimage-launcher`'s
`Manager1` interface, and what it relies on. The authoritative introspection is
kept at `docs/contracts/manager1.xml` (currently a draft; see decision 15.2).

## Connection
- Bus: session bus.
- Service name: `io.github.appimage_launcher.Manager` (from launcher's constants.py; one constant in GUI: put it in core/ or backends/ constants, not repeated).
- Object path: `/io/github/appimage_launcher/Manager`.
- Interface: `io.github.appimage_launcher.Manager1`.
- Binding: QtDBus, asynchronous calls only (never blocking on the UI thread — spec 3.4).
- Bus activation starts the daemon on first call.

## Capabilities required at startup (spec 8.1)
`inspect`, `origin`, `install-options-v1`, `conflict-error`, `remove-file-action`, `list-hash`.
And `APIVersion >= 1`. If any are missing, the AppImage section stays browsable but
Install/Update/Remove are disabled and a banner explains.

## Calls used by this app

| Call | Used for | In options | Notes |
|------|----------|------------|-------|
| property `APIVersion` | startup check | — | require >= 1 |
| property `Capabilities` | startup check | — | see list above |
| `List({all, hash})` | Installed page, matching | `all:true`, `hash:true` | hash only in low-priority background call |
| `Info(name)` | detail of one app | — | includes `sha256` |
| `Inspect(path)` | wizards | — | name, icon, version, relation; never executes |
| `Install(path, options)` | install/update/wizard install | `source_action=move`, `conflict=error` then explicit retry, `silent=true`, `origin=<JSON>` | wizard uses `source_action=copy` |
| `Remove(name, options)` | remove | `file_action=trash`, `silent=true` | never `purge` |
| `Revert(name)` | Undo after update | — | |
| `SetPolicy(name, policy)` | per-app update policy | `auto`/`manual`/`pinned` | |
| `SetOrigin(name, json)` | auto-link, "Link to catalog", unlink | empty string unlinks | |
| `Reindex()` | Rescan button | — | |
| signal `AppsChanged(kind, app_id, source)` | live refresh | — | ignore unknown kinds; debounce 300 ms |

## Errors handled (`...Error.<Name>`)
`NotFound`, `Ambiguous`, `NameCollision`, `ConflictPending` (payload with old/new meta and `relation`),
`InvalidAppImage`, `UnsupportedType`, `InvalidArgument`, `PolicyForbids`, `Busy`, `Io`, `Aborted`.
Each maps to one user message + one Details text (spec 6).

## What the GUI must NOT do (spec 9.1)
- Write into `~/Applications`.
- Read or write the launcher's SQLite file.
- Edit the launcher's desktop entries.
- Call `Remove` with `file_action=purge`.

## Contract test (spec 9.1)
`tests/contract/`: parse `docs/contracts/manager1.xml` and assert every method, option name,
property and signal used by `backends/appimage.py` exists with the right signature.
Optional `real_daemon` suite (`-m real_daemon`) runs the same scenarios against the installed
daemon once it is tagged `api-v1`.

## Open items
- Final D-Bus service name (decision 15.2).
- Exact `List` output shape (the `a(sssv)` above is a best guess from section 9.1; confirm against the real XML).
- Exact `Install`/`Info`/`Inspect` result dict keys (origin payload fields, `changed`, `previous`).
