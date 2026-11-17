"""Tests for core/archive.py safe extraction (section 5).

Both fixture archives are exercised: the normal one extracts everything,
the evil one extracts nothing outside the target and raises.
"""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from aurelis_software.core.archive import MAX_MEMBER_SIZE, safe_extract
from aurelis_software.core.errors import ArchiveError

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _write_tar(path: Path, members: dict[str, bytes | tuple[str, bytes]]) -> None:
    with tarfile.open(path, "w:gz") as tar:
        for name, content in members.items():
            if isinstance(content, tuple):
                linkname, _ = content
                info = tarfile.TarInfo(name)
                info.type = tarfile.SYMTYPE
                info.linkname = linkname
                tar.addfile(info)
            else:
                data = content
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))


def test_normal_icon_archive_extracts_everything(tmp_path):
    target = tmp_path / "icons"
    safe_extract(FIXTURES / "app-icons.tar.gz", target, kind="icons")
    extracted = {p.relative_to(target) for p in target.rglob("*") if p.is_file()}
    expected = {
        "ai.lmstudio.lm-studio.png",
        "com.getmailspring.Mailspring.png",
        "com.google.Chrome.png",
        "com.jetbrains.PhpStorm.png",
        "org.kde.kate.png",
        "org.kicad.KiCad.png",
    }
    expected = {Path(name) for name in expected}
    assert expected <= extracted
    assert all(p.suffix == ".png" for p in extracted)


def test_evil_archive_extracts_nothing_and_raises(tmp_path):
    target = tmp_path / "icons"
    with pytest.raises(ArchiveError):
        safe_extract(FIXTURES / "evil-icons.tar.gz", target, kind="icons")
    assert not any(target.rglob("*")), "evil archive must extract nothing"


def test_traversal_member_is_rejected(tmp_path):
    path = tmp_path / "evil.tar.gz"
    _write_tar(path, {"../evil.png": b"x"})
    target = tmp_path / "out"
    with pytest.raises(ArchiveError):
        safe_extract(path, target, kind="icons")
    assert not target.exists() or not any(target.rglob("*"))


def test_absolute_path_member_is_rejected(tmp_path):
    path = tmp_path / "evil.tar.gz"
    _write_tar(path, {"/absolute/evil.png": b"x"})
    target = tmp_path / "out"
    with pytest.raises(ArchiveError):
        safe_extract(path, target, kind="icons")
    assert not any(target.rglob("*"))


def test_symlink_member_is_rejected(tmp_path):
    path = tmp_path / "evil.tar.gz"
    _write_tar(path, {"evil.png": ("/etc/passwd", b"")})
    target = tmp_path / "out"
    with pytest.raises(ArchiveError):
        safe_extract(path, target, kind="icons")
    assert not any(target.rglob("*"))


def test_oversized_member_is_rejected(tmp_path):
    path = tmp_path / "evil.tar.gz"
    _write_tar(path, {"big.png": b"x"})
    # inflate the declared size beyond the limit (no payload needed)
    info = tarfile.TarInfo("big.png")
    info.size = MAX_MEMBER_SIZE + 1
    with tarfile.open(path, "w:gz") as out:
        out.addfile(info, io.BytesIO(b"\0" * info.size))
    target = tmp_path / "out"
    with pytest.raises(ArchiveError):
        safe_extract(path, target, kind="icons")
    assert not any(target.rglob("*"))


def test_catalog_archive_only_allows_apps_db(tmp_path):
    path = tmp_path / "catalog.tar.gz"
    _write_tar(path, {"apps.db": b"{}", "evil.png": b"x"})
    target = tmp_path / "out"
    with pytest.raises(ArchiveError):
        safe_extract(path, target, kind="catalog")
    assert not any(target.rglob("*"))


def test_catalog_archive_with_apps_db_extracts(tmp_path):
    path = tmp_path / "catalog.tar.gz"
    _write_tar(path, {"apps.db": b'{"schema_version": 1, "apps": []}'})
    target = tmp_path / "out"
    safe_extract(path, target, kind="catalog")
    assert (target / "apps.db").read_text() == '{"schema_version": 1, "apps": []}'
