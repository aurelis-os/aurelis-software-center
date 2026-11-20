"""Pacman output parsers (Phase 6).

Pure Python parsers for pacman -Si, -Qi, and -Qq output. No Qt, no subprocess.
Records are separated by blank lines. Each line is 'Key           : value'.
Multi-value fields (Depends On, Required By, etc.) are split on two spaces.
"""

from __future__ import annotations


def parse_si_output(text: str) -> list[dict]:
    """Parse pacman -Si output into a list of package dicts.

    Each package record is separated by blank lines. Lines follow the format:
    'Key           : value'. Multi-value fields are split on two consecutive
    spaces or contain 'None'.

    Parameters
    ----------
    text : str
        Raw output from pacman -Si command

    Returns
    -------
    list[dict]
        List of package dictionaries with keys matching pacman field names
        (lowercase with underscores). Multi-value fields are returned as lists.
    """
    packages = []
    current = {}

    for line in text.splitlines():
        stripped = line.strip()

        # Blank line separates records
        if not stripped:
            if current:
                packages.append(current)
                current = {}
            continue

        # Parse key : value
        if " : " not in line:
            continue

        key, _, value = line.partition(" : ")
        key = key.strip()
        value = value.strip()

        # Convert key to lowercase with underscores
        field_name = key.lower().replace(" ", "_")

        # Multi-value fields
        multi_value_fields = {
            "depends_on",
            "required_by",
            "optional_deps",
            "conflicts_with",
            "replaces",
            "groups",
            "provides",
        }

        if field_name in multi_value_fields:
            # Handle 'None' value
            if value == "None":
                current[field_name] = []
            else:
                # Split on two consecutive spaces
                current[field_name] = [item.strip() for item in value.split("  ") if item.strip()]
        else:
            current[field_name] = value

    # Add final record if present
    if current:
        packages.append(current)

    return packages


def parse_qi_output(text: str) -> list[dict]:
    """Parse pacman -Qi output into a list of installed package dicts.

    Similar format to -Si output but for installed packages. Records are
    separated by blank lines.

    Parameters
    ----------
    text : str
        Raw output from pacman -Qi command

    Returns
    -------
    list[dict]
        List of installed package dictionaries with keys matching pacman field
        names (lowercase with underscores). Multi-value fields are returned as lists.
    """
    packages = []
    current = {}

    for line in text.splitlines():
        stripped = line.strip()

        # Blank line separates records
        if not stripped:
            if current:
                packages.append(current)
                current = {}
            continue

        # Parse key : value
        if " : " not in line:
            continue

        key, _, value = line.partition(" : ")
        key = key.strip()
        value = value.strip()

        # Convert key to lowercase with underscores
        field_name = key.lower().replace(" ", "_")

        # Multi-value fields
        multi_value_fields = {
            "depends_on",
            "required_by",
            "optional_deps",
            "conflicts_with",
            "replaces",
            "groups",
            "provides",
        }

        if field_name in multi_value_fields:
            # Handle 'None' value
            if value == "None":
                current[field_name] = []
            else:
                # Split on two consecutive spaces
                current[field_name] = [item.strip() for item in value.split("  ") if item.strip()]
        else:
            current[field_name] = value

    # Add final record if present
    if current:
        packages.append(current)

    return packages


def parse_qq_output(text: str) -> list[str]:
    """Parse pacman -Qq output into a list of package names.

    Simple format: one package name per line.

    Parameters
    ----------
    text : str
        Raw output from pacman -Qq command

    Returns
    -------
    list[str]
        List of package names
    """
    return [line.strip() for line in text.splitlines() if line.strip()]
