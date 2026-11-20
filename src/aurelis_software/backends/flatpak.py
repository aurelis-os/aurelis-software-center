"""Flatpak backend (Phase 5.3, requirements R10.1-R10.7).

Implements the Backend ABC for Source.FLATPAK using QProcess-based
command execution with an injected command runner.

All commands are defined as module-level constants (argument lists, never
shell strings) so they can be verified in tests without touching a real
Flatpak installation.

Progress is shown as indeterminate because the flatpak CLI produces coarse
non-TTY output - a fraction cannot be derived from it.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from collections.abc import Callable

from aurelis_software.backends.base import Backend, Capabilities, Operation
from aurelis_software.core.models import App, InstalledApp, Source, UpdateInfo

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level command constants (R10.1-R10.6) - argument lists only.
# ---------------------------------------------------------------------------

LIST_INSTALLED_CMD: list[str] = [
    "flatpak",
    "list",
    "--user",
    "--app",
    "--columns=application,version,origin",
]

LIST_UPDATES_CMD: list[str] = [
    "flatpak",
    "remote-ls",
    "--user",
    "--updates",
    "--app",
    "--columns=application,version",
]

ADD_REMOTE_CMD: list[str] = [
    "flatpak",
    "remote-add",
    "--user",
    "--if-not-exists",
    "flathub",
    "https://dl.flathub.org/repo/flathub.flatpakrepo",
]

REFRESH_APPSTREAM: list[str] = [
    "flatpak",
    "update",
    "--appstream",
    "--user",
]


def _install_cmd(app_id: str) -> list[str]:
    """Return the install command for *app_id* (R10.4)."""
    return ["flatpak", "install", "--user", "--noninteractive", "-y", "flathub", app_id]


def _remove_cmd(app_id: str) -> list[str]:
    """Return the remove command for *app_id* (R10.5)."""
    return ["flatpak", "uninstall", "--user", "--noninteractive", "-y", app_id]


def _update_cmd(app_id: str) -> list[str]:
    """Return the update command for *app_id* (R10.6)."""
    return ["flatpak", "update", "--user", "--noninteractive", "-y", app_id]


# ---------------------------------------------------------------------------
# CommandRunner type alias
#
# A runner is any callable that takes a command list and returns
# (exit_code, stdout, stderr).  In production this wraps subprocess.run;
# in tests it replays captured fixtures.
# ---------------------------------------------------------------------------

CommandRunner = Callable[[list[str]], tuple[int, str, str]]


def _default_runner(cmd: list[str]) -> tuple[int, str, str]:
    """Default synchronous runner using subprocess (never called in tests)."""
    import subprocess  # local import keeps the module importable without subprocess at module load

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Output parsers
# ---------------------------------------------------------------------------


def _parse_installed(output: str) -> list[InstalledApp]:
    """Parse ``flatpak list`` tab-separated output into InstalledApp objects.

    Each row has columns: application, version, origin (tab-separated).
    Rows that do not have at least two columns are skipped.
    """
    apps: list[InstalledApp] = []
    for raw_line in output.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        parts = stripped.split("\t")
        app_id = parts[0].strip() if len(parts) > 0 else ""
        version = parts[1].strip() if len(parts) > 1 else None
        if not app_id:
            continue
        apps.append(
            InstalledApp(
                id=app_id,
                source=Source.FLATPAK,
                name=app_id,  # display name is populated from the index later
                version=version or None,
            )
        )
    return apps


def _parse_updates(output: str) -> list[UpdateInfo]:
    """Parse ``flatpak remote-ls --updates`` tab-separated output into UpdateInfo objects.

    Each row has columns: application, version (tab-separated).
    """
    updates: list[UpdateInfo] = []
    for raw_line in output.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        parts = stripped.split("\t")
        app_id = parts[0].strip() if len(parts) > 0 else ""
        version = parts[1].strip() if len(parts) > 1 else None
        if not app_id:
            continue
        updates.append(
            UpdateInfo(
                app_key=f"{Source.FLATPAK}:{app_id}",
                new_version=version or None,
                method="flatpak",
            )
        )
    return updates


# ---------------------------------------------------------------------------
# Operation helper
# ---------------------------------------------------------------------------


def _make_operation(
    app_key: str,
    kind: str,
    cmd: list[str],
    runner: CommandRunner,
    *,
    running_message: str = "",
) -> Operation:
    """Build an Operation whose work drives a synchronous command.

    Progress is indeterminate (fraction=None) because the flatpak CLI
    does not emit parseable fractions on non-TTY output (R11.1).
    """

    def work(op: Operation) -> None:
        # Emit an indeterminate progress event so the UI shows a spinner.
        step = kind  # "install" | "remove" | "update"
        op.progress(step, None, running_message)

        exit_code, _stdout, stderr = runner(cmd)

        if exit_code == 0:
            op.finish()
        else:
            tail = stderr.strip().splitlines()[-3:] if stderr.strip() else []
            op.fail("tool-failed", "\n".join(tail))

    return Operation(
        f"flatpak-{kind}-{uuid.uuid4().hex[:8]}",
        app_key,
        kind,
        cancellable=False,  # flatpak CLI cannot be interrupted cleanly mid-install
        work=work,
    )


# ---------------------------------------------------------------------------
# FlatpakBackend
# ---------------------------------------------------------------------------


class FlatpakBackend(Backend):
    """Flatpak backend for Source.FLATPAK (R10.1).

    Parameters
    ----------
    runner:
        Injected command runner ``(list[str]) -> (exit_code, stdout, stderr)``.
        Defaults to a subprocess-based runner when not supplied.
    """

    source = Source.FLATPAK

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner: CommandRunner = runner if runner is not None else _default_runner

    # ------------------------------------------------------------------
    # available property (R10.7)
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True when the ``flatpak`` binary is on PATH (R10.7)."""
        return shutil.which("flatpak") is not None

    @available.setter
    def available(self, value: bool) -> None:
        # The base class declares available as a class-level bool attribute.
        # We override it as a computed property; the setter is a no-op so
        # that BaseClass.__init__ machinery that may assign self.available
        # does not raise AttributeError.
        pass

    # ------------------------------------------------------------------
    # Backend ABC
    # ------------------------------------------------------------------

    def capabilities(self) -> Capabilities:
        ok = self.available
        return Capabilities(
            install=ok,
            remove=ok,
            update=ok,
        )

    def list_installed(self) -> list[InstalledApp]:
        """Run LIST_INSTALLED_CMD and parse the output (R10.2)."""
        exit_code, stdout, stderr = self._runner(LIST_INSTALLED_CMD)
        if exit_code != 0:
            log.warning("flatpak list failed (exit %d): %s", exit_code, stderr.strip())
            return []
        return _parse_installed(stdout)

    def list_updates(self) -> list[UpdateInfo]:
        """Run LIST_UPDATES_CMD and parse the output (R10.3)."""
        exit_code, stdout, stderr = self._runner(LIST_UPDATES_CMD)
        if exit_code != 0:
            log.warning("flatpak remote-ls failed (exit %d): %s", exit_code, stderr.strip())
            return []
        return _parse_updates(stdout)

    def install(self, app: App, **opts) -> Operation:
        """Return an Operation that installs *app* from Flathub (R10.4)."""
        return _make_operation(
            app.key,
            "install",
            _install_cmd(app.id),
            self._runner,
            running_message=f"Installing {app.name}…",
        )

    def remove(self, installed: InstalledApp) -> Operation:
        """Return an Operation that removes *installed* (R10.5)."""
        return _make_operation(
            installed.id,
            "remove",
            _remove_cmd(installed.id),
            self._runner,
            running_message=f"Removing {installed.name}…",
        )

    def update(self, app: App, installed: InstalledApp) -> Operation:
        """Return an Operation that updates *installed* to the latest version (R10.6)."""
        return _make_operation(
            app.key,
            "update",
            _update_cmd(installed.id),
            self._runner,
            running_message=f"Updating {installed.name}…",
        )

    def open(self, installed: InstalledApp) -> None:
        """Launch the Flatpak application.

        Uses ``flatpak run <app_id>`` via a detached process.
        """
        try:
            from PyQt6.QtCore import QProcess

            QProcess.startDetached("flatpak", ["run", installed.id])
        except Exception:
            log.exception("Failed to launch Flatpak app %s", installed.id)

    # ------------------------------------------------------------------
    # Flatpak-specific helpers (R12.1, R12.2)
    # ------------------------------------------------------------------

    def add_remote(self) -> Operation:
        """Return an Operation that adds the Flathub remote (R12.1)."""
        return _make_operation(
            "flatpak:flathub-remote",
            "install",
            ADD_REMOTE_CMD,
            self._runner,
            running_message="Adding Flathub remote…",
        )

    def refresh_appstream(self) -> Operation:
        """Return an Operation that refreshes Flathub AppStream metadata (R12.2)."""
        return _make_operation(
            "flatpak:flathub-appstream",
            "update",
            REFRESH_APPSTREAM,
            self._runner,
            running_message="Refreshing Flathub metadata…",
        )
