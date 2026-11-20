"""Tests for pacman output parsers (Phase 6)."""

from pathlib import Path

from aurelis_software.core.pacman_parser import (
    parse_qi_output,
    parse_qq_output,
    parse_si_output,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "pacman"


def test_parse_si_handles_multi_value_fields():
    """parse_si_output correctly parses multi-value fields as lists."""
    text = (FIXTURES / "si_output.txt").read_text()
    packages = parse_si_output(text)

    # Should have 6 packages
    assert len(packages) == 6

    # Check first package (htop) - has minimal dependencies
    htop = packages[0]
    assert htop["name"] == "htop"
    assert htop["version"] == "3.3.0-1"
    assert isinstance(htop["depends_on"], list)
    assert len(htop["depends_on"]) == 1
    assert htop["depends_on"][0] == "libncursesw.so=6-64"

    # groups field is None -> empty list
    assert htop["groups"] == []

    # Check vim - has multiple dependencies
    vim = packages[1]
    assert vim["name"] == "vim"
    assert isinstance(vim["depends_on"], list)
    assert len(vim["depends_on"]) == 8
    assert "vim-runtime=9.0.2190-1" in vim["depends_on"]
    assert "glibc" in vim["depends_on"]

    # Check provides field (multi-value)
    assert isinstance(vim["provides"], list)
    assert len(vim["provides"]) == 3
    assert "xxd" in vim["provides"]
    assert "vim-minimal" in vim["provides"]
    assert "vim-python" in vim["provides"]

    # Check replaces field (multi-value)
    assert isinstance(vim["replaces"], list)
    assert len(vim["replaces"]) == 2
    assert "vim-python" in vim["replaces"]
    assert "vim-minimal" in vim["replaces"]

    # Check bash - has a group
    bash = packages[5]
    assert bash["name"] == "bash"
    assert isinstance(bash["groups"], list)
    assert len(bash["groups"]) == 1
    assert bash["groups"][0] == "base"


def test_parse_si_handles_blank_lines_separator():
    """parse_si_output correctly separates records by blank lines."""
    text = (FIXTURES / "si_output.txt").read_text()
    packages = parse_si_output(text)

    # Should parse all 6 packages
    assert len(packages) == 6

    # Verify all expected packages are present
    names = [p["name"] for p in packages]
    assert names == ["htop", "vim", "firefox", "gimp", "python", "bash"]


def test_parse_qi_output():
    """parse_qi_output correctly parses installed package information."""
    text = (FIXTURES / "qi_output.txt").read_text()
    packages = parse_qi_output(text)

    # Should have 4 installed packages
    assert len(packages) == 4

    # Check htop
    htop = packages[0]
    assert htop["name"] == "htop"
    assert htop["version"] == "3.3.0-1"
    assert htop["required_by"] == []  # None -> empty list

    # Check vim - has required_by field
    vim = packages[1]
    assert vim["name"] == "vim"
    assert isinstance(vim["required_by"], list)
    assert len(vim["required_by"]) == 1
    assert vim["required_by"][0] == "neovim"

    # Check firefox - has required_by
    firefox = packages[2]
    assert firefox["name"] == "firefox"
    assert isinstance(firefox["required_by"], list)
    assert len(firefox["required_by"]) == 1
    assert firefox["required_by"][0] == "plasma-browser-integration"

    # Check python - has multiple required_by
    python = packages[3]
    assert python["name"] == "python"
    assert isinstance(python["required_by"], list)
    assert len(python["required_by"]) == 3
    assert "alsa-utils" in python["required_by"]
    assert "gtk-update-icon-cache" in python["required_by"]
    assert "vim" in python["required_by"]


def test_parse_qi_handles_none_value():
    """parse_qi_output handles 'None' values in multi-value fields."""
    text = (FIXTURES / "qi_output.txt").read_text()
    packages = parse_qi_output(text)

    # htop has 'None' for required_by, groups, provides
    htop = packages[0]
    assert htop["required_by"] == []
    assert htop["groups"] == []
    assert htop["provides"] == []


def test_parse_qq_output():
    """parse_qq_output returns a list of package names."""
    text = (FIXTURES / "qq_output.txt").read_text()
    packages = parse_qq_output(text)

    # Should have 15 package names
    assert len(packages) == 15

    # Check some expected packages
    assert "htop" in packages
    assert "vim" in packages
    assert "firefox" in packages
    assert "python" in packages
    assert "bash" in packages

    # Check order preserved
    assert packages[0] == "alsa-utils"
    assert packages[-1] == "xz"


def test_parse_si_empty_input():
    """parse_si_output handles empty input."""
    packages = parse_si_output("")
    assert packages == []


def test_parse_qi_empty_input():
    """parse_qi_output handles empty input."""
    packages = parse_qi_output("")
    assert packages == []


def test_parse_qq_empty_input():
    """parse_qq_output handles empty input."""
    packages = parse_qq_output("")
    assert packages == []
