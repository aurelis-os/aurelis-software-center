#!/bin/bash
set -e

# Aurelis Software Center Uninstaller

PREFIX="${PREFIX:-/usr/local}"
BIN_DIR="$PREFIX/bin"
APPLICATIONS_DIR="$PREFIX/share/applications"
ICONS_DIR="$PREFIX/share/icons/hicolor"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "  Aurelis Software Center Uninstaller  "
echo "========================================="
echo ""

read -p "Are you sure you want to uninstall Aurelis Software Center? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstallation cancelled."
    exit 0
fi

echo "==> Uninstalling Aurelis Software Center..."

# Remove launcher script
if [ -f "$BIN_DIR/aurelis-software" ]; then
    echo "    Removing launcher script..."
    sudo rm -f "$BIN_DIR/aurelis-software"
fi

# Remove desktop files
echo "    Removing desktop entries..."
sudo rm -f "$APPLICATIONS_DIR/aurelis-software.desktop"
sudo rm -f "$APPLICATIONS_DIR/aurelis-software-wizard-install.desktop"
sudo rm -f "$APPLICATIONS_DIR/aurelis-software-uninstall.desktop"

# Remove icons
echo "    Removing icons..."
sudo rm -f "$ICONS_DIR/scalable/apps/aurelis-software.svg"
sudo rm -f "$ICONS_DIR/48x48/apps/aurelis-software.png"
sudo rm -f "$ICONS_DIR/64x64/apps/aurelis-software.png"
sudo rm -f "$ICONS_DIR/128x128/apps/aurelis-software.png"

# Uninstall Python package
echo "    Uninstalling Python package..."
pip uninstall -y aurelis-software 2>/dev/null || true

# Update desktop database and icon cache
echo "    Updating desktop database..."
if command -v update-desktop-database >/dev/null 2>&1; then
    sudo update-desktop-database "$APPLICATIONS_DIR" 2>/dev/null || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    sudo gtk-update-icon-cache -f -t "$ICONS_DIR" 2>/dev/null || true
fi

echo ""
echo -e "${GREEN}========================================="
echo "  Uninstallation completed successfully!"
echo "=========================================${NC}"
echo ""
