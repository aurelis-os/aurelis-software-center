"""Store category mapping (section 4.4, Appendix B).

Ordered table, first match wins. Unknown raw categories are ignored; an
app can belong to several store categories. Toolkit/desktop tags
(KDE, Qt, GNOME, GTK, X-*) are ignored.
"""

from __future__ import annotations

_CATEGORY_TABLE: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "Graphics and Photography",
        {
            "Graphics",
            "2DGraphics",
            "3DGraphics",
            "RasterGraphics",
            "VectorGraphics",
            "Photography",
            "Scanning",
            "Viewer",
        },
    ),
    (
        "Audio and Video",
        {
            "AudioVideo",
            "Audio",
            "Video",
            "Player",
            "Recorder",
            "Music",
            "AudioVideoEditing",
            "Midi",
            "Mixer",
            "Sequencer",
            "Tuner",
        },
    ),
    (
        "Games",
        {
            "Game",
            "ArcadeGame",
            "BoardGame",
            "CardGame",
            "LogicGame",
            "StrategyGame",
            "Simulation",
            "KidsGame",
        },
    ),
    (
        "Development",
        {
            "Development",
            "IDE",
            "Debugger",
            "Building",
            "RevisionControl",
            "WebDevelopment",
            "GUIDesigner",
        },
    ),
    (
        "Internet",
        {
            "Network",
            "WebBrowser",
            "Email",
            "Chat",
            "InstantMessaging",
            "FileTransfer",
            "P2P",
            "RemoteAccess",
            "News",
        },
    ),
    (
        "Office",
        {
            "Office",
            "WordProcessor",
            "Spreadsheet",
            "Presentation",
            "Calendar",
            "ContactManagement",
            "Finance",
            "Publishing",
        },
    ),
    (
        "Education and Science",
        {
            "Education",
            "Science",
            "Astronomy",
            "Math",
            "Chemistry",
            "Physics",
            "Electronics",
            "Engineering",
            "Languages",
        },
    ),
    ("Security", {"Security"}),
    (
        "System",
        {"System", "Settings", "Monitor", "TerminalEmulator", "FileManager", "PackageManager"},
    ),
    ("Utilities", {"Utility", "Calculator", "Archiving", "Clock", "TextEditor", "Accessibility"}),
)

_IGNORED = {"kde", "qt", "gnome", "gtk"}


def _normalise(raw: str) -> str:
    value = raw.strip()
    if not value:
        return value
    if value.upper().startswith("X-"):
        return ""
    low = value.casefold()
    if low in _IGNORED:
        return ""
    return value


def map_categories(raw_categories) -> tuple[str, ...]:
    """Map raw freedesktop categories to store categories (first match wins)."""
    found: list[str] = []
    for raw in raw_categories or []:
        value = _normalise(raw)
        if not value:
            continue
        for store_category, values in _CATEGORY_TABLE:
            if value in values:
                if store_category not in found:
                    found.append(store_category)
                break
    return tuple(found)
