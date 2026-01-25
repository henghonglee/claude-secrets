#!/bin/bash
# MCP Secrets installer
# Usage: curl -sSL https://raw.githubusercontent.com/henghonglee/mcp-secrets/main/install.sh | bash

set -e

echo "Installing mcp-secrets..."

# Check for pipx
if command -v pipx &> /dev/null; then
    pipx install git+https://github.com/henghonglee/mcp-secrets.git
elif command -v pip &> /dev/null; then
    pip install --user git+https://github.com/henghonglee/mcp-secrets.git
else
    echo "Error: pipx or pip required. Install with: brew install pipx"
    exit 1
fi

echo ""
echo "Running setup..."
mcp-secrets init

echo ""
echo "Done! mcp-secrets is ready to use."
