# Flatpak progress spike (spec 8.2, decision 15.4)

## Environment
- `flatpak` at `/usr/bin/flatpak` — **installed**.
- Flathub user remote configured: `flathub https://dl.flathub.org/repo/`.
- No user-installed Flatpak apps (`flatpak list --user --app` empty).
- No network-dependent install was performed (would require time/network).

## Measurement: output with vs without a TTY

I ran `flatpak remotes --user --columns=name,url`, `flatpak remote-ls --user flathub --app --columns=application,version`,
and `flatpak list --user --app --columns=application,version,origin` both piped (no TTY) and under a PTY.

### Without a TTY (piped stdout)
- `flatpak remotes --user --columns=name,url`:
  ```
  flathub	https://dl.flathub.org/repo/
  ```
  Clean tab-separated values, no header row, no ANSI escape codes.
- `flatpak remote-ls --user flathub --app --columns=application,version`:
  clean tab-separated lines, one app per line, no header, e.g.
  ```
  ai.jan.Jan	0.8.8
  ai.lmstudio.lm-studio	0.4.28-2
  ```
  ~60 apps listed; trivial to parse by splitting on tabs.

### With a TTY (pty)
- `flatpak remotes --user --columns=name,url`:
  ```
  \e[1mName    URL\e[22m
  flathub https://dl.flathub.org/repo/
  ```
  ANSI bold on the header, space-padded columns, header row present.
- `flatpak remote-ls ...`:
  ANSI bold header `Application ID      Version`, space-padded columns, header row present.
  Harder to parse reliably (variable padding, ANSI codes, header).

### Progress during install/update
- Per spec 8.2: "the Flatpak CLI prints rich progress only on a TTY."
- I did **not** capture install/update progress output (no app installed, no network install performed).
- Could not measure: byte-level progress, fraction reporting, stall behaviour, non-TTY progress format.

## Recommendation
Use **(a) parsing non-TTY output with an indeterminate progress bar** — this is the spec's default plan
(spec 8.2, decision 15.4).

Rationale from measurement:
- Non-TTY output is clean, tab-separated, header-free, and easy to parse reliably.
- TTY output adds ANSI codes and padding that is fragile to parse.
- A PTY (option b) would give rich progress but requires PTY allocation, output parsing of escape sequences,
  and reaping a child PTY — added complexity for coarse benefit.
- libflatpak via PyGObject (option c) adds a new runtime dependency, which needs section 15 approval and
  owner sign-off (rule 5: standard library / existing deps first).

The GUI should show an indeterminate bar during Flatpak install/remove/update and surface the CLI's
stderr tail as Details on failure (spec 10.5).

## What I could NOT measure
- Actual install/update progress output (with or without a TTY) — no install was performed.
- Non-TTY progress format / granularity.
- Whether a PTY yields usable fraction-based progress.
- `flatpak update --appstream` refresh output and timing.
