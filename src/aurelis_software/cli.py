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
    from aurelis_software.core.matching import build_origin, match_installed
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

    linked = match_installed(inst, {"org.kde.kate": entry}, {})
    assert linked.kind == "linked"

    inst2 = InstalledApp(
        id="org.kde.kate",
        source=Source.APPIMAGE,
        name="Kate",
        sha256="new",
    )
    auto_link = match_installed(inst2, {"org.kde.kate": entry}, {"new": entry})
    assert auto_link.kind == "auto_link"
    assert auto_link.origin is not None
    assert auto_link.origin["catalog_id"] == "org.kde.kate"

    origin = build_origin(entry)
    assert origin["catalog_id"] == "org.kde.kate"
    assert origin["sha256"] == "new"

    print("selftest ok")
    return 0


def main(argv=None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    paths = Paths.xdg()
    config = load(paths)
    if args.command == "catalog":
        if args.action == "list":
            return _catalog_list(args, paths)
        if args.action == "refresh":
            return _catalog_refresh(args, paths, config)
    if args.command == "search":
        return _search(args, paths)
    if args.command == "show":
        return _show(args, paths)
    if args.command == "selftest":
        return _selftest()
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
