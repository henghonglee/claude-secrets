# Claude Secrets

A secure secrets management plugin for Claude Code and MCP clients. Enables AI assistants to safely handle credentials with user approval, automatic redaction, and secret capture from command output.

## Features

- **Secret Injection** - Use `{{SECRET_NAME}}` placeholders in commands to inject secrets
- **Session-Based Permissions** - User approves secret access per-session with time-based expiry
- **Output Redaction** - Automatically redacts known secrets and common patterns from output
- **Secret Capture** - Extract secrets from command output (e.g., AWS session tokens) and store for future use
- **LLM-Friendly Metadata** - Descriptions help future LLMs discover and use the right secrets
- **macOS Menu Bar App** - Native notifications and a secret-request prompt for secret requests
- **Local Web UI** - Browser-based UI (bundled with the menu bar app) to add, view, and delete secrets
- **Encrypted Vault** - Secrets stored with Fernet encryption

## Installation

### One-Line Install (Recommended)

```bash
curl -sSL https://raw.githubusercontent.com/henghonglee/claude-secrets/main/install.sh | bash
```

The install script installs the package (via `pipx`, falling back to `pip install --user`) and then runs `ccs init`, which:
- Creates the encrypted vault
- Installs the Claude Code plugin (via marketplace)
- Starts the menu bar app (macOS)
- Enables auto-start on login (macOS, via launchd)

### Manual Installation

```bash
pipx install git+https://github.com/henghonglee/claude-secrets.git
ccs init
```

### From Source

```bash
git clone https://github.com/henghonglee/claude-secrets.git
cd claude-secrets
pip install -e .
ccs init
```

## Quick Start

```bash
# Initialize vault + install plugin + start menubar + enable auto-start on login
ccs init

# Add a secret (prompts for value, description, and tags)
ccs add AWS_ACCESS_KEY

# List stored secrets
ccs list

# Check status
ccs status
```

A description helps future LLMs understand what each secret is for, and tags let you group and filter related secrets.

### Plugin-Only Install (if claude-secrets is already installed)

```bash
claude plugin marketplace add henghonglee/claude-secrets
claude plugin install claude-secrets@henghonglee-claude-secrets
```

## CLI Reference

The `ccs` command is the primary interface. Run `ccs --help` for the full list, or `ccs --version` to print the version.

| Command | Description |
|---------|-------------|
| `ccs init [--no-menubar] [--no-plugin]` | Create the vault, install the Claude Code plugin, and (macOS) start the menu bar app + enable auto-start on login |
| `ccs status` | Show status of components (vault secret count, menubar running, auto-start) |
| `ccs add NAME` | Add a secret. Prompts for value (masked), description, and tags |
| `ccs list [--tag TAG]` | List all secrets, optionally filtered by tag (`-t`) |
| `ccs remove NAME` | Remove a single secret (prompts for confirmation) |
| `ccs export FILE` | Export the vault to an encrypted file |
| `ccs import FILE` | Import secrets from a previously exported encrypted file |
| `ccs serve [--session-timeout 1h] [--port N]` | Start the MCP server over stdio (see below) |
| `ccs logs [--tail N]` | Show the last N lines (default 20) of the audit log |
| `ccs menubar [--stop]` | Launch (or stop) the macOS menu bar app |
| `ccs stop` | Stop all running claude-secrets processes (menubar and server) |
| `ccs setup` | macOS only: init the vault, install launchd auto-start, and start the menubar (does not install the plugin) |
| `ccs uninstall [--delete-vault]` | Uninstall claude-secrets; keeps your secrets unless `--delete-vault` is passed |
| `ccs config set KEY VALUE` | Set a configuration value (supports dot-notation keys) |
| `ccs config get KEY` | Get a configuration value |
| `ccs config show` | Print the full configuration |
| `ccs config show-mcp` | Print a ready-to-paste MCP server configuration snippet |

> **Note:** `ccs serve --port` (HTTP mode) is not yet implemented — it prints a message and exits. The server currently runs over stdio only. `--session-timeout`/`-t` accepts values like `30m`, `1h`, or `8h` and controls how long a granted permission lasts for that server session.

## Claude Code Commands

When installed as a plugin:

| Command | Description |
|---------|-------------|
| `/claude-secrets:list` | List all available secrets |
| `/claude-secrets:add [NAME]` | Add a new secret |
| `/claude-secrets:run <command>` | Run a command with secret injection |

## MCP Configuration (Non-Plugin)

For Claude Desktop or other MCP clients, add the server to your configuration. You can generate this snippet at any time with `ccs config show-mcp`:

```json
{
  "mcpServers": {
    "secrets": {
      "command": "ccs",
      "args": ["serve"]
    }
  }
}
```

> The plugin's own `.mcp.json` wraps the call in a login shell — `bash -l -c "ccs serve"` — so that `ccs` is found on `PATH`. If `ccs` is not on your client's `PATH`, use the same wrapper or an absolute path to the `ccs` binary.

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
- `command` *(required)* - Command with `{{SECRET_NAME}}` placeholders
- `timeout` - Timeout in seconds (default: 60)
- `capture` - Extract secrets from JSON output. Each entry requires `path`, `name`, and `description`:
  - `path` *(required)* - JSONPath expression (e.g., `$.Credentials.SecretAccessKey`)
  - `name` *(required)* - Name for the captured secret
  - `description` *(required)* - LLM-friendly description
  - `expires_at` *(optional)* - ISO 8601 expiration timestamp
