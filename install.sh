#!/bin/bash
# Claude Secrets installer
# Usage: curl -sSL https://raw.githubusercontent.com/henghonglee/claude-secrets/main/install.sh | bash

set -e

echo "Installing claude-secrets..."

# Check for pipx
if command -v pipx &> /dev/null; then
    pipx install git+https://github.com/henghonglee/claude-secrets.git
elif command -v pip &> /dev/null; then
    pip install --user git+https://github.com/henghonglee/claude-secrets.git
else
    echo "Error: pipx or pip required. Install with: brew install pipx"
    exit 1
fi

echo ""
echo "Running setup..."
ccs init

echo ""
echo "Done! claude-secrets is ready to use."
