#!/usr/bin/env python3
"""Regenerate test fixtures: evil-icons.tar.gz and apps.edge.db."""

import io
import tarfile
import json
from pathlib import Path

FIXTURES = Path("tests/fixtures")
FIXTURES.mkdir(exist_ok=True)


def create_evil_icons():
    """Create evil-icons.tar.gz with malicious archive entries for safety testing."""
    evil_members = {
        "../evil.png": b"traversal",
        "/absolute/evil.png": b"absolute",
        "evil.png": ("/etc/passwd", b""),  # symlink
        "big.png": b"x",  # will be made oversized
        "normal.png": b"normal",
    }

    with tarfile.open(FIXTURES / "evil-icons.tar.gz", "w:gz") as tar:
        for name, content in evil_members.items():
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
        # Add oversized member (MAX_MEMBER_SIZE + 1)
        info = tarfile.TarInfo("big.png")
        info.size = 2 * 1024 * 1024 + 1  # MAX_MEMBER_SIZE + 1
        tar.addfile(info, io.BytesIO(b"\0" * info.size))

    print("Created evil-icons.tar.gz")


def extract_app_icons():
    """Extract app-icons.tar.gz to tests/fixtures/icons/ for tests."""
    icon_tar = FIXTURES / "app-icons.tar.gz"
    icons_dir = FIXTURES / "icons"
    if icon_tar.exists():
        icons_dir.mkdir(exist_ok=True)
        with tarfile.open(icon_tar, "r:gz") as tar:
            tar.extractall(icons_dir)
        print(f"Extracted app icons to {icons_dir}")
    else:
        print(f"Warning: {icon_tar} not found")


