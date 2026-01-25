"""MCP server implementation."""

import sys
import os
import signal
import atexit
import json
import logging
from datetime import datetime
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from rich.console import Console
from rich.prompt import Confirm

from .vault import Vault
from .permissions import PermissionManager
from .injector import extract_placeholders, inject_secrets, mask_command
from .executor import execute_command
from .redactor import apply_redaction_with_capture
from .config import LOG_FILE, CONFIG_DIR, ensure_config_dir, emit_event, request_permission

PID_FILE = CONFIG_DIR / "server.pid"


def write_pid_file():
    """Write PID file for status detection."""
    ensure_config_dir()
    PID_FILE.write_text(str(os.getpid()))


def remove_pid_file():
    """Remove PID file on exit."""
    PID_FILE.unlink(missing_ok=True)

console = Console(stderr=True)
logger = logging.getLogger(__name__)


def log_audit(event_type: str, secret_name: str, status: str, context: str = "") -> None:
    """Log an audit event."""
    ensure_config_dir()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} - {event_type} - {secret_name} - {status}"
    if context:
        line += f" - {context}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


class MCPSecretsServer:
    """MCP server for secrets management."""

    def __init__(self, timeout_seconds: int = 3600):
        self.vault = Vault()
        self.vault.load()
        self.permissions = PermissionManager(timeout_seconds)
        self.server = Server("mcp-secrets")
        # Track list_secrets calls for enforcement
        self._list_secrets_called = False
        self._last_listed_secrets: set[str] = set()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Set up MCP tool handlers."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="run_command",
                    description="""Use INSTEAD OF Bash for ANY command that generates, outputs, or requires secrets.

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
{"command": "curl -H 'Authorization: Bearer {{API_TOKEN}}' https://api.example.com"}""",
                    inputSchema={
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
                ),
                Tool(
                    name="list_secrets",
                    description="""List available secrets with their names, descriptions, and tags.

Use this to discover what secrets are available before running commands.
The description field contains LLM-friendly hints about:
- What the secret is for
- What commands/APIs it works with
- Related secrets that should be used together
- Expiration or validity info""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tag": {
                                "type": "string",
                                "description": "Filter by tag (optional)"
                            }
                        }
                    }
                ),
                Tool(
                    name="get_permissions",
                    description="Get current session permission status for secrets",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="request_secret",
                    description="Request user to add a missing secret. ENFORCED: You MUST call list_secrets FIRST - this call will FAIL if you haven't. Only use this for secrets NOT in the list.",
                    inputSchema={
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
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
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
        # Extract placeholders
        placeholders = extract_placeholders(command)

        if placeholders:
            # Always request permission for every secret use (no caching)
            is_interactive = sys.stdin.isatty()

            for secret_name in placeholders:
                secret = self.vault.get(secret_name)
                if not secret:
                    return {
                        "error": "secret_not_found",
                        "secret": secret_name,
                        "message": f"Secret '{secret_name}' not found in vault"
                    }

                if is_interactive:
                    # Prompt user for permission interactively
                    console.print(f"\n[bold yellow]Permission Request[/bold yellow]")
                    console.print(f"Secret: [cyan]{secret_name}[/cyan]")
                    console.print(f"Description: {secret.description}")
                    console.print(f"Command: {mask_command(command)}")

                    if Confirm.ask("Allow this use?", default=False):
                        log_audit("ACCESS", secret_name, "granted", mask_command(command))
                        console.print(f"[green]Granted[/green]")
                    else:
                        log_audit("ACCESS", secret_name, "denied", mask_command(command))
                        console.print(f"[red]Denied[/red]")
                        return {
                            "error": "permission_denied",
                            "secret": secret_name,
                            "message": f"User denied access to secret '{secret_name}'"
                        }
                else:
                    # Non-interactive (MCP mode): request permission via menubar
                    if request_permission(secret_name, secret.description, mask_command(command)):
                        log_audit("ACCESS", secret_name, "granted (menubar)", mask_command(command))
                    else:
                        log_audit("ACCESS", secret_name, "denied (menubar)", mask_command(command))
                        return {
                            "error": "permission_denied",
                            "secret": secret_name,
                            "message": f"User denied access to secret '{secret_name}' (or timeout)"
                        }

            # All secrets approved for this request
            allowed = set(placeholders)

            # Inject secrets
            injected_command, missing = inject_secrets(command, self.vault, allowed)

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

        # Get all secret values for redaction (injected secrets)
        secret_values = [
            self.vault.get_value(name)
            for name in placeholders
            if self.vault.get_value(name)
        ]

        # Build capture config from specs
        capture_config = {}
        for spec in capture_specs:
            path = spec.get("path", "")
            name = spec.get("name", "")
            if path and name:
                capture_config[path] = {
                    "name": name,
                    "description": spec.get("description", ""),
                    "tags": spec.get("tags", []),
                }

        # Apply redaction and capture to stdout
        stdout, captured = apply_redaction_with_capture(
            result.stdout,
            secret_values=secret_values,
            capture_config=capture_config,
            patterns=redact_patterns if redact_patterns else None,
            use_builtin_patterns=not skip_builtin,
        )

        # Apply redaction to stderr (no capture)
        stderr, _ = apply_redaction_with_capture(
            result.stderr,
            secret_values=secret_values,
            patterns=redact_patterns if redact_patterns else None,
            use_builtin_patterns=not skip_builtin,
        )

        # Store captured secrets in vault
        captured_names = []
        for name, value in captured.items():
            # Find the spec for this capture
            spec = None
            for s in capture_specs:
                if s.get("name") == name or name.startswith(s.get("name", "")):
                    spec = s
                    break

            if spec:
                description = spec.get("description", f"Captured from command: {mask_command(command)}")
                expires_at = spec.get("expires_at")
            else:
                description = f"Captured from command: {mask_command(command)}"
                expires_at = None

            self.vault.add(name, value, description, expires_at=expires_at)
            captured_names.append(name)
            log_audit("CAPTURE", name, "stored", mask_command(command))

        # Save vault if we captured anything
        if captured_names:
            self.vault.save()
            # Emit event for menubar notification
            emit_event("secret_captured", {
                "secrets": captured_names,
                "command": mask_command(command),
            })

        response = {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result.exit_code,
        }

        if captured_names:
            response["captured_secrets"] = captured_names

        if result.timed_out:
            response["timed_out"] = True

        return response

    def _list_secrets(self, tag: Optional[str] = None) -> dict:
        """List available secrets."""
        if tag:
            secrets = self.vault.list_by_tag(tag)
        else:
            secrets = self.vault.list_all()

        result = []
        secret_names = set()
        for s in secrets:
            entry = {
                "name": s.name,
                "description": s.description,
            }
            if s.expires_at:
                entry["expires_at"] = s.expires_at
            result.append(entry)
            secret_names.add(s.name)

        # Track that list_secrets was called and what secrets were visible
        self._list_secrets_called = True
        self._last_listed_secrets = secret_names

        return {"secrets": result}

    def _get_permissions(self) -> dict:
        """Get current permission status."""
        return {
            "permissions": self.permissions.get_status()
        }

    def _request_secret(self, name: str, description: str) -> dict:
        """Request the user to add a missing secret."""
        if not name:
            return {"error": "Secret name is required"}

        # STRICT ENFORCEMENT: list_secrets MUST be called first
        if not self._list_secrets_called:
            log_audit("REQUEST_SECRET", name, "rejected", "list_secrets not called first")
            return {
                "error": "list_secrets_not_called",
                "message": "You MUST call list_secrets first before requesting a new secret. "
                           "This ensures you check if the secret already exists."
            }

        # Check if it already exists in vault
        if self.vault.get(name):
            log_audit("REQUEST_SECRET", name, "rejected", "secret already exists in vault")
            return {
                "error": "secret_already_exists",
                "message": f"Secret '{name}' already exists in vault. "
                           "You should have seen this in the list_secrets response."
            }

        # Check if it was visible in the last list_secrets call
        if name in self._last_listed_secrets:
            log_audit("REQUEST_SECRET", name, "rejected", "secret was in list_secrets response")
            return {
                "error": "secret_was_listed",
                "message": f"Secret '{name}' was returned by list_secrets. "
                           "Do not request secrets that already exist."
            }

        # Emit event for menubar to show dialog
        emit_event("secret_needed", {
            "secrets": [{"name": name, "description": description}],
        })

        return {
            "status": "requested",
            "message": f"User has been prompted to add secret '{name}'"
        }

    async def run(self) -> None:
        """Run the MCP server on stdio."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def run_server(timeout_seconds: int = 3600) -> None:
    """Entry point to run the MCP server."""
    import asyncio

    # Write PID file for status detection
    write_pid_file()
    atexit.register(remove_pid_file)

    # Clean up PID file on signals
    def signal_handler(signum, frame):
        remove_pid_file()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        server = MCPSecretsServer(timeout_seconds=timeout_seconds)
        asyncio.run(server.run())
    finally:
        remove_pid_file()