- `redact_patterns` - Additional regex patterns to redact
- `skip_builtin_patterns` - Skip built-in redaction patterns (default: false)

### `list_secrets`

List available secrets with their descriptions.

```json
{
  "tag": "aws"
}
```

Returns (the `expires_at` field is only present when a secret has an expiry):

```json
{
  "secrets": [
    {
      "name": "AWS_ACCESS_KEY",
      "description": "AWS access key for production account"
    }
  ]
}
```

### `request_secret`

Request the user to add a missing secret via the menu bar app. Both `name` and `description` are required.

```json
{
  "name": "GITHUB_TOKEN",
  "description": "Personal access token for GitHub API. Needs repo and workflow scopes."
}
```

`request_secret` is guarded: you must call `list_secrets` first, and it will reject names that already exist in the vault or that appeared in the last `list_secrets` response. On success it emits a `secret_needed` event and returns immediately with `{"status": "requested"}`; the menu bar app then opens a prompt for the user to enter the secret value.

### `get_permissions`

Get current session permission status for secrets. Takes no parameters.

## How It Works

1. **Client LLM calls `list_secrets`** to discover available secrets
2. **LLM constructs command** with `{{SECRET_NAME}}` placeholders
3. **User approves** secret access when prompted (cached for session)
4. **Server injects secrets** and executes command
5. **Output is redacted** before returning to LLM
6. **Captured secrets** are stored with LLM-provided descriptions for future use

## Menu Bar App (macOS)

The menu bar app provides:
- Server status indicator
- List of stored secrets with expiry times
- A native secret-request prompt when an MCP client requests a missing secret
- Notifications when secrets are captured or expiring
- **Add Secret...** and **View Secrets...** menu items that open the bundled [Web UI](#web-ui) in your browser

Start it with either entry point:

```bash
ccs menubar              # or: claude-secrets-menubar
ccs menubar --stop       # stop the running app
```

## Web UI

The menu bar app bundles a small local Flask web UI for managing secrets in the browser. It starts automatically when the menu bar app launches and is reachable from the **Add Secret...** and **View Secrets...** menu items.

- Runs on `http://127.0.0.1:5789` by default, falling back to a random free port if 5789 is in use
- Bound to `127.0.0.1` only — it is never exposed beyond localhost
- Pages:
  - `/add` — form to add a secret (name, value, description, optional expiry). Supports `?name=` / `?description=` prefill, which the menu bar uses when prompting for a missing secret
  - `/list` — table of all secrets with a status badge (**Valid** / **Expiring** within 24h / **Expired**)
  - Per-row **Delete** action (with confirmation)

## Security Model

- **Encrypted storage** - Vault encrypted with Fernet (AES-128-CBC with HMAC-SHA256 authentication)
- **File permissions** - Vault, key, and config files are stored `0600` inside a `0700` directory (`~/.claude-secrets/`). The encryption key lives at `~/.claude-secrets/key`, so encryption protects the at-rest vault file, not against another user who can already read your home directory
- **Permission prompts** - User must approve each secret's use
- **Session expiry** - Permissions auto-expire (default: 1 hour). The MCP server's timeout is set via `ccs serve --session-timeout` (default `1h`)
- **Output redaction** - Secrets automatically removed from command output, plus built-in patterns for AWS keys, GitHub/Slack tokens, generic API keys, and bearer tokens
- **Audit logging** - All secret access logged to `~/.claude-secrets/audit.log` (view with `ccs logs`)

## Uninstalling

### One-Line Uninstall

```bash
curl -sSL https://raw.githubusercontent.com/henghonglee/claude-secrets/main/uninstall.sh | bash
```

### Manual Uninstall

```bash
ccs uninstall      # Stops menubar, removes plugin, keeps secrets
pipx uninstall claude-secrets
```

### Delete Everything (including secrets)

```bash
ccs uninstall --delete-vault   # prompts for confirmation before deleting the vault
pipx uninstall claude-secrets
```

Your secrets are preserved by default in `~/.claude-secrets/` so you can reinstall later without losing them.

## Plugin Structure

```
claude-secrets/
├── .claude-plugin/
│   ├── plugin.json          # Plugin manifest
│   └── marketplace.json     # Marketplace manifest (for plugin distribution)
├── .mcp.json                 # MCP server configuration
├── skills/
│   └── secrets/
│       └── SKILL.md         # Teaches Claude when/how to use secrets
├── commands/
│   ├── list.md              # /claude-secrets:list command
│   ├── add.md               # /claude-secrets:add command
│   └── run.md               # /claude-secrets:run command
└── src/
    └── claude_secrets/      # Python package
```

## Configuration

Configuration is stored at `~/.claude-secrets/config.json`:

```json
{
  "session_timeout": 3600
}
```

Manage it with the `ccs config` commands:

```bash
ccs config set session_timeout 7200   # keys support dot-notation; values are parsed as JSON/number/string
ccs config get session_timeout
ccs config show
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=claude_secrets

# Test plugin locally
claude --plugin-dir ./
```

## License

MIT
