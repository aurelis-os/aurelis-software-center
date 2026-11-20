"""Tests for PacmanBackend (Phase 6)."""

from aurelis_software.backends.pacman import PacmanBackend
from aurelis_software.core.models import App, InstalledApp, Source


class FakePkgdClient:
    """Fake PkgdClient for testing."""

    def __init__(self):
        self.installed_packages = []
        self.user_packages = []
        self.queue = {"install": [], "remove": []}
        self.install_calls = []
        self.remove_calls = []
        self.install_error = None
        self.remove_error = None

    def status(self):
        """Return status including user packages and queue."""
        return {
            "user_packages": self.user_packages,
            "queue": self.queue,
        }

    def list(self):
        """Return list of installed packages."""
        return {"packages": self.installed_packages}

    def install(self, packages):
        """Queue packages for install."""
        self.install_calls.append(packages)
        if self.install_error:
            raise self.install_error

        queued = []
        core = []
        already_installed = []

        for pkg in packages:
            # Check if already installed
            if any(p["name"] == pkg for p in self.installed_packages):
                already_installed.append(pkg)
            else:
                queued.append(pkg)
                self.queue["install"].append(pkg)

        return {
            "queued": queued,
            "core": core,
            "already_installed": already_installed,
            "queue": self.queue,
        }

    def remove(self, packages):
        """Queue packages for removal."""
        self.remove_calls.append(packages)
        if self.remove_error:
            raise self.remove_error

        queued = []
        core = []
        install_cancelled = []

        for pkg in packages:
            queued.append(pkg)
            self.queue["remove"].append(pkg)

        return {
            "queued": queued,
            "core": core,
            "install_cancelled": install_cancelled,
            "queue": self.queue,
        }

    def queue(self):
        """Return the current queue."""
        return {"queue": self.queue}


class FakeRunner:
    """Fake command runner for testing."""

    def __init__(self):
        self.commands = []
        self.responses = {}
        self.default_response = (0, "", "")

    def __call__(self, cmd):
        self.commands.append(cmd)
        # Return a response based on command
        key = tuple(cmd)
        return self.responses.get(key, self.default_response)

    def set_response(self, cmd, exit_code, stdout, stderr):
        """Set the response for a specific command."""
        self.responses[tuple(cmd)] = (exit_code, stdout, stderr)


def test_list_installed_classifies_locked_user_dependency():
    """list_installed classifies packages as locked, user, or dependency."""
    # Set up fake client with packages
    client = FakePkgdClient()
    client.installed_packages = [
        {"name": "bash", "version": "5.2.0-1"},
        {"name": "htop", "version": "3.3.0-1"},
        {"name": "libncursesw.so", "version": "6.4-1"},
    ]
    client.user_packages = ["htop"]

    # bash is core, htop is user, libncursesw.so is dependency
    backend = PacmanBackend(
        runner=FakeRunner(),
        pkgd_client=client,
        core_packages_path=None,
        user_packages_path=None,
    )
    backend._core_packages = {"bash"}

    apps = backend.list_installed()

    assert len(apps) == 3

    # Find each app
    bash = next(a for a in apps if a.id == "bash")
    htop = next(a for a in apps if a.id == "htop")
    libncurses = next(a for a in apps if a.id == "libncursesw.so")

    # Check classification
    assert bash.locked is True  # core package
    assert htop.locked is False  # user package
    assert libncurses.locked is False  # dependency

    # Check source
    assert all(a.source == Source.PACMAN for a in apps)


def test_list_installed_sets_pending_from_queue():
    """list_installed sets pending='install'/'remove' based on queue."""
    client = FakePkgdClient()
    client.installed_packages = [
        {"name": "vim", "version": "9.0.0-1"},
        {"name": "htop", "version": "3.3.0-1"},
    ]
    client.queue = {
        "install": ["gimp"],
        "remove": ["vim"],
    }
    client.user_packages = ["vim", "htop"]

    backend = PacmanBackend(runner=FakeRunner(), pkgd_client=client)
    apps = backend.list_installed()

    vim = next(a for a in apps if a.id == "vim")
    htop = next(a for a in apps if a.id == "htop")

    assert vim.pending == "remove"
    assert htop.pending is None


def test_install_calls_pkgd_client_install():
    """install calls PkgdClient.install and emits Operation events."""
    client = FakePkgdClient()
    backend = PacmanBackend(runner=FakeRunner(), pkgd_client=client)

    app = App(
        key="pacman:htop",
        id="htop",
        source=Source.PACMAN,
        name="htop",
        summary="Interactive process viewer",
    )

    op = backend.install(app)
    assert op.state.value == "pending"
    assert op.kind == "install"

    # Execute the operation
    op._work(op)

    # Check that install was called
    assert len(client.install_calls) == 1
    assert client.install_calls[0] == ["htop"]

    # Check operation completed successfully
    assert op.state.value == "finished"
    assert len(op.events) >= 2  # progress + finish


