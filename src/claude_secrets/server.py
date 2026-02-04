"""MCP server implementation."""

import asyncio
import atexit
import json
import os
import signal
import sys
from datetime import datetime
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from rich.console import Console
from rich.prompt import Confirm

from .config import CONFIG_DIR, LOG_FILE, ensure_config_dir
from .events import emit_event
from .executor import execute_command
from .injector import extract_placeholders, inject_secrets, mask_command
from .permissions import PermissionManager, request_permission
from .redactor import apply_redaction_with_capture
from .vault import Vault


# === CONSTANTS === #


console = Console(stderr=True)
PID_FILE = CONFIG_DIR / "server.pid"


# === TOOL SCHEMAS === #


RUN_COMMAND_SCHEMA = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "Command with {{SECRET_NAME}} placeholders for secret injection"
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds (default: 60)",
            "default": 60
        },
        "capture": {
            "type": "array",
            "description": "Capture secrets from command output and store in vault for future use",
            "items": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "JSON path to extract (e.g., '$.Credentials.SecretAccessKey')"
                    },
                    "name": {
                        "type": "string",
                        "description": "Name for the captured secret (used as {{NAME}} in future commands)"
                    },
                    "description": {
                        "type": "string",
                        "description": "LLM-friendly description explaining: what this secret is, what commands/APIs it works with, any related secrets it must be used with, and how it was generated"
                    },
                    "expires_at": {
                        "type": "string",
                        "description": "ISO 8601 timestamp when this secret expires (e.g., '2024-01-24T12:00:00Z')"
                    }
                },
                "required": ["path", "name", "description"]
            }
        },
        "redact_patterns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Additional regex patterns to redact from output"
        },
        "skip_builtin_patterns": {
            "type": "boolean",
            "description": "Skip built-in secret patterns (AWS keys, GitHub tokens, etc.). Default: false"
        }
    },
    "required": ["command"]
}

LIST_SECRETS_SCHEMA = {
    "type": "object",
    "properties": {
        "tag": {"type": "string", "description": "Filter by tag (optional)"}
    }
}

GET_PERMISSIONS_SCHEMA = {
    "type": "object",
    "properties": {}
}

REQUEST_SECRET_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Name for the secret (e.g., GITHUB_TOKEN, AWS_ACCESS_KEY)"
        },
        "description": {
            "type": "string",
            "description": "LLM-friendly description explaining what this secret is for, what commands/APIs use it, and any related secrets"
        }
    },
    "required": ["name", "description"]
}

RUN_COMMAND_DESCRIPTION = """Use INSTEAD OF Bash for ANY command that generates, outputs, or requires secrets.

WHEN TO USE (check before every Bash command):
- Command GENERATES secrets: API keys, tokens, passwords, credentials, certificates
- Command OUTPUTS secrets: Keys in response, tokens in JSON, credentials in any format
- Command REQUIRES secrets: Use {{SECRET_NAME}} placeholders instead of raw values
- Command accesses sensitive services: Cloud, databases, auth systems, payment APIs

FEATURES:
- Redacts secrets from output (prevents exposure in chat history)
- Captures secrets via 'capture' param and stores in encrypted vault
- Injects secrets via {{SECRET_NAME}} placeholders

CAPTURE EXAMPLE (use when command outputs credentials):
{
  "command": "aws iam create-access-key --user-name dev --profile admin",
  "capture": [
    {"path": "$.AccessKey.AccessKeyId", "name": "DEV_KEY_ID", "description": "AWS access key ID for dev user"},
    {"path": "$.AccessKey.SecretAccessKey", "name": "DEV_SECRET", "description": "AWS secret key for dev user"}
  ]
}

INJECTION EXAMPLE (use when command needs credentials):
{"command": "curl -H 'Authorization: Bearer {{API_TOKEN}}' https://api.example.com"}

SHELL PORTABILITY WARNING:
- Do NOT use `echo -e` - it's not portable (writes "-e" literally on macOS/zsh)
- Use `printf` for formatted output: printf 'line1\\nline2\\n'
- Or use heredocs: cat << 'EOF'
multiline
content
EOF"""

LIST_SECRETS_DESCRIPTION = """List available secrets with their names, descriptions, and tags.

Use this to discover what secrets are available before running commands.
The description field contains LLM-friendly hints about:
- What the secret is for
- What commands/APIs it works with
- Related secrets that should be used together
- Expiration or validity info"""

GET_PERMISSIONS_DESCRIPTION = "Get current session permission status for secrets"

REQUEST_SECRET_DESCRIPTION = "Request user to add a missing secret. ENFORCED: You MUST call list_secrets FIRST - this call will FAIL if you haven't. Only use this for secrets NOT in the list."


# === PUBLIC API === #


