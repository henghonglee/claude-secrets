"""
py2app setup for Claude Secrets Menu Bar app.

Build with:
    python setup_app.py py2app
"""

import sys
from setuptools import setup

# Add src to path so py2app can find our package
sys.path.insert(0, 'src')

APP = ['app_launcher.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'app_icon.icns',
    'plist': {
        'CFBundleName': 'Claude Secrets',
        'CFBundleDisplayName': 'Claude Secrets',
        'CFBundleIdentifier': 'com.claudesecrets.menubar',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': True,  # Menu bar app (no dock icon)
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.13.0',
    },
    'packages': [
        'claude_secrets',
        'rumps',
        'keyring',
        'cryptography',
        'rich',
        'click',
        'cffi',
        'jaraco',
        'markdown_it',
        'pygments',
    ],
    'includes': [
        'claude_secrets.vault',
        'claude_secrets.config',
        'claude_secrets.menubar',
        'keyring.backends',
        'keyring.backends.macOS',
    ],
    'excludes': [
        # Exclude heavy packages not needed for menu bar
        'mcp',
        'openai',
        'httpx',
        'pydantic',
        'pytest',
        'numpy',
        'pandas',
    ],
    'site_packages': True,
}

setup(
    name='Claude Secrets',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
