"""Pacman backend (Phase 6).

Implements the Backend ABC for Source.PACMAN using RPC to the pkgd daemon
for all mutating operations (install, remove). Never runs pkg as a subprocess
in production paths.

The runner parameter is for pacman read-only commands (pacman -Si, -Qi, -Qq)
in tests and fallback paths. All install/remove operations go through PkgdClient.

Classification:
- locked: package in core_packages (cannot be removed)
- user: package in user_packages (can be removed)
- dependency: installed but not in either list

Pending state:
- 'install': package is in the pkgd queue to be installed
- 'remove': package is in the pkgd queue to be removed
- None: no pending operation
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from aurelis_software.backends.base import Backend, Capabilities, Operation
from aurelis_software.core.models import App, InstalledApp, Source, UpdateInfo

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level command constants
# ---------------------------------------------------------------------------

LIST_INSTALLED_CMD: list[str] = ["pacman", "-Qq"]


def _query_info_cmd(package_name: str) -> list[str]:
    """Return the command to query installed package info."""
    return ["pacman", "-Qi", package_name]


# ---------------------------------------------------------------------------
# CommandRunner type alias
# ---------------------------------------------------------------------------

CommandRunner = Callable[[list[str]], tuple[int, str, str]]


def _default_runner(cmd: list[str]) -> tuple[int, str, str]:
    """Default synchronous runner using subprocess."""
    import subprocess

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# PacmanBackend
# ---------------------------------------------------------------------------


class PacmanBackend(Backend):
    """Pacman backend for Source.PACMAN.

    Parameters
    ----------
    runner:
        Injected command runner for read-only pacman commands.
    pkgd_client:
        Injected PkgdClient for install/remove operations via RPC.
    core_packages_path:
        Path to JSON file containing list of core package names.
    user_packages_path:
        Path to JSON file containing list of user package names.
    """

    source = Source.PACMAN

    def __init__(
        self,
        runner: CommandRunner | None = None,
        pkgd_client=None,
        core_packages_path: str | Path | None = None,
        user_packages_path: str | Path | None = None,
    ) -> None:
        self._runner: CommandRunner = runner if runner is not None else _default_runner
        self._pkgd_client = pkgd_client
        self._core_packages: set[str] = set()
        self._user_packages: set[str] = set()

        # Load core packages
        if core_packages_path is not None:
            try:
                with open(core_packages_path) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._core_packages = set(data)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                log.warning("Could not load core packages from %s", core_packages_path)

        # Load user packages
        if user_packages_path is not None:
            try:
                with open(user_packages_path) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._user_packages = set(data)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                log.warning("Could not load user packages from %s", user_packages_path)

    # ------------------------------------------------------------------
    # available property
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True when the pkg binary is on PATH."""
        return shutil.which("pkg") is not None

    @available.setter
    def available(self, value: bool) -> None:
        # No-op setter for compatibility with base class.
        pass

    # ------------------------------------------------------------------
    # Backend ABC
    # ------------------------------------------------------------------

    def capabilities(self) -> Capabilities:
        can_mutate = self.available and self._pkgd_client is not None
        return Capabilities(
            install=can_mutate,
            remove=can_mutate,
            update=False,
        )

    def list_installed(self) -> list[InstalledApp]:
        """List installed packages with classification and pending state."""
        # If pkgd_client is not available, fall back to basic pacman -Qq
        if self._pkgd_client is None:
            exit_code, stdout, stderr = self._runner(LIST_INSTALLED_CMD)
            if exit_code != 0:
                log.warning("pacman -Qq failed (exit %d): %s", exit_code, stderr.strip())
                return []

            from aurelis_software.core import pacman_parser

            package_names = pacman_parser.parse_qq_output(stdout)
            return [
                InstalledApp(
                    id=name,
                    source=Source.PACMAN,
                    name=name,
                    version=None,
                    locked=False,
                    pending=None,
                )
                for name in package_names
            ]

        # Use pkgd_client to get full state
        try:
            status = self._pkgd_client.status()
            queue = status.get("queue", {"install": [], "remove": []})
            install_queue = set(queue.get("install", []))
            remove_queue = set(queue.get("remove", []))

            # Get list of all installed packages
            pkg_list = self._pkgd_client.list()
            packages = pkg_list.get("packages", [])

            apps: list[InstalledApp] = []
            for pkg in packages:
                name = pkg.get("name", "")
                if not name:
                    continue

                version = pkg.get("version")

                # Determine locked status
                locked = name in self._core_packages

                # Determine pending state
                pending = None
                if name in install_queue:
                    pending = "install"
                elif name in remove_queue:
                    pending = "remove"

                apps.append(
                    InstalledApp(
                        id=name,
                        source=Source.PACMAN,
                        name=name,
                        version=version,
                        locked=locked,
                        pending=pending,
                    )
                )

        except Exception as e:  # noqa: BLE001
            log.warning("Failed to get package list via pkgd: %s", e)
            # Fall back to basic listing
            apps = []

        if not apps:
            exit_code, stdout, stderr = self._runner(LIST_INSTALLED_CMD)
            if exit_code != 0:
                log.warning("pacman -Qq failed (exit %d): %s", exit_code, stderr.strip())
                return []

            from aurelis_software.core import pacman_parser

            package_names = pacman_parser.parse_qq_output(stdout)
            return [
                InstalledApp(
                    id=name,
                    source=Source.PACMAN,
                    name=name,
                    version=None,
                    locked=False,
                    pending=None,
                )
                for name in package_names
            ]

        return apps

    def list_updates(self) -> list[UpdateInfo]:
        """List available updates (always empty for Pacman in Aurelis).

        Aurelis uses pinned repositories, so package updates only come
        with full OS updates, not individual package updates.
        """
        return []

    def install(self, app: App, **opts) -> Operation:
        """Return an Operation that installs the package via pkgd."""
        if self._pkgd_client is None:
            return _make_failed_operation(
                app.key,
                "install",
                "daemon-unavailable",
                "Package daemon is not available",
            )

        return _make_install_operation(app.key, app.id, app.name, self._pkgd_client)

    def remove(self, installed: InstalledApp) -> Operation:
        """Return an Operation that removes the package via pkgd.

        First checks Required By via pacman -Qi. If any reverse dependencies
        are user packages, fails with ConflictPending.
        """
        if self._pkgd_client is None:
            return _make_failed_operation(
                installed.id,
                "remove",
                "daemon-unavailable",
                "Package daemon is not available",
            )

        return _make_remove_operation(
            installed.id,
            installed.name,
            self._runner,
            self._pkgd_client,
            self._user_packages,
        )

    def update(self, app: App, installed: InstalledApp) -> Operation:
        """Return an Operation that fails (Pacman updates not supported in Aurelis)."""
        return _make_failed_operation(
            app.key,
            "update",
            "not-supported",
            "Pacman updates are not supported (repositories are pinned)",
        )

    def open(self, installed: InstalledApp) -> None:
        """No-op: Pacman packages have no single launch path."""


