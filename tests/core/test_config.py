"""Tests for core/config.py (section 4.7)."""

from __future__ import annotations

from aurelis_software.core.config import load, save
from aurelis_software.core.paths import Paths


def test_defaults_have_all_documented_keys(tmp_path):
    paths = Paths(
        config_dir=tmp_path / "cfg", cache_dir=tmp_path / "cache", state_dir=tmp_path / "state"
    )
    cfg = load(paths)
    assert cfg.get("catalog.refresh_hours") == 24
    assert cfg.get("ui.language") == "system"
    assert cfg.get("ui.show_proprietary") is True
    assert cfg.get("ui.hide_incompatible") is True
    assert cfg.get("network.offline") is False
    assert cfg.get("flathub.enabled") is False
    assert cfg.get("pacman.enabled") is False
    assert cfg.get("updates.include_self_managed") is False
    assert cfg.get("downloads.allow_unverified") == "ask"
    assert cfg.get("wizard.run_without_asking") == []


def test_catalog_urls_are_the_documented_release_assets(tmp_path):
    paths = Paths(
        config_dir=tmp_path / "cfg", cache_dir=tmp_path / "cache", state_dir=tmp_path / "state"
    )
    cfg = load(paths)
    assert cfg.get("catalog.apps_url") == (
        "https://github.com/aurelis-os/aurelis-software-database/"
        "releases/download/latest/apps.db.tar.gz"
    )
    assert cfg.get("catalog.icons_url") == (
        "https://github.com/aurelis-os/aurelis-software-database/"
        "releases/download/latest/app-icons.tar.gz"
    )


def test_file_values_override_defaults(tmp_path):
    paths = Paths(
        config_dir=tmp_path / "cfg", cache_dir=tmp_path / "cache", state_dir=tmp_path / "state"
    )
    paths.config_file.parent.mkdir(parents=True)
    paths.config_file.write_text('[ui]\nlanguage = "el"\nrefresh_hours = 48\n')
    cfg = load(paths)
    assert cfg.get("ui.language") == "el"
    assert cfg.get("catalog.refresh_hours") == 24  # defaults still apply elsewhere


def test_unknown_keys_are_preserved(tmp_path):
    paths = Paths(
        config_dir=tmp_path / "cfg", cache_dir=tmp_path / "cache", state_dir=tmp_path / "state"
    )
    paths.config_file.parent.mkdir(parents=True)
    paths.config_file.write_text('[ui]\nlanguage = "el"\n[custom]\nfoo = "bar"\n')
    cfg = load(paths)
    assert cfg.get("ui.language") == "el"
    assert cfg.data.get("custom", {}).get("foo") == "bar"


def test_save_round_trip_preserves_known_and_unknown_keys(tmp_path):
    paths = Paths(
        config_dir=tmp_path / "cfg", cache_dir=tmp_path / "cache", state_dir=tmp_path / "state"
    )
    paths.config_file.parent.mkdir(parents=True)
    paths.config_file.write_text('[ui]\nlanguage = "el"\n[custom]\nfoo = "bar"\n')
    cfg = load(paths)
    cfg.data["ui"]["hide_incompatible"] = False
    save(paths, cfg)
    again = load(paths)
    assert again.get("ui.language") == "el"
    assert again.get("ui.hide_incompatible") is False
    assert again.data.get("custom", {}).get("foo") == "bar"
