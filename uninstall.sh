#!/bin/bash
# Claude Secrets uninstaller
# Usage: curl -sSL https://raw.githubusercontent.com/henghonglee/claude-secrets/main/uninstall.sh | bash

set -e

echo "Uninstalling claude-secrets..."

# Run uninstall command if available
if command -v ccs &> /dev/null; then
    ccs uninstall
fi

# Remove package
if command -v pipx &> /dev/null; then
    pipx uninstall claude-secrets 2>/dev/null || true
else
    pip uninstall claude-secrets -y 2>/dev/null || true
fi

echo ""
echo "Done! Your secrets are preserved in ~/.claude-secrets/"
echo "To also delete secrets: rm -rf ~/.claude-secrets"
