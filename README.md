# MCP Secrets

A secure secrets management plugin for Claude Code and MCP clients. Enables AI assistants to safely handle credentials with user approval, automatic redaction, and secret capture from command output.

## Features

- **Secret Injection** - Use `{{SECRET_NAME}}` placeholders in commands to inject secrets
- **Session-Based Permissions** - User approves secret access per-session with time-based expiry
- **Output Redaction** - Automatically redacts known secrets and common patterns from output
- **Secret Capture** - Extract secrets from command output (e.g., AWS session tokens) and store for future use
- **LLM-Friendly Metadata** - Descriptions help future LLMs discover and use the right secrets
- **macOS Menu Bar App** - Native notifications and dialogs for secret requests
- **Encrypted Vault** - Secrets stored with Fernet encryption

## Installation

### One-Line Install (Recommended)

```bash
curl -sSL https://raw.githubusercontent.com/henghonglee/mcp-secrets/main/install.sh | bash
```

This automatically:
- Installs the package via pipx
- Creates the encrypted vault
- Installs the Claude Code plugin
- Starts the menu bar app
- Enables auto-start on login

### Manual Installation

```bash
pipx install git+https://github.com/henghonglee/mcp-secrets.git
mcp-secrets init
```

### From Source

```bash
git clone https://github.com/henghonglee/mcp-secrets.git
cd mcp-secrets
pip install -e .
mcp-secrets init
```

## Quick Start

```bash
# Initialize vault + start menubar + enable auto-start on login
mcp-secrets init

# Add a secret with description (helps LLMs understand what it's for)
mcp-secrets add AWS_ACCESS_KEY

# Check status
mcp-secrets status
```

The `init` command automatically:
- Creates the encrypted vault
- Installs the Claude Code plugin (via marketplace)
- Starts the menu bar app
- Enables auto-start on login (macOS)

### Plugin-Only Install (if mcp-secrets is already installed)

```bash
claude plugin marketplace add henghonglee/mcp-secrets
claude plugin install mcp-secrets@henghonglee-mcp-secrets
```

## Claude Code Commands

When installed as a plugin:

| Command | Description |
|---------|-------------|
| `/mcp-secrets:list` | List all available secrets |
| `/mcp-secrets:add [NAME]` | Add a new secret |
| `/mcp-secrets:run <command>` | Run a command with secret injection |

## MCP Configuration (Non-Plugin)

For Claude Desktop or other MCP clients, add to your configuration:

```json
{
  "mcpServers": {
    "secrets": {
      "command": "mcp-secrets",
      "args": ["serve"]
    }
  }
}
```

## MCP Tools

### `run_command`

Execute a CLI command with secret injection and output redaction.

```json
{
  "command": "aws s3 ls --profile {{AWS_PROFILE}}",
  "timeout": 60,
  "capture": [
    {
      "path": "$.Credentials.SecretAccessKey",
      "name": "AWS_SESSION_SECRET",
      "description": "Temporary AWS secret key from STS. Use with AWS_SESSION_KEY_ID and AWS_SESSION_TOKEN.",
      "expires_at": "2024-01-24T12:00:00Z"
    }
  ]
}
```

**Parameters:**
- `command` - Command with `{{SECRET_NAME}}` placeholders
- `timeout` - Timeout in seconds (default: 60)
- `capture` - Extract secrets from JSON output:
  - `path` - JSONPath expression (e.g., `$.Credentials.SecretAccessKey`)
  - `name` - Name for the captured secret
  - `description` - LLM-friendly description
  - `expires_at` - ISO 8601 expiration timestamp
- `redact_patterns` - Additional regex patterns to redact
- `skip_builtin_patterns` - Skip built-in redaction patterns

### `list_secrets`

List available secrets with their descriptions.

```json
{
  "tag": "aws"
}
```

Returns:
```json
{
  "secrets": [
    {
      "name": "AWS_ACCESS_KEY",
      "description": "AWS access key for production account",
      "expires_at": null
    }
  ]
}
```

### `request_secret`

Request the user to add a missing secret via the menu bar app.

```json
{
  "name": "GITHUB_TOKEN",
  "description": "Personal access token for GitHub API. Needs repo and workflow scopes."
}
```

The menu bar app will show a native macOS dialog prompting the user to enter the secret value.

### `get_permissions`

Get current session permission status for secrets.

## How It Works

1. **Client LLM calls `list_secrets`** to discover available secrets
2. **LLM constructs command** with `{{SECRET_NAME}}` placeholders
3. **User approves** secret access when prompted (cached for session)
4. **Server injects secrets** and executes command
5. **Output is redacted** before returning to LLM
6. **Captured secrets** are stored with LLM-provided descriptions for future use

## Menu Bar App (macOS)

The menu bar app provides:
- Server status indicator (🔐 running / 🔓 stopped)
- List of stored secrets with expiry times
- Native dialogs for secret requests
- Notifications when secrets are captured or expiring

Start with:
```bash
mcp-secrets-menubar
```

## Security Model

- **Encrypted storage** - Vault encrypted with Fernet (AES-128-CBC)
- **Permission prompts** - User must approve each secret's use
- **Session expiry** - Permissions auto-expire (default: 1 hour)
- **Output redaction** - Secrets automatically removed from command output
- **Audit logging** - All secret access logged to `~/.mcp-secrets/audit.log`

## Uninstalling

### One-Line Uninstall

```bash
curl -sSL https://raw.githubusercontent.com/henghonglee/mcp-secrets/main/uninstall.sh | bash
```

### Manual Uninstall

```bash
mcp-secrets uninstall      # Stops menubar, removes plugin, keeps secrets
pipx uninstall mcp-secrets
```

### Delete Everything (including secrets)

```bash
mcp-secrets uninstall --delete-vault
pipx uninstall mcp-secrets
```

Your secrets are preserved by default in `~/.mcp-secrets/` so you can reinstall later without losing them.

## Plugin Structure

```
mcp-secrets/
├── .claude-plugin/
│   ├── plugin.json          # Plugin manifest
│   └── marketplace.json     # Marketplace manifest (for plugin distribution)
├── .mcp.json                 # MCP server configuration
├── skills/
│   └── secrets/
│       └── SKILL.md         # Teaches Claude when/how to use secrets
├── commands/
│   ├── list.md              # /mcp-secrets:list command
│   ├── add.md               # /mcp-secrets:add command
│   └── run.md               # /mcp-secrets:run command
└── src/
    └── mcp_secrets/         # Python package
```

## Configuration

Configuration stored at `~/.mcp-secrets/config.json`:

```json
{
  "session_timeout": 3600
}
```

Set values with:
```bash
mcp-secrets config set session_timeout 7200
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=mcp_secrets

# Test plugin locally
claude --plugin-dir ./
```

## License

MIT
