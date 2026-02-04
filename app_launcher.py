#!/usr/bin/env python3
"""Launcher script for Claude Secrets menu bar app."""

import sys
import os

# Ensure the package can be found
if getattr(sys, 'frozen', False):
    # Running as compiled app
    app_dir = os.path.dirname(sys.executable)
    # Add Resources directory to path for py2app
    resources_dir = os.path.join(os.path.dirname(app_dir), 'Resources')
    if resources_dir not in sys.path:
        sys.path.insert(0, resources_dir)

from claude_secrets.menubar import run_menubar

if __name__ == "__main__":
    run_menubar()
