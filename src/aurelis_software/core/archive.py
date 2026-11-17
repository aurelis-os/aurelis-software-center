"""Safe tar archive extraction (section 5).

Members are validated before anything is extracted: absolute paths,
parent traversal, symlinks, hard links and devices are rejected, only
expected member names are allowed, and per-member and total size limits
are enforced. ``tarfile.extractall`` is always used with a filter.
"""

from __future__ import annotations

import posixpath
import re
import tarfile
from pathlib import Path

from .errors import ArchiveError

ICON_NAME = re.compile(r"^[A-Za-z0-9._-]+\.png$")

MAX_MEMBER_SIZE = 2 * 1024 * 1024
MAX_TOTAL_SIZE = 200 * 1024 * 1024

_MEMBER_ALLOWLIST = {
    "catalog": lambda name: name == "apps.db",
    "icons": lambda name: bool(ICON_NAME.fullmatch(name)),
}


def _member_kind_ok(kind: str, name: str) -> bool:
    check = _MEMBER_ALLOWLIST.get(kind)
    if check is None:
        msg = f"unknown archive kind: {kind!r}"
        raise ValueError(msg)
    return check(name)


def _validate_member(member: tarfile.TarInfo, kind: str) -> str:
    name = member.name
    clean = posixpath.normpath(name)
    if (
        clean in (".", "..")
        or clean.startswith("/")
        or ".." in posixpath.split(clean)[0].split("/")
    ):
        msg = f"unsafe archive member path: {name!r}"
        raise ArchiveError(msg)
    if member.issym() or member.islnk() or member.isdev():
        msg = f"unsafe archive member type: {name!r}"
        raise ArchiveError(msg)
    if not _member_kind_ok(kind, clean):
        msg = f"unexpected archive member: {name!r}"
        raise ArchiveError(msg)
    return clean


def safe_extract(archive: Path | str, target: Path | str, *, kind: str = "icons") -> None:
    """Extract ``archive`` into ``target`` after validating every member."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        total = 0
        for member in members:
            clean = _validate_member(member, kind)
            if member.isfile():
                if member.size > MAX_MEMBER_SIZE:
                    msg = f"archive member too large: {clean!r} ({member.size} bytes)"
                    raise ArchiveError(msg)
                total += member.size
                if total > MAX_TOTAL_SIZE:
                    msg = f"archive total size exceeds {MAX_TOTAL_SIZE} bytes"
                    raise ArchiveError(msg)
        try:
            tar.extractall(target, filter="data")
        except TypeError:  # pragma: no cover - Python < 3.12 fallback
            tar.extractall(target)