def run_server(timeout_seconds: int = 3600) -> None:
    """Entry point to run the MCP server."""
    _write_pid_file()
    atexit.register(_remove_pid_file)

    signal.signal(signal.SIGTERM, lambda *_: _cleanup_and_exit(0))
    signal.signal(signal.SIGINT, lambda *_: _cleanup_and_exit(0))

    try:
        server = MCPSecretsServer(timeout_seconds=timeout_seconds)
        asyncio.run(server.run())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        _cleanup_and_exit(0)


class MCPSecretsServer:
    """MCP server for secrets management."""

    def __init__(self, timeout_seconds: int = 3600):
        self.vault = Vault()
        self.vault.load()
        self.permissions = PermissionManager(timeout_seconds)
        self.server = Server("claude-secrets")
        self._list_secrets_called = False
        self._last_listed_secrets: set[str] = set()
        self._setup_handlers()

    async def run(self) -> None:
        """Run the MCP server on stdio."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )

    def _setup_handlers(self) -> None:
        """Set up MCP tool handlers."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(name="run_command", description=RUN_COMMAND_DESCRIPTION, inputSchema=RUN_COMMAND_SCHEMA),
                Tool(name="list_secrets", description=LIST_SECRETS_DESCRIPTION, inputSchema=LIST_SECRETS_SCHEMA),
                Tool(name="get_permissions", description=GET_PERMISSIONS_DESCRIPTION, inputSchema=GET_PERMISSIONS_SCHEMA),
                Tool(name="request_secret", description=REQUEST_SECRET_DESCRIPTION, inputSchema=REQUEST_SECRET_SCHEMA),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            return await self._handle_tool_call(name, arguments)

    async def _handle_tool_call(self, name: str, arguments: dict) -> list[TextContent]:
        """Route tool calls to appropriate handlers."""
        try:
            if name == "run_command":
                result = await self._run_command(
                    arguments.get("command", ""),
                    arguments.get("timeout", 60),
                    arguments.get("capture", []),
                    arguments.get("redact_patterns", []),
                    arguments.get("skip_builtin_patterns", False),
                )
            elif name == "list_secrets":
                result = self._list_secrets(arguments.get("tag"))
            elif name == "get_permissions":
                result = self._get_permissions()
            elif name == "request_secret":
                result = self._request_secret(
                    arguments.get("name", ""),
                    arguments.get("description", ""),
                )
            else:
                result = {"error": f"Unknown tool: {name}"}

            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    async def _run_command(
        self,
        command: str,
        timeout: int,
        capture_specs: list[dict],
        redact_patterns: list[str],
        skip_builtin: bool,
    ) -> dict:
        """Run a command with secret injection, capture, and redaction."""
        placeholders = extract_placeholders(command)

        # Handle secret injection if placeholders present
        if placeholders:
            error = await self._request_permissions_for_secrets(placeholders, command)
            if error:
                return error

            injected_command, missing = inject_secrets(command, self.vault, set(placeholders))
            if missing:
                return {
                    "error": "secrets_missing",
                    "secrets": missing,
                    "message": f"Secrets not found: {', '.join(missing)}. Use request_secret tool to ask user to add them."
                }
        else:
            injected_command = command

        # Execute command
        result = execute_command(injected_command, timeout=timeout)

        # Redact output
        secret_values = self._get_secret_values(placeholders)
        capture_config = self._build_capture_config(capture_specs)

        stdout, captured = apply_redaction_with_capture(
            result.stdout,
            secret_values=secret_values,
            capture_config=capture_config,
            patterns=redact_patterns or None,
            use_builtin_patterns=not skip_builtin,
        )

        stderr, _ = apply_redaction_with_capture(
            result.stderr,
            secret_values=secret_values,
            patterns=redact_patterns or None,
            use_builtin_patterns=not skip_builtin,
        )

        # Store any captured secrets
        captured_names = self._store_captured_secrets(captured, capture_specs, command)

        # Build response
        return self._build_command_response(stdout, stderr, result.exit_code, result.timed_out, captured_names)

    def _get_secret_values(self, placeholders: list[str]) -> list[str]:
        """Get secret values for the given placeholder names."""
        return [v for name in placeholders if (v := self.vault.get_value(name))]

    def _build_command_response(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        timed_out: bool,
        captured_names: list[str],
    ) -> dict:
        """Build the response dict for run_command."""
        response = {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
        }
        if captured_names:
            response["captured_secrets"] = captured_names
        if timed_out:
            response["timed_out"] = True
        return response

    async def _request_permissions_for_secrets(self, placeholders: list[str], command: str) -> Optional[dict]:
        """Request permission for each secret. Returns error dict if denied, None if all approved."""
        is_interactive = sys.stdin.isatty()
        masked_command = mask_command(command)

        for secret_name in placeholders:
            secret = self.vault.get(secret_name)
            if not secret:
                return {
                    "error": "secret_not_found",
                    "secret": secret_name,
                    "message": f"Secret '{secret_name}' not found in vault"
                }

            if is_interactive:
                granted = self._request_interactive_permission(secret_name, secret.description, masked_command)
            else:
                granted = request_permission(secret_name, secret.description, masked_command)
                status = "granted (menubar)" if granted else "denied (menubar)"
                _log_audit("ACCESS", secret_name, status, masked_command)

            if not granted:
                return {
                    "error": "permission_denied",
                    "secret": secret_name,
                    "message": f"User denied access to secret '{secret_name}'" + (" (or timeout)" if not is_interactive else "")
                }

        return None

    def _request_interactive_permission(self, secret_name: str, description: str, masked_command: str) -> bool:
        """Request permission interactively via console."""
        console.print(f"\n[bold yellow]Permission Request[/bold yellow]")
        console.print(f"Secret: [cyan]{secret_name}[/cyan]")
        console.print(f"Description: {description}")
        console.print(f"Command: {masked_command}")

        if Confirm.ask("Allow this use?", default=False):
            _log_audit("ACCESS", secret_name, "granted", masked_command)
            console.print("[green]Granted[/green]")
            return True
        else:
            _log_audit("ACCESS", secret_name, "denied", masked_command)
            console.print("[red]Denied[/red]")
            return False

    def _build_capture_config(self, capture_specs: list[dict]) -> dict:
        """Build capture config from specs."""
        config = {}
        for spec in capture_specs:
            path = spec.get("path", "")
            name = spec.get("name", "")
            if path and name:
                config[path] = {
                    "name": name,
                    "description": spec.get("description", ""),
                    "tags": spec.get("tags", []),
                }
        return config

    def _store_captured_secrets(self, captured: dict, capture_specs: list[dict], command: str) -> list[str]:
        """Store captured secrets in vault and return list of names."""
        if not captured:
            return []

        captured_names = []
        masked_command = mask_command(command)

        for name, value in captured.items():
            spec = next(
                (s for s in capture_specs if s.get("name") == name or name.startswith(s.get("name", ""))),
                None
            )

            description = spec.get("description", f"Captured from command: {masked_command}") if spec else f"Captured from command: {masked_command}"
            expires_at = spec.get("expires_at") if spec else None

            self.vault.add(name, value, description, expires_at=expires_at)
            captured_names.append(name)
            _log_audit("CAPTURE", name, "stored", masked_command)

        self.vault.save()
        emit_event("secret_captured", {"secrets": captured_names, "command": masked_command})

        return captured_names

    def _list_secrets(self, tag: Optional[str] = None) -> dict:
        """List available secrets."""
        secrets = self.vault.list_by_tag(tag) if tag else self.vault.list_all()

        result = []
        secret_names = set()
        for s in secrets:
            entry = {"name": s.name, "description": s.description}
            if s.expires_at:
                entry["expires_at"] = s.expires_at
            result.append(entry)
            secret_names.add(s.name)

        self._list_secrets_called = True
        self._last_listed_secrets = secret_names

        return {"secrets": result}

    def _get_permissions(self) -> dict:
        """Get current permission status."""
        return {"permissions": self.permissions.get_status()}

    def _request_secret(self, name: str, description: str) -> dict:
        """Request the user to add a missing secret."""
        if not name:
            return {"error": "Secret name is required"}

        if not self._list_secrets_called:
            _log_audit("REQUEST_SECRET", name, "rejected", "list_secrets not called first")
            return {
                "error": "list_secrets_not_called",
                "message": "You MUST call list_secrets first before requesting a new secret. This ensures you check if the secret already exists."
            }

        if self.vault.get(name):
            _log_audit("REQUEST_SECRET", name, "rejected", "secret already exists in vault")
            return {
                "error": "secret_already_exists",
                "message": f"Secret '{name}' already exists in vault. You should have seen this in the list_secrets response."
            }

        if name in self._last_listed_secrets:
            _log_audit("REQUEST_SECRET", name, "rejected", "secret was in list_secrets response")
            return {
                "error": "secret_was_listed",
                "message": f"Secret '{name}' was returned by list_secrets. Do not request secrets that already exist."
            }

        emit_event("secret_needed", {"secrets": [{"name": name, "description": description}]})

        return {"status": "requested", "message": f"User has been prompted to add secret '{name}'"}


# === PRIVATE MODULE HELPERS === #


def _write_pid_file() -> None:
    """Write PID file for status detection."""
    ensure_config_dir()
    PID_FILE.write_text(str(os.getpid()))


def _remove_pid_file() -> None:
    """Remove PID file on exit."""
    PID_FILE.unlink(missing_ok=True)


def _cleanup_and_exit(code: int = 0) -> None:
    """Clean up and exit without triggering Python's finalization race."""
    _remove_pid_file()
    try:
        sys.stdin.close()
    except Exception:
        pass
    os._exit(code)


def _log_audit(event_type: str, secret_name: str, status: str, context: str = "") -> None:
    """Log an audit event."""
    ensure_config_dir()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} - {event_type} - {secret_name} - {status}"
    if context:
        line += f" - {context}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
