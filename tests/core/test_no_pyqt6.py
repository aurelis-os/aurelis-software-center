"""Guard: no PyQt6 imports anywhere under core/ (rule 2 of section 0)."""

from __future__ import annotations

from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "aurelis_software" / "core"


def _core_files():
    return sorted(CORE_DIR.rglob("*.py"))


def test_no_pyqt6_imports_under_core():
    for py_file in _core_files():
        text = py_file.read_text()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import PyQt6", "from PyQt6")):
                msg = f"PyQt6 import in {py_file}: {stripped}"
                raise AssertionError(msg)
