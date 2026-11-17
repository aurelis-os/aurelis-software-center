"""Tests for core/paths.py (section 4.7)."""

from __future__ import annotations

from pathlib import Path

from aurelis_software.core.paths import Paths


def test_xdg_defaults_are_under_home(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    paths = Paths.xdg()

    assert paths.config_dir == Path(str(tmp_path) + "/.config")
    assert paths.cache_dir == Path(str(tmp_path) + "/.cache")
    assert paths.state_dir == Path(str(tmp_path) + "/.local/state")


def test_xdg_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    paths = Paths.xdg()
    assert paths.config_dir == tmp_path / "cfg"
    assert paths.cache_dir == tmp_path / "cache"
    assert paths.state_dir == tmp_path / "state"


def test_derived_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    paths = Paths.xdg()
    assert paths.config_file == tmp_path / "cfg" / "aurelis-software" / "config.toml"
    assert paths.catalog_db == tmp_path / "cache" / "aurelis-software" / "catalog" / "apps.db"
    assert (
        paths.catalog_prev == tmp_path / "cache" / "aurelis-software" / "catalog" / "apps.db.prev"
    )
    assert paths.icons_dir == tmp_path / "cache" / "aurelis-software" / "icons"
    assert paths.downloads_dir == tmp_path / "cache" / "aurelis-software" / "downloads"
    assert paths.state_file == tmp_path / "state" / "aurelis-software" / "catalog-state.json"


def test_paths_are_injected_without_env(tmp_path):
    paths = Paths(
        config_dir=tmp_path / "cfg", cache_dir=tmp_path / "cache", state_dir=tmp_path / "state"
    )
    assert paths.config_dir == tmp_path / "cfg"
