# Claude Secrets Proxy

**Project Location:** `/Users/henghonglee/ai-projects/claude-secrets/`

An intelligent CLI secrets manager for any MCP-compatible client, installable via Homebrew.

## Overview

A Python CLI application + MCP server with an **Ollama-powered local LLM** that:

1. **Smart Secret Detection** - Local model parses CLI output to identify and save secrets
2. **Semantic Secret Discovery** - Describe what you need, finds matching secrets
3. **Session-Based Permissions** - User approves secret access once per session
4. **Contextual Storage** - Secrets saved with descriptions for intelligent retrieval

Works with any MCP client: Claude Code, Cursor, Continue, Zed, custom integrations, etc.

**Supported Platforms:** macOS and Linux (uses Keychain on macOS, libsecret on Linux)

## Installation

```bash
brew tap lightsprint/claude-secrets
brew install claude-secrets
```

After installation:
```bash
# Initialize the vault (creates encrypted storage)
claude-secrets init

# Start the MCP server (or configure to run on login)
claude-secrets serve

# Show MCP configuration snippet
claude-secrets config
```

## Architecture

```
┌─────────────────┐         ┌─────────────────────────────────────────────┐
│   MCP Client    │────────▶│         Claude Secrets Proxy                   │
│ (any client)    │         │                                             │
└─────────────────┘         │  ┌───────────────────────────────────────┐  │
                            │  │           Ollama (Local LLM)          │  │
                            │  │  • Parse responses for secrets        │  │
                            │  │  • Semantic search for secrets        │  │
                            │  │  • Generate secret descriptions       │  │
                            │  └───────────────────────────────────────┘  │
                            │                    │                        │
                            │  ┌─────────────────┴─────────────────────┐  │
                            │  │         Secret Vault                  │  │
                            │  │  ~/.claude-secrets/vault.enc             │  │
                            │  └───────────────────────────────────────┘  │
                            │                    │                        │
                            │  ┌─────────────────┴─────────────────────┐  │
                            │  │      Session Permissions              │  │
                            │  │      (in-memory, per-session)         │  │
                            │  └───────────────────────────────────────┘  │
                            └─────────────────────────────────────────────┘
```

## CLI Commands

### `claude-secrets init`
Initialize the secrets vault.
- Creates `~/.claude-secrets/` directory
- Generates encryption key and stores in macOS Keychain
- Creates empty encrypted vault

### `claude-secrets serve`
Start the MCP server.
- Runs on stdio (for MCP integration)
- Options:
  - `--port` for HTTP mode (debugging)
  - `--session-timeout <duration>` permission expiry time (default: 1h, e.g., 30m, 2h, 8h)
- **Requires Ollama**: Will refuse to start if Ollama is not running

### `claude-secrets add <name>`
Add a new secret interactively.
```bash
claude-secrets add AWS_PROD_KEY
# Prompts for:
#   Value: ********
#   Description: Production AWS access key for account 123456
#   Tags (comma-separated): aws, production
```

### `claude-secrets list`
List all secrets (names + descriptions only).
```bash
claude-secrets list
# AWS_PROD_KEY      - Production AWS access key for account 123456 [aws, production]
# GITHUB_TOKEN      - Personal access token for github.com/user [github, api]
```

### `claude-secrets search <query>`
Semantic search for secrets.
```bash
claude-secrets search "AWS credentials for production"
# 1. AWS_PROD_KEY (score: 0.95) - Production AWS access key
# 2. AWS_DEV_KEY (score: 0.42) - Development AWS access key
```

### `claude-secrets remove <name>`
Remove a secret from the vault.

### `claude-secrets export`
Export secrets (encrypted) for backup.

### `claude-secrets import <file>`
Import secrets from backup.

### `claude-secrets config`
Print MCP server configuration snippet for your client.
```bash
claude-secrets config
# Outputs JSON/YAML config to add to your MCP client
```

### `claude-secrets logs`
View recent audit logs.
```bash
claude-secrets logs --tail 20
# 2024-01-15 10:30:22 - ACCESS - AWS_PROD_KEY - granted - aws s3 ls
# 2024-01-15 10:30:45 - DETECT - Found potential secret in output
```

## MCP Tool Interface

### `run_command`
Execute a CLI command with secret injection and output processing.

**Parameters:**
- `command` (string): CLI command with `{{SECRET_NAME}}` placeholders
- `timeout` (int, optional): Timeout in seconds (default: 60)