# ---------------------------------------------------------------------------
# Operation helpers
# ---------------------------------------------------------------------------


def _make_failed_operation(
    app_key: str,
    kind: str,
    code: str,
    message: str,
) -> Operation:
    """Create an Operation that immediately fails."""

    def work(op: Operation) -> None:
        op.fail(code, message)

    return Operation(
        f"pacman-{kind}-{uuid.uuid4().hex[:8]}",
        app_key,
        kind,
        cancellable=False,
        work=work,
    )


def _make_install_operation(
    app_key: str,
    package_id: str,
    package_name: str,
    pkgd_client,
) -> Operation:
    """Create an Operation that installs a package via pkgd."""

    def work(op: Operation) -> None:
        try:
            op.progress("install", None, f"Installing {package_name}…")

            result = pkgd_client.install([package_id])

            # Check if it was queued
            queued = result.get("queued", [])
            if package_id in queued:
                op.finish()
            else:
                # Package was not queued (might be core, already installed, etc.)
                details = []
                if package_id in result.get("core", []):
                    details.append("Package is a core system package")
                if package_id in result.get("already_installed", []):
                    details.append("Package is already installed")
                detail_text = "; ".join(details) if details else "Package was not queued"
                op.fail("not-queued", detail_text)

        except ImportError:
            op.fail("daemon-unavailable", "aurelis_common.rpc is not available")
        except Exception as e:  # noqa: BLE001
            # Check for specific RPC errors by class name
            error_class = type(e).__name__
            if error_class == "PkgdDownError":
                op.fail("daemon-unreachable", str(e))
            elif error_class == "PkgdError":
                op.fail("daemon-error", str(e))
            else:
                op.fail("install-failed", str(e))

    return Operation(
        f"pacman-install-{uuid.uuid4().hex[:8]}",
        app_key,
        "install",
        cancellable=False,
        work=work,
    )


def _make_remove_operation(  # noqa: C901
    package_id: str,
    package_name: str,
    runner: CommandRunner,
    pkgd_client,
    user_packages: set[str],
) -> Operation:
    """Create an Operation that removes a package via pkgd.

    Checks Required By first and fails if any user packages depend on it.
    """

    def work(op: Operation) -> None:  # noqa: C901, PLR0912
        try:
            # First check Required By via pacman -Qi
            exit_code, stdout, stderr = runner(_query_info_cmd(package_id))
            if exit_code != 0:
                log.warning("pacman -Qi %s failed (exit %d): %s", package_id, exit_code, stderr)
                # Proceed anyway - package might not be installed
            else:
                from aurelis_software.core import pacman_parser

                # Parse the output
                packages = pacman_parser.parse_qi_output(stdout)
                if packages:
                    pkg_info = packages[0]
                    required_by = pkg_info.get("required_by", [])

                    # Check if any reverse dependencies are user packages
                    # Extract just the package name (before any version or description)
                    user_dependents = []
                    for dep in required_by:
                        # Split on whitespace to get just the package name
                        dep_name = dep.split()[0] if dep else ""
                        if dep_name in user_packages:
                            user_dependents.append(dep_name)

                    if user_dependents:
                        op.fail(
                            "ConflictPending",
                            f"Required by: {', '.join(user_dependents)}",
                        )
                        return

            # No conflicts, proceed with removal
            op.progress("remove", None, f"Removing {package_name}…")

            result = pkgd_client.remove([package_id])

            # Check if it was queued for removal
            queued = result.get("queued", [])
            if package_id in queued:
                op.finish()
            else:
                # Check why it wasn't queued
                details = []
                if package_id in result.get("core", []):
                    details.append("Package is a core system package")
                if package_id in result.get("install_cancelled", []):
                    details.append("Queued install was cancelled")
                detail_text = (
                    "; ".join(details) if details else "Package was not queued for removal"
                )
                op.fail("not-queued", detail_text)

        except ImportError:
            op.fail("daemon-unavailable", "aurelis_common.rpc is not available")
        except Exception as e:  # noqa: BLE001
            # Check for specific RPC errors by class name
            error_class = type(e).__name__
            if error_class == "PkgdDownError":
                op.fail("daemon-unreachable", str(e))
            elif error_class == "PkgdError":
                op.fail("daemon-error", str(e))
            else:
                op.fail("remove-failed", str(e))

    return Operation(
        f"pacman-remove-{uuid.uuid4().hex[:8]}",
        package_id,
        "remove",
        cancellable=False,
        work=work,
    )
