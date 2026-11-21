#!/bin/bash
# Test installation locally without sudo

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_PREFIX="$SCRIPT_DIR/.test-install"

echo "======================================"
echo "  Testing Aurelis Software Installer  "
echo "======================================"
echo ""
echo "Installing to: $TEST_PREFIX"
echo ""

# Clean previous test installation
rm -rf "$TEST_PREFIX"

# Run installer with test prefix
PREFIX="$TEST_PREFIX" "$SCRIPT_DIR/install.sh"

echo ""
echo "==> Verifying installation..."

# Check if files exist
ERRORS=0

if [ ! -f "$TEST_PREFIX/bin/aurelis-software" ]; then
    echo "✗ Launcher script not found"
    ERRORS=$((ERRORS + 1))
else
    echo "✓ Launcher script installed"
fi

if [ ! -f "$TEST_PREFIX/share/applications/aurelis-software.desktop" ]; then
    echo "✗ Desktop file not found"
    ERRORS=$((ERRORS + 1))
else
    echo "✓ Desktop file installed"
fi

if [ ! -f "$TEST_PREFIX/share/icons/hicolor/scalable/apps/aurelis-software.svg" ]; then
    echo "✗ Icon not found"
    ERRORS=$((ERRORS + 1))
else
    echo "✓ Icon installed"
fi

# Check if Python package is installed
if ! python3 -c "import aurelis_software" 2>/dev/null; then
    echo "✗ Python package not importable"
    ERRORS=$((ERRORS + 1))
else
    echo "✓ Python package installed"
fi

echo ""
if [ $ERRORS -eq 0 ]; then
    echo "✓ All checks passed!"
    echo ""
    echo "To test the installed launcher:"
    echo "  $TEST_PREFIX/bin/aurelis-software --help"
    echo ""
    echo "To clean up test installation:"
    echo "  rm -rf $TEST_PREFIX"
    exit 0
else
    echo "✗ $ERRORS check(s) failed"
    exit 1
fi
