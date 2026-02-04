#!/usr/bin/env python3
"""Build script for Claude Secrets macOS app using PyInstaller."""

import os
import subprocess
import sys
import shutil
from pathlib import Path


def main():
    # Ensure we're in the right directory
    os.chdir(Path(__file__).parent)

    # Install PyInstaller if needed
    print("Installing PyInstaller...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # Generate icon if needed
    if not Path("app_icon.icns").exists():
        print("Generating app icon...")
        subprocess.run([sys.executable, "generate_icon.py"], check=True)

    # Clean previous builds
    for d in ["build", "dist"]:
        if Path(d).exists():
            shutil.rmtree(d)

    # Create spec file content
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app_launcher.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'claude_secrets',
        'claude_secrets.vault',
        'claude_secrets.config',
        'claude_secrets.menubar',
        'rumps',
        'keyring',
        'keyring.backends',
        'keyring.backends.macOS',
        'cryptography',
        'cryptography.fernet',
        'cryptography.hazmat.primitives.kdf.pbkdf2',
        'cffi',
        'rich',
        'rich.console',
        'rich.table',
        'rich.prompt',
        'click',
        'jaraco',
        'jaraco.classes',
        'jaraco.functools',
        'jaraco.context',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'mcp',
        'openai',
        'httpx',
        'pydantic',
        'pytest',
        'numpy',
        'pandas',
        'matplotlib',
        'scipy',
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Claude Secrets',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Claude Secrets',
)

app = BUNDLE(
    coll,
    name='Claude Secrets.app',
    icon='app_icon.icns',
    bundle_identifier='com.claudesecrets.menubar',
    info_plist={
        'CFBundleName': 'Claude Secrets',
        'CFBundleDisplayName': 'Claude Secrets',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': True,
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.13.0',
    },
)
'''

    # Write spec file
    Path("ClaudeSecrets.spec").write_text(spec_content)

    # Run PyInstaller
    print("Building app with PyInstaller...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "ClaudeSecrets.spec", "--noconfirm"],
        capture_output=False
    )

    if result.returncode != 0:
        print("Build failed!")
        sys.exit(1)

    # Check if app was created
    app_path = Path("dist/Claude Secrets.app")
    if not app_path.exists():
        print("Error: App bundle was not created")
        sys.exit(1)

    print(f"\nApp bundle created at: {app_path}")

    # Create DMG
    create_dmg()


def create_dmg():
    """Create a DMG file for distribution."""
    print("\nCreating DMG...")

    dmg_name = "Claude-Secrets-1.0.0.dmg"
    dmg_temp = Path("dist/temp.dmg")
    dmg_final = Path(f"dist/{dmg_name}")

    # Remove old DMG if exists
    dmg_final.unlink(missing_ok=True)
    dmg_temp.unlink(missing_ok=True)

    # Create a temporary DMG
    subprocess.run([
        "hdiutil", "create",
        "-size", "200m",
        "-fs", "HFS+",
        "-volname", "Claude Secrets",
        str(dmg_temp)
    ], check=True)

    # Mount the DMG
    result = subprocess.run(
        ["hdiutil", "attach", str(dmg_temp)],
        capture_output=True,
        text=True,
        check=True
    )

    # Find mount point
    mount_point = None
    for line in result.stdout.split("\n"):
        if "/Volumes" in line:
            mount_point = line.split("\t")[-1].strip()
            break

    if not mount_point:
        print("Error: Could not find mount point")
        sys.exit(1)

    try:
        # Copy the app
        subprocess.run([
            "cp", "-R",
            "dist/Claude Secrets.app",
            f"{mount_point}/"
        ], check=True)

        # Create symlink to Applications
        subprocess.run([
            "ln", "-s",
            "/Applications",
            f"{mount_point}/Applications"
        ], check=True)

    finally:
        # Unmount
        subprocess.run(["hdiutil", "detach", mount_point], check=True)

    # Convert to compressed DMG
    subprocess.run([
        "hdiutil", "convert",
        str(dmg_temp),
        "-format", "UDZO",
        "-o", str(dmg_final)
    ], check=True)

    # Clean up
    dmg_temp.unlink(missing_ok=True)

    print(f"\n{'='*50}")
    print("BUILD COMPLETE")
    print(f"{'='*50}")
    print(f"DMG created at: dist/{dmg_name}")
    print(f"\nTo install:")
    print(f"  1. Open dist/{dmg_name}")
    print(f"  2. Drag 'Claude Secrets' to Applications")
    print(f"  3. Launch from Applications or Spotlight")


if __name__ == "__main__":
    main()