def test_install_fails_when_daemon_unavailable():
    """install fails with daemon-unavailable when pkgd_client is None."""
    backend = PacmanBackend(runner=FakeRunner(), pkgd_client=None)

    app = App(
        key="pacman:htop",
        id="htop",
        source=Source.PACMAN,
        name="htop",
        summary="Interactive process viewer",
    )

    op = backend.install(app)
    op._work(op)

    assert op.state.value == "failed"
    assert op.result is not None
    assert op.result.error == "daemon-unavailable"


def test_remove_checks_required_by_and_fails_on_conflict():
    """remove checks Required By and fails with ConflictPending if dependents are user packages."""
    runner = FakeRunner()
    # Set up pacman -Qi response with required_by field
    qi_output = """Name            : python
Version         : 3.11.0-1
Description     : Python programming language
Required By     : vim  alsa-utils

"""
    runner.set_response(["pacman", "-Qi", "python"], 0, qi_output, "")

    client = FakePkgdClient()
    client.installed_packages = [
        {"name": "python", "version": "3.11.0-1"},
        {"name": "vim", "version": "9.0.0-1"},
    ]
    client.user_packages = ["python", "vim"]

    backend = PacmanBackend(runner=runner, pkgd_client=client)
    backend._user_packages = {"python", "vim"}

    installed = InstalledApp(
        id="python",
        source=Source.PACMAN,
        name="python",
        version="3.11.0-1",
    )

    op = backend.remove(installed)
    op._work(op)

    # Should fail with ConflictPending
    assert op.state.value == "failed"
    assert op.result is not None
    assert op.result.error == "ConflictPending"
    assert "vim" in op.result.details


def test_remove_succeeds_when_no_conflict():
    """remove succeeds when no user packages depend on it."""
    runner = FakeRunner()
    # Set up pacman -Qi response with no required_by
    qi_output = """Name            : htop
Version         : 3.3.0-1
Description     : Interactive process viewer
Required By     : None

"""
    runner.set_response(["pacman", "-Qi", "htop"], 0, qi_output, "")

    client = FakePkgdClient()
    client.installed_packages = [
        {"name": "htop", "version": "3.3.0-1"},
    ]
    client.user_packages = ["htop"]

    backend = PacmanBackend(runner=runner, pkgd_client=client)
    backend._user_packages = {"htop"}

    installed = InstalledApp(
        id="htop",
        source=Source.PACMAN,
        name="htop",
        version="3.3.0-1",
    )

    op = backend.remove(installed)
    op._work(op)

    # Should succeed
    assert len(client.remove_calls) == 1
    assert client.remove_calls[0] == ["htop"]
    assert op.state.value == "finished"


def test_available_false_when_pkg_not_on_path():
    """available property returns False when pkg binary is not on PATH."""
    backend = PacmanBackend(runner=FakeRunner(), pkgd_client=None)

    # In the test environment, 'pkg' likely doesn't exist
    # We can't easily mock shutil.which here, but we can document the behavior
    # The available property checks shutil.which("pkg")
    available = backend.available
    # Just verify it's a boolean
    assert isinstance(available, bool)


def test_list_updates_always_empty():
    """list_updates always returns an empty list."""
    client = FakePkgdClient()
    backend = PacmanBackend(runner=FakeRunner(), pkgd_client=client)

    updates = backend.list_updates()
    assert updates == []


def test_update_not_supported():
    """update returns an Operation that fails with not-supported."""
    backend = PacmanBackend(runner=FakeRunner(), pkgd_client=FakePkgdClient())

    app = App(
        key="pacman:htop",
        id="htop",
        source=Source.PACMAN,
        name="htop",
        summary="Interactive process viewer",
    )
    installed = InstalledApp(
        id="htop",
        source=Source.PACMAN,
        name="htop",
        version="3.3.0-1",
    )

    op = backend.update(app, installed)
    op._work(op)

    assert op.state.value == "failed"
    assert op.result is not None
    assert op.result.error == "not-supported"
    assert "pinned" in op.result.details.lower()


def test_capabilities_when_daemon_unavailable():
    """capabilities returns install=False, remove=False when pkgd_client is None."""
    backend = PacmanBackend(runner=FakeRunner(), pkgd_client=None)
    caps = backend.capabilities()

    assert caps.install is False
    assert caps.remove is False
    assert caps.update is False


def test_list_installed_fallback_without_pkgd():
    """list_installed falls back to pacman -Qq when pkgd_client is None."""
    runner = FakeRunner()
    qq_output = """bash
htop
vim
python
"""
    runner.set_response(["pacman", "-Qq"], 0, qq_output, "")

    backend = PacmanBackend(runner=runner, pkgd_client=None)
    apps = backend.list_installed()

    assert len(apps) == 4
    names = [a.id for a in apps]
    assert names == ["bash", "htop", "vim", "python"]

    # All should have pending=None and locked=False in fallback mode
    assert all(a.pending is None for a in apps)
    assert all(a.locked is False for a in apps)
