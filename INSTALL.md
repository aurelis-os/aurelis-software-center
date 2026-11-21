# Installation Guide - Aurelis Software Center

## Quick Install (Arch Linux)

```bash
cd /path/to/aurelis-software-center
chmod +x install.sh
./install.sh
```

The installer will:
- Check for required dependencies (Python 3.11+, PyQt6)
- Offer to install missing dependencies via pacman
- Offer to install optional dependencies (appimage-launcher, flatpak)
- Install the application system-wide
- Add desktop entries to your application menu
- Install the application icon

## Requirements

### Required
- Python 3.11 or higher
- PyQt6 6.6 or higher
- pip (Python package manager)

### Optional (for full functionality)
- `appimage-launcher` - Manage AppImage applications
- `flatpak` - Install applications from Flathub
- `pacman` - Native Arch package management (already installed on Arch)

## Installation Options

### System-wide Installation (Recommended)

Installs to `/usr/local` by default:

```bash
./install.sh
```

### Custom Installation Prefix

Install to a custom location:

```bash
PREFIX=/opt ./install.sh
```

### Manual Installation

If you prefer to install manually:

```bash
# Install dependencies
sudo pacman -S python python-pyqt6 python-pip

# Optional dependencies
sudo pacman -S appimage-launcher flatpak

# Configure Flathub (if using flatpak)
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

# Install Python package
pip install --user .

# Copy desktop files
sudo cp resources/aurelis-software.desktop /usr/share/applications/
sudo cp resources/aurelis-software-wizard-install.desktop /usr/share/applications/
sudo cp resources/aurelis-software-uninstall.desktop /usr/share/applications/

# Copy icon
sudo mkdir -p /usr/share/icons/hicolor/scalable/apps
sudo cp resources/icons/aurelis-software.svg /usr/share/icons/hicolor/scalable/apps/

# Update desktop database
sudo update-desktop-database /usr/share/applications
sudo gtk-update-icon-cache -f -t /usr/share/icons/hicolor
```

## Running the Application

After installation, you can launch Aurelis Software Center:

### From KDE Application Launcher
1. Open the Application Launcher (Alt+F1)
2. Navigate to System → Aurelis Software

### From Command Line
```bash
aurelis-software
```

### Installation Wizard (for AppImages)
```bash
aurelis-software wizard install /path/to/app.AppImage
```

### Uninstallation Wizard
```bash
aurelis-software wizard uninstall /path/to/installed/app
```

## Uninstallation

To remove Aurelis Software Center:

```bash
cd /path/to/aurelis-software-center
./uninstall.sh
```

Or manually:

```bash
# Remove Python package
pip uninstall aurelis-software

# Remove desktop files
sudo rm /usr/share/applications/aurelis-software*.desktop

# Remove icon
sudo rm /usr/share/icons/hicolor/scalable/apps/aurelis-software.svg

# Update databases
sudo update-desktop-database /usr/share/applications
sudo gtk-update-icon-cache -f -t /usr/share/icons/hicolor
```

## Troubleshooting

### Icon not showing in KDE
```bash
# Refresh icon cache
sudo gtk-update-icon-cache -f -t /usr/share/icons/hicolor
kbuildsycoca6  # KDE 6
```

### Desktop file not appearing
```bash
# Update desktop database
sudo update-desktop-database /usr/share/applications

# Force KDE menu refresh
kbuildsycoca6  # KDE 6
```

### Python package not found
Make sure `~/.local/bin` is in your PATH:
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Missing dependencies error
Install all required dependencies:
```bash
sudo pacman -S python python-pyqt6 python-pip
```

## Development Installation

For development, install in editable mode:

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Run checks (linting, formatting, tests)
./check

# Run tests only
pytest

# Run application from source
python -m aurelis_software
```

## KDE Integration

The application is designed to integrate seamlessly with KDE Plasma:
- Uses SVG icon for crisp rendering at any size
- Follows KDE desktop entry specifications
- Appears in the System category of the application menu
- Uses native KDE/Qt6 styling

## File Locations

After installation:
- Executable: `/usr/local/bin/aurelis-software`
- Desktop files: `/usr/local/share/applications/aurelis-software*.desktop`
- Icon: `/usr/local/share/icons/hicolor/scalable/apps/aurelis-software.svg`
- Python package: `~/.local/lib/python3.*/site-packages/aurelis_software/`

## License

Proprietary — Aurelis Software