**Behavior:**
1. Parse `{{PLACEHOLDER}}` tokens from command
2. Check session permissions for each secret (prompt user if not granted)
3. Substitute placeholders with secret values
4. Execute command
5. Scan output with Ollama for potential new secrets
6. Redact known secrets from output
7. Return sanitized output

**Returns:**
```json
{
  "stdout": "...",
  "stderr": "...",
  "exit_code": 0,
  "secrets_detected": 1,
  "message": "Found 1 potential secret in output. Run 'claude-secrets pending' to review."
}
```

### `search_secrets`
Semantic search for secrets by description.

**Parameters:**
- `query` (string): Natural language description

**Returns:**
```json
{
  "matches": [
    {"name": "AWS_PROD_KEY", "description": "...", "score": 0.95},
    {"name": "AWS_DEV_KEY", "description": "...", "score": 0.42}
  ]
}
```

### `list_secrets`
List available secrets.

**Parameters:**
- `tag` (string, optional): Filter by tag

**Returns:**
```json
{
  "secrets": [
    {"name": "AWS_PROD_KEY", "description": "...", "tags": ["aws", "prod"]},
    {"name": "GITHUB_TOKEN", "description": "...", "tags": ["github"]}
  ]
}
```

### `get_permissions`
Get current session permission status.

**Returns:**
```json
{
  "permissions": [
    {"name": "AWS_PROD_KEY", "status": "granted"},
    {"name": "GITHUB_TOKEN", "status": "pending"}
  ]
}
```

## Permission Flow

When an MCP client uses a secret for the first time in a session:

```
MCP Client: run_command("aws s3 ls {{AWS_PROD_KEY}}")
                              ↓
MCP Server detects AWS_PROD_KEY needs permission
                              ↓
Returns to client:
{
  "error": "permission_required",
  "secret": "AWS_PROD_KEY",
  "message": "User approval needed. Waiting for permission..."
}
                              ↓
CLI prompts user (in terminal where server runs):
┌─────────────────────────────────────────────────┐
│ MCP client wants to use secret: AWS_PROD_KEY    │
│ Description: Production AWS access key          │
│ Command: aws s3 ls {{AWS_PROD_KEY}}             │
│                                                 │
│ Allow for this session? [y/N]                   │
└─────────────────────────────────────────────────┘
                              ↓
User types 'y' → Permission granted (expires after session-timeout)
                              ↓
Command executes, output returned (redacted)
```

**Permission Expiry:** Permissions are time-based and expire after the configured `--session-timeout` (default: 1 hour). After expiry, the user will be prompted again.

## LLM Integration

An LLM is **required** for claude-secrets to function. The server will refuse to start if it cannot connect to the configured LLM endpoint.

Supports any OpenAI-compatible chat completions API:
- **Ollama** (recommended for local/private use)
- **OpenAI API**
- **Azure OpenAI**
- **LM Studio**
- **vLLM**
- Any other OpenAI-compatible endpoint

### Configuration
```bash
# Option 1: Ollama (default, local)
claude-secrets config set llm.base_url http://localhost:11434/v1
claude-secrets config set llm.model llama3.2:3b

# Option 2: OpenAI
claude-secrets config set llm.base_url https://api.openai.com/v1
claude-secrets config set llm.model gpt-4o-mini
claude-secrets config set llm.api_key sk-...

# Option 3: Any OpenAI-compatible endpoint
claude-secrets config set llm.base_url https://your-endpoint.com/v1
claude-secrets config set llm.model your-model
claude-secrets config set llm.api_key your-key
```

### Ollama Setup (Recommended for Local Use)
```bash
# Install Ollama
# macOS:
brew install ollama
# Linux:
curl -fsSL https://ollama.com/install.sh | sh

# Pull the default model (fast and lightweight)
ollama pull llama3.2:3b

# Start Ollama
ollama serve
```

### LLM Usage

**Secret Detection** - When command output might contain secrets:
```
Prompt: "Analyze this output for secrets (API keys, tokens, passwords, credentials).
Output: {stdout}
Return JSON: {secrets: [{value, type, suggested_name, suggested_description}]}"
```

**Semantic Search** - Finding relevant secrets:
```
Prompt: "Given these secrets with descriptions:
{list of name: description pairs}
Find best matches for: '{user_query}'
Return JSON: {matches: [{name, score, reason}]}"
```

## Project Structure