def create_apps_edge_db():
    """Create apps.edge.db with edge-case entries for testing."""
    edge_db = {
        "schema_version": 1,
        "generated_at": "2026-11-13T05:00:00Z",
        "count": 23,
        "apps": [
            {
                "id": "org.kde.kate",
                "name": "Kate Advanced Text Editor for Developers and Writers",
                "summary": "Advanced text editor",
                "description": "A powerful text editor.\nSupports plugins and sessions.",
                "repo": "KDE/kate",
                "version": "26.08.1",
                "version_changed_at": "2026-08-15T10:00:00Z",
                "download_url": "https://github.com/KDE/kate/releases/download/v26.08.1/kate.AppImage",
                "size": 45000000,
                "sha256": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
                "zsync_url": "https://github.com/KDE/kate/releases/download/v26.08.1/kate.AppImage.zsync",
                "arch": "x86_64",
                "developer": "KDE e.V.",
                "license": "GPL-2.0-only",
                "categories": ["TextEditor", "Utility"],
                "keywords": ["text", "editor", "code", "kate"],
                "urls": {"homepage": "https://kate-editor.org", "vcs-browser": "https://invent.kde.org/utilities/kate"},
                "icon": {"type": "png", "name": "org.kde.kate.png"},
                "screenshots": [{"default": True, "width": 1280, "height": 800, "url": "screenshots/kate-1.png"}],
                "invented": True
            },
            {
                "id": "org.gnome.photos",
                "name": "Φωτογραφίες και Εικόνες Διαχείρισης και Αρχειοθήκης",
                "summary": "Photo manager",
                "description": "Organize and edit your photos.",
                "repo": "GNOME/gnome-photos",
                "version": "46.0",
                "version_changed_at": "2026-09-01T08:00:00Z",
                "download_url": "https://github.com/GNOME/gnome-photos/releases/download/v46.0/photos.AppImage",
                "size": 120000000,
                "sha256": None,
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "GNOME",
                "license": "GPL-3.0-or-later",
                "categories": ["Photography"],
                "keywords": ["photo", "image", "gallery", "φωτογραφία"],
                "urls": {"homepage": "https://wiki.gnome.org/Apps/Photos"},
                "icon": {"type": "png", "name": "org.gnome.photos.png"},
                "screenshots": [
                    {"default": True, "width": 1920, "height": 1080, "url": "screenshots/photos-1.png"},
                    {"default": False, "width": 1920, "height": 1080, "url": "screenshots/photos-2.png"}
                ],
                "invented": True
            },
            {
                "id": "com.google.chrome",
                "name": "Google Chrome",
                "summary": "Web browser",
                "description": "Fast, secure web browser.",
                "repo": "Google/chrome",
                "version": "131.0.0",
                "version_changed_at": "2026-11-01T00:00:00Z",
                "download_url": "https://dl.google.com/linux/direct/google-chrome.AppImage",
                "size": 90000000,
                "sha256": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "Google LLC",
                "license": "LicenseRef-proprietary",
                "categories": ["WebBrowser"],
                "keywords": ["browser", "internet", "web"],
                "urls": {"homepage": "https://chrome.google.com", "donation": "https://chrome.google.com/donate"},
                "icon": {"type": "png", "name": "com.google.chrome.png"},
                "screenshots": [],
                "invented": True
            },
            {
                "id": "io.github.giantpinkrobot.leap",
                "name": "Leap",
                "summary": "",
                "description": "",
                "repo": "giantpinkrobot/leap",
                "version": "1.2.3",
                "version_changed_at": "2026-01-01T00:00:00Z",
                "download_url": "https://github.com/giantpinkrobot/leap/releases/download/v1.2.3/leap.AppImage",
                "size": None,
                "sha256": None,
                "zsync_url": None,
                "arch": None,
                "developer": None,
                "license": None,
                "categories": [],
                "keywords": [],
                "urls": {},
                "icon": {"type": "png", "name": "io.github.giantpinkrobot.leap.png"},
                "screenshots": None,
                "invented": True
            },
            {
                "id": "org.blender.blender",
                "name": "Blender",
                "summary": "3D creation suite",
                "description": "3D modeling, animation and rendering.",
                "repo": "Blender/blender",
                "version": "latest",
                "version_changed_at": "2026-11-10T12:00:00Z",
                "download_url": "https://download.blender.org/release/Blender4.2/blender.AppImage",
                "size": 200000000,
                "sha256": "cafebabecafebabecafebabecafebabecafebabecafebabecafebabecafebabe",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "Blender Foundation",
                "license": "GPL-2.0-or-later",
                "Categories": ["3DGraphics", "Graphics"],
                "keywords": ["3d", "modeling", "animation", "rendering"],
                "urls": {"homepage": "https://blender.org"},
                "icon": {"type": "png", "name": "org.blender.blender.png"},
                "screenshots": [{"default": True, "width": 1920, "height": 1080, "url": "screenshots/blender-1.png"}],
                "invented": True
            },
            {
                "id": "com.spotify.spotify",
                "name": "Spotify",
                "summary": "Music streaming",
                "description": "Listen to music.",
                "repo": "Spotify/spotify",
                "version": "1.2.4",
                "version_changed_at": "2026-10-01T00:00:00Z",
                "download_url": "https://download.spotify.com/spotify.AppImage",
                "size": 80000000,
                "sha256": None,
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "Spotify AB",
                "license": "LicenseRef-proprietary",
                "categories": ["AudioVideo", "Player"],
                "keywords": ["music", "streaming", "audio"],
                "urls": {"homepage": "https://spotify.com"},
                "icon": {"type": "png", "name": "com.spotify.spotify.png"},
                "screenshots": [{"default": True, "width": 1280, "height": 720, "url": "screenshots/spotify-1.png"}],
                "invented": True
            },
            {
                "id": "org.filezilla.filezilla",
                "name": "FileZilla",
                "summary": "FTP client",
                "description": "Fast and reliable FTP client.",
                "repo": "FileZilla/filezilla",
                "version": "3.68.0",
                "version_changed_at": "2026-09-15T00:00:00Z",
                "download_url": "https://download.filezilla.org/filezilla.AppImage",
                "size": 30000000,
                "sha256": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef12",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "Tim Kosse",
                "license": "GPL-2.0-only",
                "categories": ["FileTransfer"],
                "keywords": ["ftp", "sftp", "file transfer"],
                "urls": {"homepage": "https://filezilla-project.org", "bugtracker": "https://bugs.filezilla-project.org"},
                "icon": {"type": "png", "name": "org.filezilla.filezilla.png"},
                "screenshots": [{"default": True, "width": 1280, "height": 800, "url": "screenshots/filezilla-1.png"}],
                "invented": True
            },
            {
                "id": "org.videolan.vlc",
                "name": "VLC media player",
                "summary": "Media player",
                "description": "Plays most media files.",
                "repo": "VideoLAN/vlc",
                "version": "3.0.21",
                "version_changed_at": "2026-10-15T00:00:00Z",
                "download_url": "https://download.videolan.org/pub/videolan/vlc/AppImage/vlc.AppImage",
                "size": 60000000,
                "sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
                "zsync_url": None,
                "arch": "aarch64",
                "developer": "VideoLAN",
                "license": "GPL-2.0-or-later",
                "categories": ["AudioVideo", "Video", "Player"],
                "keywords": ["media", "video", "audio", "player"],
                "urls": {"homepage": "https://videolan.org"},
                "icon": {"type": "png", "name": "org.videolan.vlc.png"},
                "screenshots": [{"default": True, "width": 1280, "height": 720, "url": "screenshots/vlc-1.png"}],
                "invented": True
            },
            {
                "id": "org.libreoffice.libreoffice",
                "name": "LibreOffice",
                "summary": "Office suite",
                "description": "Word processor, spreadsheet, presentation.",
                "repo": "LibreOffice/libreoffice",
                "version": "24.8",
                "version_changed_at": "2026-08-20T00:00:00Z",
                "download_url": "https://download.libreoffice.org/libreoffice.AppImage",
                "size": 250000000,
                "sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "The Document Foundation",
                "license": "MPL-2.0",
                "categories": ["Office", "WordProcessor", "Spreadsheet", "Presentation"],
                "keywords": ["office", "writer", "calc", "impress", "document"],
                "urls": {"homepage": "https://libreoffice.org", "help": "https://help.libreoffice.org"},
                "icon": {"type": "png", "name": "org.libreoffice.libreoffice.png"},
                "screenshots": [{"default": True, "width": 1920, "height": 1080, "url": "screenshots/libreoffice-1.png"}],
                "invented": True
            },
            {
                "id": "org.gimp.gimp",
                "name": "GIMP",
                "summary": "Image editor",
                "description": "GNU Image Manipulation Program.",
                "repo": "GIMP/gimp",
                "version": "2.10.38",
                "version_changed_at": "2026-07-01T00:00:00Z",
                "download_url": "https://download.gimp.org/gimp/AppImage/gimp.AppImage",
                "size": 100000000,
                "sha256": "1111111111111111111111111111111111111111111111111111111111111111",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "GIMP Team",
                "license": "GPL-3.0-or-later",
                "categories": ["RasterGraphics", "Photography"],
                "keywords": ["image", "edit", "photo", "graphics"],
                "urls": {"homepage": "https://gimp.org"},
                "icon": {"type": "png", "name": "org.gimp.gimp.png"},
                "screenshots": [{"default": True, "width": 1920, "height": 1200, "url": "screenshots/gimp-1.png"}],
                "invented": True
            },
            {
                "id": "org.keepassxc.keepassxc",
                "name": "KeePassXC",
                "summary": "Password manager",
                "description": "Community-driven password manager.",
                "repo": "keepassxreboot/keepassxc",
                "version": "2.7.8",
                "version_changed_at": "2026-09-20T00:00:00Z",
                "download_url": "https://github.com/keepassxreboot/keepassxc/releases/download/2.7.8/KeePassXC.AppImage",
                "size": 40000000,
                "sha256": "2222222222222222222222222222222222222222222222222222222222222222",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "KeePassXC Team",
                "license": "GPL-3.0-or-later",
                "categories": ["Security"],
                "keywords": ["password", "security", "manager", "encryption"],
                "urls": {"homepage": "https://keepassxc.org", "vcs-browser": "https://github.com/keepassxreboot/keepassxc"},
                "icon": {"type": "png", "name": "org.keepassxc.keepassxc.png"},
                "screenshots": [{"default": True, "width": 1280, "height": 800, "url": "screenshots/keepassxc-1.png"}],
                "invented": True
            },
            {
                "id": "org.telegram.desktop",
                "name": "Telegram",
                "summary": "Messaging",
                "description": "Fast and secure messaging.",
                "repo": "telegramdesktop/telegramdesktop",
                "version": "5.10",
                "version_changed_at": "2026-10-25T00:00:00Z",
                "download_url": "https://github.com/telegramdesktop/tdesktop/releases/download/v5.10/telegram.AppImage",
                "size": 50000000,
                "sha256": "3333333333333333333333333333333333333333333333333333333333333333",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "Telegram FZ-LLC",
                "license": "GPL-3.0-or-later",
                "categories": ["Chat", "InstantMessaging"],
                "keywords": ["chat", "messaging", "telegram", "secure"],
                "urls": {"homepage": "https://telegram.org"},
                "icon": {"type": "png", "name": "org.telegram.desktop.png"},
                "screenshots": [{"default": True, "width": 1280, "height": 800, "url": "screenshots/telegram-1.png"}],
                "invented": True
            },
            {
                "id": "org.filezilla.missingchecksum",
                "name": "FileZilla NoChecksum",
                "summary": "FTP client",
                "description": "FTP client without a checksum.",
                "repo": "FileZilla/filezilla",
                "version": "3.68.0",
                "version_changed_at": "2026-09-15T00:00:00Z",
                "download_url": "https://download.filezilla.org/filezilla-nochecksum.AppImage",
                "size": 30000000,
                "sha256": None,
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "Tim Kosse",
                "license": "GPL-2.0-only",
                "categories": ["FileTransfer"],
                "keywords": ["ftp"],
                "urls": {"homepage": "https://filezilla-project.org"},
                "icon": {"type": "png", "name": "org.filezilla.missingchecksum.png"},
                "screenshots": [{"default": True, "width": 1280, "height": 800, "url": "screenshots/filezilla-nochecksum-1.png"}],
                "invented": True
            },
            {
                "id": "org.example.noarch",
                "name": "NoArch App",
                "summary": "No arch specified",
                "description": "App with null architecture.",
                "repo": "example/noarch",
                "version": "1.0",
                "version_changed_at": "2026-01-01T00:00:00Z",
                "download_url": "https://example.com/noarch.AppImage",
                "size": 10000000,
                "sha256": "4444444444444444444444444444444444444444444444444444444444444444",
                "zsync_url": None,
                "arch": None,
                "developer": "Example",
                "license": "MIT",
                "categories": ["Utility"],
                "keywords": ["example"],
                "urls": {"homepage": "https://example.com"},
                "icon": {"type": "png", "name": "org.example.noarch.png"},
                "screenshots": [{"default": True, "width": 800, "height": 600, "url": "screenshots/noarch-1.png"}],
                "invented": True
            },
            {
                "id": "org.example.latestapp",
                "name": "Latest App",
                "summary": "Latest version app",
                "description": "Uses latest version string.",
                "repo": "example/latest",
                "version": "latest",
                "version_changed_at": "2026-11-12T00:00:00Z",
                "download_url": "https://example.com/latest.AppImage",
                "size": 20000000,
                "sha256": "5555555555555555555555555555555555555555555555555555555555555555",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "Example",
                "license": "MIT",
                "categories": ["Utility"],
                "keywords": ["example", "latest"],
                "urls": {},
                "icon": {"type": "png", "name": "org.example.latestapp.png"},
                "screenshots": None,
                "invented": True
            },
            {
                "id": "org.example.hugekeywords",
                "name": "Huge Keywords",
                "summary": "Many keywords",
                "description": "App with a large keyword list.",
                "repo": "example/huge",
                "version": "1.0",
                "version_changed_at": "2026-01-01T00:00:00Z",
                "download_url": "https://example.com/huge.AppImage",
                "size": 5000000,
                "sha256": "6666666666666666666666666666666666666666666666666666666666666666",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "Example",
                "license": "MIT",
                "categories": ["Utility"],
                "keywords": ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron", "pi", "rho", "sigma", "tau", "upsilon", "phi", "chi", "psi", "omega", "keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
                "urls": {"homepage": "https://example.com"},
                "icon": {"type": "png", "name": "org.example.hugekeywords.png"},
                "screenshots": [{"default": True, "width": 800, "height": 600, "url": "screenshots/huge-1.png"}],
                "invented": True
            },
            {
                "id": "org.example.noicon",
                "name": "No Icon App",
                "summary": "Missing icon",
                "description": "App whose icon file is absent.",
                "repo": "example/noicon",
                "version": "1.0",
                "version_changed_at": "2026-01-01T00:00:00Z",
                "download_url": "https://example.com/noicon.AppImage",
                "size": 5000000,
                "sha256": "7777777777777777777777777777777777777777777777777777777777777777",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "Example",
                "license": "MIT",
                "categories": ["Utility"],
                "keywords": ["example"],
                "urls": {},
                "icon": {"type": "png", "name": "does-not-exist.png"},
                "screenshots": [],
                "invented": True
            },
            {
                "id": "org.kde.okular",
                "name": "Okular",
                "summary": "Document viewer",
                "description": "Universal document viewer.",
                "repo": "KDE/okular",
                "version": "24.08",
                "version_changed_at": "2026-08-30T00:00:00Z",
                "download_url": "https://github.com/KDE/okular/releases/download/v24.08/okular.AppImage",
                "size": 80000000,
                "sha256": "8888888888888888888888888888888888888888888888888888888888888888",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "KDE e.V.",
                "license": "GPL-2.0-or-later",
                "categories": ["Viewer"],
                "keywords": ["pdf", "document", "viewer"],
                "urls": {"homepage": "https://okular.org"},
                "icon": {"type": "png", "name": "org.kde.okular.png"},
                "screenshots": [{"default": True, "width": 1280, "height": 800, "url": "screenshots/okular-1.png"}],
                "invented": True
            },
            {
                "id": "org.gnome.gedit",
                "name": "gedit",
                "summary": "Text editor",
                "description": "Simple text editor for GNOME.",
                "repo": "GNOME/gedit",
                "version": "47.0",
                "version_changed_at": "2026-09-10T00:00:00Z",
                "download_url": "https://download.gnome.org/gedit.AppImage",
                "size": 25000000,
                "sha256": "9999999999999999999999999999999999999999999999999999999999999999",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "GNOME",
                "license": "GPL-2.0-or-later",
                "categories": ["TextEditor"],
                "keywords": ["text", "editor", "gnome"],
                "urls": {"homepage": "https://wiki.gnome.org/Apps/Gedit"},
                "icon": {"type": "png", "name": "org.gnome.gedit.png"},
                "screenshots": [{"default": True, "width": 1280, "height": 800, "url": "screenshots/gedit-1.png"}],
                "invented": True
            },
            {
                "id": "org.example.greek",
                "name": "Φωτογραφία",
                "summary": "Greek-named app",
                "description": "An app with a Greek name.",
                "repo": "example/greek",
                "version": "1.0",
                "version_changed_at": "2026-01-01T00:00:00Z",
                "download_url": "https://example.com/greek.AppImage",
                "size": 5000000,
                "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "Example",
                "license": "MIT",
                "categories": ["Utility"],
                "keywords": ["φωτο", "εικώνα"],
                "urls": {"homepage": "https://example.com"},
                "icon": {"type": "png", "name": "org.example.greek.png"},
                "screenshots": [{"default": True, "width": 800, "height": 600, "url": "screenshots/greek-1.png"}],
                "invented": True
            },
            {
                "id": "org.example.nodownloadurl",
                "name": "No Download URL",
                "summary": "No download",
                "description": "Entry missing download_url (should be skipped).",
                "repo": "example/nodl",
                "version": "1.0",
                "version_changed_at": "2026-01-01T00:00:00Z",
                "download_url": None,
                "size": 5000000,
                "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "Example",
                "license": "MIT",
                "categories": ["Utility"],
                "keywords": ["example"],
                "urls": {},
                "icon": {"type": "png", "name": "org.example.nodownloadurl.png"},
                "screenshots": [],
                "invented": True
            },
            {
                "id": "org.mozilla.firefox",
                "name": "Firefox",
                "summary": "Web browser",
                "description": "Fast, private web browser.",
                "repo": "Mozilla/firefox",
                "version": "132.0",
                "version_changed_at": "2026-11-05T00:00:00Z",
                "download_url": "https://ftp.mozilla.org/pub/firefox/releases/132.0/linux-x86_64/AppImage/firefox.AppImage",
                "size": 95000000,
                "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "Mozilla Foundation",
                "license": "MPL-2.0",
                "categories": ["WebBrowser"],
                "keywords": ["browser", "web", "internet", "firefox"],
                "urls": {"homepage": "https://mozilla.org/firefox", "vcs-browser": "https://hg.mozilla.org/mozilla-central"},
                "icon": {"type": "png", "name": "org.mozilla.firefox.png"},
                "screenshots": [{"default": True, "width": 1920, "height": 1080, "url": "screenshots/firefox-1.png"}],
                "invented": True
            },
            {
                "id": "org.gnome.calculator",
                "name": "Calculator",
                "summary": "Calculator",
                "description": "Simple calculator.",
                "repo": "GNOME/gnome-calculator",
                "version": "47.0",
                "version_changed_at": "2026-09-05T00:00:00Z",
                "download_url": "https://download.gnome.org/gnome-calculator.AppImage",
                "size": 10000000,
                "sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
                "zsync_url": None,
                "arch": "x86_64",
                "developer": "GNOME",
                "license": "GPL-3.0-or-later",
                "categories": ["Calculator", "Utility"],
                "keywords": ["calculator", "math", "arithmetic"],
                "urls": {"homepage": "https://wiki.gnome.org/Apps/Calculator"},
                "icon": {"type": "png", "name": "org.gnome.calculator.png"},
                "screenshots": [{"default": True, "width": 800, "height": 600, "url": "screenshots/calculator-1.png"}],
                "invented": True
            }
        ],
        "invented": True
    }

    with open(FIXTURES / "apps.edge.db", "w") as f:
        json.dump(edge_db, f, indent=2)

    print("Created apps.edge.db")


if __name__ == "__main__":
    create_evil_icons()
    create_apps_edge_db()
    extract_app_icons()
    print("All fixtures regenerated")