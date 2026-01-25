#!/bin/bash
# MCP Secrets uninstaller
# Usage: curl -sSL https://raw.githubusercontent.com/henghonglee/mcp-secrets/main/uninstall.sh | bash

set -e

echo "Uninstalling mcp-secrets..."

# Run uninstall command if available
if command -v mcp-secrets &> /dev/null; then
    mcp-secrets uninstall
fi

# Remove package
if command -v pipx &> /dev/null; then
    pipx uninstall mcp-secrets 2>/dev/null || true
else
    pip uninstall mcp-secrets -y 2>/dev/null || true
fi

echo ""
echo "Done! Your secrets are preserved in ~/.mcp-secrets/"
echo "To also delete secrets: rm -rf ~/.mcp-secrets"