```
claude-secrets/
├── pyproject.toml              # Package config, dependencies, entry points
├── README.md
├── LICENSE
├── src/
│   └── claude_secrets/
│       ├── __init__.py
│       ├── cli.py              # Click CLI commands
│       ├── server.py           # MCP server implementation
│       ├── vault.py            # Encrypted secret storage
│       ├── permissions.py      # Session permission management
│       ├── llm.py              # OpenAI-compatible LLM client
│       ├── detector.py         # LLM-based secret detection
│       ├── search.py           # Semantic secret search
│       ├── injector.py         # Placeholder substitution
│       ├── executor.py         # CLI command execution
│       ├── redactor.py         # Output redaction
│       └── config.py           # Configuration management
├── homebrew/
│   └── claude-secrets.rb          # Homebrew formula
└── tests/
    ├── test_vault.py
    ├── test_detector.py
    ├── test_search.py
    └── test_injector.py
```

## Dependencies

```toml
[project]
dependencies = [
    "click>=8.0",           # CLI framework
    "mcp>=1.0",             # MCP SDK
    "cryptography>=41.0",   # Encryption (Fernet)
    "openai>=1.0",          # OpenAI-compatible API client
    "keyring>=24.0",        # Keychain (macOS) / libsecret (Linux)
    "rich>=13.0",           # Beautiful terminal output
]
```

## Homebrew Formula

```ruby
class McpSecrets < Formula
  desc "Intelligent secrets proxy for MCP clients"
  homepage "https://github.com/lightsprint/claude-secrets"
  url "https://github.com/lightsprint/claude-secrets/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "..."
  license "MIT"

  depends_on "python@3.11"

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      To get started:
        claude-secrets init
        claude-secrets config  # Shows how to add to your MCP client

      Then start the server:
        claude-secrets serve

      Or run as a background service:
        brew services start claude-secrets
    EOS
  end

  service do
    run [opt_bin/"claude-secrets", "serve"]
    keep_alive true
    log_path var/"log/claude-secrets.log"
  end
end
```

## MCP Client Configuration

After running `claude-secrets config`, add to your MCP client's configuration:

**Example (JSON):**
```json
{
  "mcpServers": {
    "secrets": {
      "command": "claude-secrets",
      "args": ["serve"]
    }
  }
}
```

## Files to Create

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, dependencies, CLI entry points |
| `src/claude_secrets/cli.py` | Click-based CLI commands |
| `src/claude_secrets/server.py` | MCP server with tool definitions |
| `src/claude_secrets/vault.py` | Encrypted secret storage with Fernet |
| `src/claude_secrets/permissions.py` | Session permission tracking |
| `src/claude_secrets/llm.py` | OpenAI-compatible LLM client |
| `src/claude_secrets/detector.py` | LLM secret detection in output |
| `src/claude_secrets/search.py` | Semantic search implementation |
| `src/claude_secrets/injector.py` | {{PLACEHOLDER}} substitution |
| `src/claude_secrets/executor.py` | Subprocess execution |
| `src/claude_secrets/redactor.py` | Output sanitization |
| `homebrew/claude-secrets.rb` | Homebrew formula |

## Implementation Phases

### Phase 1: Core CLI & Storage
1. Project setup with pyproject.toml
2. Vault implementation (encrypted storage + keychain)
3. Basic CLI: init, add, list, remove

### Phase 2: MCP Server
4. MCP server skeleton
5. Injector (placeholder substitution)
6. Executor (subprocess management)
7. Redactor (output sanitization)
8. Permission system (interactive prompts)

### Phase 3: Ollama Intelligence
9. Ollama client
10. Secret detector (scan output)
11. Semantic search

### Phase 4: Distribution
12. Homebrew formula
13. GitHub releases
14. Documentation

## Verification

1. **Install locally**:
   ```bash
   pip install -e .
   claude-secrets init
   ```

2. **Add test secret**:
   ```bash
   claude-secrets add TEST_KEY
   # Value: secret123
   # Description: Test key for verification
   ```

3. **Test CLI**:
   ```bash
   claude-secrets list
   claude-secrets search "test key"
   ```

4. **Test MCP server**:
   ```bash
   claude-secrets serve &
   # In another terminal, test with MCP client
   ```

5. **Integration test with MCP client**:
   ```bash
   claude-secrets config
   # Add config to your MCP client
   # Ask it to run: echo {{TEST_KEY}}
   # Verify permission prompt appears
   # Verify output shows [REDACTED]
   ```

## Security Model

- **Encryption**: AES-128 via Fernet
- **Key Storage**: macOS Keychain / Linux libsecret (never on disk)
- **Permissions**: Time-based expiry (configurable, default 1 hour)
- **LLM Privacy**: Use Ollama or local LLM for maximum privacy; cloud LLMs will receive command outputs for analysis
- **Audit Trail**: All access logged (without secret values)
- **No Persistence**: Session permissions cleared on server restart
