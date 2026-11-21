#!/bin/bash
set -e

# Aurelis Software Center Installer
# For Arch Linux / KDE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-/usr/local}"
INSTALL_DIR="$PREFIX/share/aurelis-software"
BIN_DIR="$PREFIX/bin"
APPLICATIONS_DIR="$PREFIX/share/applications"
ICONS_DIR="$PREFIX/share/icons/hicolor"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "======================================"
echo "  Aurelis Software Center Installer  "
echo "======================================"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ] && [ -z "$SUDO_USER" ]; then
    echo -e "${YELLOW}Warning: Running as root. Installation will be system-wide.${NC}"
    echo ""
fi

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a package is installed (Arch)
package_installed() {
    pacman -Qi "$1" >/dev/null 2>&1
}

echo "==> Checking dependencies..."
MISSING_DEPS=()
MISSING_OPTIONAL=()

# Check required dependencies
if ! command_exists python3; then
    MISSING_DEPS+=("python")
fi

if ! command_exists pip; then
    MISSING_DEPS+=("python-pip")
fi

if ! python3 -c "import PyQt6" 2>/dev/null; then
    MISSING_DEPS+=("python-pyqt6")
fi

# Check optional dependencies
if ! package_installed appimage-launcher; then
    MISSING_OPTIONAL+=("appimage-launcher")
fi

if ! package_installed flatpak; then
    MISSING_OPTIONAL+=("flatpak")
fi

# Handle missing required dependencies
if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo -e "${RED}Missing required dependencies: ${MISSING_DEPS[*]}${NC}"
    echo ""
    
    if command_exists pacman; then
        read -p "Would you like to install them now? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "==> Installing dependencies..."
            sudo pacman -S --needed "${MISSING_DEPS[@]}"
        else
            echo -e "${RED}Cannot continue without required dependencies.${NC}"
            exit 1
        fi
    else
        echo "Please install the following packages manually:"
        for dep in "${MISSING_DEPS[@]}"; do
            echo "  - $dep"
        done
        exit 1
    fi
fi

# Report optional dependencies
if [ ${#MISSING_OPTIONAL[@]} -gt 0 ]; then
    echo -e "${YELLOW}Optional dependencies not installed: ${MISSING_OPTIONAL[*]}${NC}"
    echo "These provide additional functionality:"
    if [[ " ${MISSING_OPTIONAL[*]} " =~ " appimage-launcher " ]]; then
        echo "  - appimage-launcher: Manage AppImage applications"
    fi
    if [[ " ${MISSING_OPTIONAL[*]} " =~ " flatpak " ]]; then
        echo "  - flatpak: Install Flatpak applications from Flathub"
    fi
    echo ""
    
    read -p "Would you like to install optional dependencies? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "==> Installing optional dependencies..."
        sudo pacman -S --needed "${MISSING_OPTIONAL[@]}"
        
        # Configure Flathub if flatpak was just installed
        if [[ " ${MISSING_OPTIONAL[*]} " =~ " flatpak " ]]; then
            echo "==> Configuring Flathub repository..."
            flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
        fi
    fi
fi

echo -e "${GREEN}✓ All required dependencies satisfied${NC}"
echo ""

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.11"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}Python $REQUIRED_VERSION or higher is required (found $PYTHON_VERSION)${NC}"
    exit 1
fi

echo "==> Installing Aurelis Software Center..."

# Install Python package
echo "    Installing Python package..."
cd "$SCRIPT_DIR"
pip install --user --upgrade .

# Create installation directories
echo "    Creating installation directories..."
sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$BIN_DIR"
sudo mkdir -p "$APPLICATIONS_DIR"
sudo mkdir -p "$ICONS_DIR/scalable/apps"
sudo mkdir -p "$ICONS_DIR/48x48/apps"
sudo mkdir -p "$ICONS_DIR/64x64/apps"
sudo mkdir -p "$ICONS_DIR/128x128/apps"

# Install icon
if [ -f "$SCRIPT_DIR/resources/icons/aurelis-software.svg" ]; then
    echo "    Installing icon..."
    sudo cp "$SCRIPT_DIR/resources/icons/aurelis-software.svg" "$ICONS_DIR/scalable/apps/"
else
    echo -e "${YELLOW}    Warning: Icon not found at resources/icons/aurelis-software.svg${NC}"
fi

# Install desktop files
echo "    Installing desktop entries..."
sudo cp "$SCRIPT_DIR/resources/aurelis-software.desktop" "$APPLICATIONS_DIR/"
sudo cp "$SCRIPT_DIR/resources/aurelis-software-wizard-install.desktop" "$APPLICATIONS_DIR/"
sudo cp "$SCRIPT_DIR/resources/aurelis-software-uninstall.desktop" "$APPLICATIONS_DIR/"

# Create launcher script
echo "    Creating launcher script..."
cat << 'EOF' | sudo tee "$BIN_DIR/aurelis-software" > /dev/null
#!/bin/bash
python3 -m aurelis_software "$@"
EOF
sudo chmod +x "$BIN_DIR/aurelis-software"

# Update desktop database and icon cache
echo "    Updating desktop database..."
if command_exists update-desktop-database; then
    sudo update-desktop-database "$APPLICATIONS_DIR" 2>/dev/null || true
fi

if command_exists gtk-update-icon-cache; then
    sudo gtk-update-icon-cache -f -t "$ICONS_DIR" 2>/dev/null || true
fi

echo ""
echo -e "${GREEN}======================================"
echo "  Installation completed successfully!"
echo "======================================${NC}"
echo ""
echo "You can now launch Aurelis Software Center from:"
echo "  • Application menu (KDE: Application Launcher → System)"
echo "  • Command line: aurelis-software"
echo ""
echo "Installation details:"
echo "  • Executable: $BIN_DIR/aurelis-software"
echo "  • Desktop files: $APPLICATIONS_DIR/aurelis-software*.desktop"
echo "  • Icons: $ICONS_DIR/scalable/apps/aurelis-software.svg"
echo ""
echo "To uninstall, run: $SCRIPT_DIR/uninstall.sh"
echo ""
