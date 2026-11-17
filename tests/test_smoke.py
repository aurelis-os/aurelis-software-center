"""Smoke tests for fixtures.

The real catalog database is present at ``tests/fixtures/apps.db`` and parses
as JSON with ``schema_version == 1``. This suite also validates the companion
edge fixture ``tests/fixtures/apps.edge.db`` (every entry is labelled
``invented``: true) and the icons archive.
"""

import json
import tarfile
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def test_apps_edge_db_loads():
    path = FIXTURES / "apps.edge.db"
    data = json.loads(path.read_text())
    assert data["schema_version"] == 1
    assert isinstance(data["apps"], list)
    for app in data["apps"]:
        assert app.get("invented") is True


def test_icons_archive_opens():
    path = FIXTURES / "app-icons.tar.gz"
    with tarfile.open(path) as tar:
        members = tar.getnames()
    assert members, "app-icons.tar.gz should contain at least one icon"
    for name in members:
        assert not name.startswith("../"), name
        assert not name.startswith("/"), name


def test_real_apps_db_parses_with_schema_version_one():
    path = FIXTURES / "apps.db"
    data = json.loads(path.read_text())
    assert data["schema_version"] == 1
    assert isinstance(data["apps"], list)
    assert data["count"] == len(data["apps"])
