#!/bin/bash
set -e

echo "=== Building Claude Secrets macOS App ==="

# Ensure we're in the project directory
cd "$(dirname "$0")"

# Activate virtual environment
source .venv/bin/activate

# Install build dependencies
echo "Installing build dependencies..."
pip install py2app pillow

# Generate app icon if it doesn't exist
if [ ! -f "app_icon.icns" ]; then
    echo "Generating app icon..."
    python generate_icon.py
fi

# Clean previous builds
rm -rf build dist

# Build the app
echo "Building .app bundle..."
python setup_app.py py2app

# Verify the app was built
if [ ! -d "dist/Claude Secrets.app" ]; then
    echo "Error: App bundle was not created"
    exit 1
fi

echo "App bundle created at: dist/Claude Secrets.app"

# Create DMG
echo "Creating DMG..."
DMG_NAME="Claude-Secrets-1.0.0.dmg"
DMG_TEMP="dist/temp.dmg"
DMG_FINAL="dist/$DMG_NAME"

# Remove old DMG if exists
rm -f "$DMG_FINAL"

# Create a temporary DMG
hdiutil create -size 200m -fs HFS+ -volname "Claude Secrets" "$DMG_TEMP"

# Mount the DMG
MOUNT_POINT=$(hdiutil attach "$DMG_TEMP" | grep "/Volumes" | awk '{print $3}')

# Copy the app
cp -R "dist/Claude Secrets.app" "$MOUNT_POINT/"

# Create a symlink to Applications
ln -s /Applications "$MOUNT_POINT/Applications"

# Create a background instructions file
cat > "$MOUNT_POINT/.background_instructions.txt" << 'EOF'
Drag Claude Secrets to Applications to install.

After installation:
1. Open Terminal
2. Run: pip install claude-secrets
3. Run: ccs init
4. Launch Claude Secrets from Applications
EOF

# Unmount
hdiutil detach "$MOUNT_POINT"

# Convert to compressed DMG
hdiutil convert "$DMG_TEMP" -format UDZO -o "$DMG_FINAL"

# Clean up
rm -f "$DMG_TEMP"

echo ""
echo "=== Build Complete ==="
echo "DMG created at: dist/$DMG_NAME"
echo ""
echo "To install:"
echo "  1. Open the DMG"
echo "  2. Drag 'Claude Secrets' to Applications"
echo "  3. Launch from Applications or Spotlight"
