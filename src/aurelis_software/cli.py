"""Developer CLI: ``python -m aurelis_software.cli``.

Core and services only: catalog refresh/list, search, show. No UI, no Qt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aurelis_software.core.catalog import CatalogResult, load_catalog
from aurelis_software.core.config import load
from aurelis_software.core.paths import Paths
from aurelis_software.core.search import build_index, search
from aurelis_software.core.textfmt import paragraphs, url_labels
from aurelis_software.services.db_updater import DbUpdater, url_fetch


def _load_catalog(catalog_path: Path) -> CatalogResult | None:
    """Load the catalog, printing a calm message and returning None if missing."""
    try:
        return load_catalog(catalog_path)
    except FileNotFoundError:
        print("no catalog cache; run `catalog refresh`", file=sys.stderr)
        return None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aurelis-software")
    sub = parser.add_subparsers(dest="command", required=True)

    catalog = sub.add_parser("catalog", help="catalog maintenance")
    catalog_actions = catalog.add_subparsers(dest="action", required=True)
    catalog_list = catalog_actions.add_parser("list", help="list catalog apps")
    catalog_list.add_argument("--catalog", default=None)
    catalog_refresh = catalog_actions.add_parser("refresh", help="refresh the catalog")
    catalog_refresh.add_argument("--force", action="store_true")

    search_cmd = sub.add_parser("search", help="search the catalog")
    search_cmd.add_argument("query")
    search_cmd.add_argument("--catalog", default=None)

    show_cmd = sub.add_parser("show", help="show a catalog entry")
    show_cmd.add_argument("id")
    show_cmd.add_argument("--catalog", default=None)

    sub.add_parser("selftest", help="exercise the service and backend modules")

    sub.add_parser(
        "dbus-ping",
        help="ping the appimage-launcher daemon (requires running daemon)",
    )

    sub.add_parser(
        "list-installed",
        help="list installed AppImages via the daemon (requires running daemon)",
    )

    return parser


def _catalog_list(args, paths: Paths) -> int:
    catalog_path = Path(args.catalog) if args.catalog else paths.catalog_db
    result = _load_catalog(catalog_path)
    if result is None:
        return 1
    print(
        f"schema_version={result.schema_version} "
        f"generated_at={result.generated_at} apps={len(result.apps)}"
    )
    for app in result.apps:
        print(f"{app.id}\t{app.name}\t{app.version or '-'}")
    return 0


def _catalog_refresh(args, paths: Paths, config) -> int:
    updater = DbUpdater(paths, config, url_fetch)
    result = updater.refresh(force=args.force)
    if result.error is not None:
        print(f"refresh failed: {result.error}", file=sys.stderr)
        return 1
    line = f"catalog {result.reason}"
    if result.catalog is not None:
        line += f" (apps={len(result.catalog.apps)})"
    print(line)
    return 0


def _search(args, paths: Paths) -> int:
    catalog_path = Path(args.catalog) if args.catalog else paths.catalog_db
    result = _load_catalog(catalog_path)
    if result is None:
        return 1
    index = build_index(result.apps)
    found = search(index, args.query)
    print(f"{len(found)} results")
    for app in found:
        print(f"{app.id}\t{app.name}\t{app.version or '-'}")
    return 0


def _show(args, paths: Paths) -> int:
    catalog_path = Path(args.catalog) if args.catalog else paths.catalog_db
    result = _load_catalog(catalog_path)
    if result is None:
        return 1
    app = next((entry for entry in result.apps if entry.id == args.id), None)
    if app is None:
        print(f"unknown id: {args.id}", file=sys.stderr)
        return 1
    print(f"{app.id}  ({app.source})")
    print(f"{app.name} — {app.summary}")
    print(f"version: {app.version or '-'}")
    print("categories: " + (", ".join(app.store_categories) if app.store_categories else "-"))
    description = app.raw.get("description") or ""
    for para in paragraphs(description):
        print(para)
    for label, url in url_labels(app.raw.get("urls")):
        print(f"{label}: {url}")
    return 0


def _selftest() -> int:
    """Exercise the service/backend modules end to end (reachability check)."""
    from aurelis_software.backends.base import OperationState
    from aurelis_software.backends.fake import FakeBackend
    from aurelis_software.core.matching import build_origin, match_installed_to_catalog
    from aurelis_software.core.models import App, InstalledApp, Source
    from aurelis_software.core.versions import update_available
    from aurelis_software.services.operations import OperationQueue

    queue = OperationQueue()
    backend = FakeBackend()
    app = App(
        key="appimage:org.kde.kate",
        id="org.kde.kate",
        source=Source.APPIMAGE,
        name="Kate",
        summary="editor",
    )
    op = backend.install(app)
    queue.enqueue(op, backend)
    assert op.state == OperationState.FINISHED

    entry = App(
        key="appimage:org.kde.kate",
        id="org.kde.kate",
        source=Source.APPIMAGE,
        name="Kate",
        summary="editor",
        version="2",
        raw={"sha256": "new"},
    )
    inst = InstalledApp(
        id="org.kde.kate",
        source=Source.APPIMAGE,
        name="Kate",
        origin={"catalog_id": "org.kde.kate", "version": "1", "sha256": "old"},
    )
    assert update_available(entry, inst) is True

    linked = match_installed_to_catalog(inst, [entry])
    assert linked.kind == "origin"
    assert linked.catalog_app is entry

    inst2 = InstalledApp(
        id="org.kde.kate",
        source=Source.APPIMAGE,
        name="Kate",
        sha256="new",
    )
    auto_link = match_installed_to_catalog(inst2, [entry], file_sha256="new")
    assert auto_link.kind == "sha256"
    assert auto_link.catalog_app is entry

    origin = build_origin(entry)
    assert origin["catalog_id"] == "org.kde.kate"
    assert origin["sha256"] == "new"

    print("selftest ok")
    return 0


def _dbus_ping() -> int:
    """Ping the appimage-launcher daemon: read APIVersion and Capabilities."""
    import sys

    from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer
    from PyQt6.QtDBus import QDBusConnection

    from aurelis_software.backends.appimage import AppImageBackend
    from aurelis_software.services.qt_dbus import DbusClient

    QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        print("session bus not connected", file=sys.stderr)
        return 1
    client = DbusClient(bus)
    backend = AppImageBackend(client)
    results: list = []
    errors: list = []
    loop = QEventLoop()

    def _ok(version, caps):
        results.append((version, caps))
        loop.quit()

    def _fail(err):
        errors.append(err)
        loop.quit()

    backend.check_availability(ok_cb=_ok, fail_cb=_fail)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    if errors:
        print(f"daemon unavailable: {errors[0]}", file=sys.stderr)
        return 1
    if not results:
        print("timeout waiting for daemon", file=sys.stderr)
        return 1
    version, caps = results[0]
    print(f"APIVersion: {version}")
    print(f"Capabilities: {', '.join(sorted(caps))}")
    return 0


_MIN_INSTALLED_ENTRY_LEN = 3  # (app_id, name, version)


def _list_installed() -> int:
    """List installed AppImages via the daemon."""
    import sys

    from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer
    from PyQt6.QtDBus import QDBusConnection

    from aurelis_software.backends.appimage import AppImageBackend
    from aurelis_software.services.qt_dbus import DbusClient

    QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        print("session bus not connected", file=sys.stderr)
        return 1
    client = DbusClient(bus)
    backend = AppImageBackend(client)
    results: list = []
    errors: list = []
    loop = QEventLoop()

    backend.list_installed_async(
        {"all": True},
        reply_cb=lambda apps: (results.append(apps), loop.quit()),
        error_cb=lambda e: (errors.append(e), loop.quit()),
    )
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    if errors:
        print(f"error: {errors[0]}", file=sys.stderr)
        return 1
    if not results:
        print("timeout", file=sys.stderr)
        return 1
    apps = results[0]
    if not apps:
        print("(no installed AppImages)")
        return 0
    for entry in apps:
        # entry is a tuple/list: (app_id, name, version, ...)
        if isinstance(entry, (list, tuple)) and len(entry) >= _MIN_INSTALLED_ENTRY_LEN:
            print(f"{entry[0]}\t{entry[1]}\t{entry[2]}")
        else:
            print(entry)
    return 0


def main(argv=None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    paths = Paths.xdg()
    config = load(paths)
    _dispatch = {
        "search": lambda: _search(args, paths),
        "show": lambda: _show(args, paths),
        "selftest": _selftest,
        "dbus-ping": _dbus_ping,
        "list-installed": _list_installed,
    }
    if args.command == "catalog":
        if args.action == "list":
            return _catalog_list(args, paths)
        return _catalog_refresh(args, paths, config)
    fn = _dispatch.get(args.command)
    if fn is not None:
        return fn()
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
