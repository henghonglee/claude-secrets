"""Click CLI commands for mcp-secrets."""

import sys
import os
import json
import shutil
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm

from .config import load_config, set_config_value, get_config_value, CONFIG_DIR
from .vault import Vault

console = Console()

LAUNCHD_LABEL = "com.mcp-secrets.menubar"
LAUNCHD_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def get_mcp_secrets_path() -> str:
    """Get the path to the mcp-secrets executable."""
    return shutil.which("mcp-secrets") or "mcp-secrets"


def generate_launchd_plist() -> str:
    """Generate the launchd plist content."""
    mcp_path = get_mcp_secrets_path()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{mcp_path}</string>
        <string>menubar</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{CONFIG_DIR}/menubar.log</string>
    <key>StandardErrorPath</key>
    <string>{CONFIG_DIR}/menubar.log</string>
</dict>
</plist>
"""


def install_launchd_agent() -> bool:
    """Install the launchd agent for auto-start on login."""
    if sys.platform != "darwin":
        return False

    # Create LaunchAgents directory if needed
    LAUNCHD_PLIST.parent.mkdir(parents=True, exist_ok=True)

    # Write plist
    LAUNCHD_PLIST.write_text(generate_launchd_plist())

    # Load the agent
    subprocess.run(["launchctl", "unload", str(LAUNCHD_PLIST)], capture_output=True)
    result = subprocess.run(["launchctl", "load", str(LAUNCHD_PLIST)], capture_output=True)

    return result.returncode == 0


def uninstall_launchd_agent() -> bool:
    """Uninstall the launchd agent."""
    if sys.platform != "darwin":
        return False

    if not LAUNCHD_PLIST.exists():
        return False

    # Unload the agent
    subprocess.run(["launchctl", "unload", str(LAUNCHD_PLIST)], capture_output=True)

    # Remove plist
    LAUNCHD_PLIST.unlink(missing_ok=True)

    return True


def is_menubar_running() -> bool:
    """Check if menubar is running."""
    result = subprocess.run(["pgrep", "-f", "mcp-secrets.*menubar"], capture_output=True)
    return result.returncode == 0


def start_menubar_background() -> bool:
    """Start menubar in background."""
    if is_menubar_running():
        return True

    mcp_path = get_mcp_secrets_path()
    subprocess.Popen(
        [mcp_path, "menubar"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    return True


def stop_menubar() -> bool:
    """Stop the menubar process."""
    result = subprocess.run(["pkill", "-f", "mcp-secrets.*menubar"], capture_output=True)
    return result.returncode == 0


def is_claude_code_installed() -> bool:
    """Check if Claude Code CLI is installed."""
    return shutil.which("claude") is not None


def install_claude_plugin() -> tuple[bool, str]:
    """Install the mcp-secrets Claude Code plugin. Returns (success, message)."""
    if not is_claude_code_installed():
        return False, "Claude Code not installed"

    # First, add the marketplace (if not already added)
    marketplace_result = subprocess.run(
        ["claude", "plugin", "marketplace", "add", "henghonglee/mcp-secrets"],
        capture_output=True,
        text=True
    )

    # Check if marketplace was added or already exists
    marketplace_ok = (
        marketplace_result.returncode == 0 or
        "already" in marketplace_result.stderr.lower() or
        "already" in marketplace_result.stdout.lower()
    )

    if not marketplace_ok:
        return False, f"Failed to add marketplace: {marketplace_result.stderr.strip()}"

    # Now install the plugin from the marketplace
    result = subprocess.run(
        ["claude", "plugin", "install", "mcp-secrets@henghonglee-mcp-secrets"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        return True, "Plugin installed"
    elif "already installed" in result.stderr.lower() or "already installed" in result.stdout.lower():
        return True, "Plugin already installed"
    else:
        return False, result.stderr.strip() or "Unknown error"


def uninstall_claude_plugin() -> tuple[bool, str]:
    """Uninstall the mcp-secrets Claude Code plugin and marketplace. Returns (success, message)."""
    if not is_claude_code_installed():
        return False, "Claude Code not installed"

    # Uninstall the plugin
    result = subprocess.run(
        ["claude", "plugin", "uninstall", "mcp-secrets@henghonglee-mcp-secrets"],
        capture_output=True,
        text=True
    )

    plugin_removed = (
        result.returncode == 0 or
        "not installed" in result.stderr.lower() or
        "not found" in result.stderr.lower()
    )

    # Remove the marketplace
    marketplace_result = subprocess.run(
        ["claude", "plugin", "marketplace", "remove", "henghonglee-mcp-secrets"],
        capture_output=True,
        text=True
    )

    if plugin_removed:
        return True, "Plugin and marketplace removed"
    else:
        return False, result.stderr.strip() or "Unknown error"


@click.group()
@click.version_option()
def main():
    """MCP Secrets - Intelligent secrets proxy for MCP clients."""
    pass


@main.command()
@click.option("--no-menubar", is_flag=True, help="Skip menubar setup")
@click.option("--no-plugin", is_flag=True, help="Skip Claude Code plugin installation")
def init(no_menubar: bool, no_plugin: bool):
    """Initialize the secrets vault, start menubar, and install Claude Code plugin."""
    vault = Vault()

    # Initialize vault
    is_new = vault.init()
    if is_new:
        console.print(f"[green]✓[/green] Created vault at {CONFIG_DIR}")
    else:
        console.print(f"[green]✓[/green] Vault exists at {CONFIG_DIR}")

    # Install Claude Code plugin
    if not no_plugin:
        if is_claude_code_installed():
            success, msg = install_claude_plugin()
            if success:
                console.print(f"[green]✓[/green] Claude Code plugin installed")
            else:
                console.print(f"[yellow]![/yellow] Claude Code plugin: {msg}")
        else:
            console.print("[dim]·[/dim] Claude Code not found (plugin skipped)")

    # Setup menubar auto-start (macOS only)
    if sys.platform == "darwin" and not no_menubar:
        if install_launchd_agent():
            console.print("[green]✓[/green] Auto-start enabled (launches on login)")
        else:
            console.print("[yellow]![/yellow] Could not enable auto-start")

        if start_menubar_background():
            console.print("[green]✓[/green] Menu bar app started")
        else:
            console.print("[yellow]![/yellow] Could not start menu bar app")

    console.print("\n[bold green]Ready![/bold green]")
    console.print("\n[dim]Commands:[/dim]")
    console.print("  [cyan]mcp-secrets add NAME[/cyan]  - Add a secret")
    console.print("  [cyan]mcp-secrets status[/cyan]    - Check status")
    console.print("  [cyan]mcp-secrets uninstall[/cyan] - Uninstall (keeps secrets)")


@main.command()
@click.argument("name")
def add(name: str):
    """Add a new secret."""
    vault = Vault()
    vault.load()

    # Check if exists
    existing = vault.get(name)
    if existing:
        if not Confirm.ask(f"Secret '{name}' exists. Overwrite?"):
            return

    # Get secret value (hidden input)
    value = Prompt.ask("Value", password=True)
    if not value:
        console.print("[red]Error:[/red] Value cannot be empty")
        return

    description = Prompt.ask("Description")
    tags_str = Prompt.ask("Tags (comma-separated)", default="")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]

    vault.add(name, value, description, tags)
    console.print(f"[green]Added secret:[/green] {name}")


@main.command("list")
@click.option("--tag", "-t", help="Filter by tag")
def list_secrets(tag: str):
    """List all secrets."""
    vault = Vault()
    vault.load()

    if tag:
        secrets = vault.list_by_tag(tag)
    else:
        secrets = vault.list_all()

    if not secrets:
        console.print("[dim]No secrets found[/dim]")
        return

    table = Table(show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Tags", style="dim")

    for secret in secrets:
        table.add_row(
            secret.name,
            secret.description,
            ", ".join(secret.tags) if secret.tags else "",
        )

    console.print(table)


@main.command()
@click.argument("name")
def remove(name: str):
    """Remove a secret."""
    vault = Vault()
    vault.load()

    if not vault.get(name):
        console.print(f"[red]Error:[/red] Secret '{name}' not found")
        return

    if Confirm.ask(f"Remove secret '{name}'?"):
        vault.remove(name)
        console.print(f"[green]Removed:[/green] {name}")


@main.command()
@click.argument("file", type=click.Path())
def export(file: str):
    """Export secrets to encrypted file."""
    vault = Vault()
    vault.load()

    data = vault.export_encrypted()
    Path(file).write_bytes(data)
    console.print(f"[green]Exported to:[/green] {file}")


@main.command("import")
@click.argument("file", type=click.Path(exists=True))
def import_secrets(file: str):
    """Import secrets from encrypted file."""
    vault = Vault()
    vault.load()

    data = Path(file).read_bytes()
    count = vault.import_encrypted(data)
    console.print(f"[green]Imported {count} secrets[/green]")


@main.group()
def config():
    """Configuration management."""
    pass


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Set a configuration value."""
    set_config_value(key, value)
    console.print(f"[green]Set[/green] {key} = {value}")


@config.command("get")
@click.argument("key")
def config_get(key: str):
    """Get a configuration value."""
    value = get_config_value(key)
    if value is None:
        console.print(f"[dim]Not set:[/dim] {key}")
    else:
        console.print(f"{key} = {value}")


@config.command("show")
def config_show():
    """Show all configuration."""
    cfg = load_config()
    console.print_json(data=cfg)


@config.command("show-mcp")
def config_show_mcp():
    """Show MCP server configuration snippet."""
    mcp_config = {
        "mcpServers": {
            "secrets": {
                "command": "mcp-secrets",
                "args": ["serve"]
            }
        }
    }
    console.print("[bold]Add this to your MCP client configuration:[/bold]\n")
    console.print_json(data=mcp_config)


@main.command()
@click.option("--port", "-p", type=int, help="Run in HTTP mode on this port")
@click.option("--session-timeout", "-t", default="1h", help="Permission expiry time (e.g., 30m, 1h, 8h)")
def serve(port: int, session_timeout: str):
    """Start the MCP server."""
    # Parse timeout
    timeout_seconds = parse_timeout(session_timeout)

    # Print to stderr to avoid interfering with MCP protocol on stdout
    import sys
    print(f"Session timeout: {session_timeout}", file=sys.stderr)

    if port:
        print(f"HTTP mode not yet implemented (port {port})", file=sys.stderr)
        sys.exit(1)

    # Run MCP server on stdio
    from .server import run_server
    run_server(timeout_seconds=timeout_seconds)


def parse_timeout(s: str) -> int:
    """Parse timeout string like '30m', '1h', '8h' to seconds."""
    s = s.strip().lower()
    if s.endswith("h"):
        return int(s[:-1]) * 3600
    elif s.endswith("m"):
        return int(s[:-1]) * 60
    elif s.endswith("s"):
        return int(s[:-1])
    else:
        return int(s)


@main.command()
@click.option("--tail", "-n", default=20, help="Number of lines to show")
def logs(tail: int):
    """View recent audit logs."""
    from .config import LOG_FILE

    if not LOG_FILE.exists():
        console.print("[dim]No logs yet[/dim]")
        return

    lines = LOG_FILE.read_text().strip().split("\n")
    for line in lines[-tail:]:
        console.print(line)


@main.command()
@click.option("--stop", "stop_flag", is_flag=True, help="Stop the running menu bar app")
def menubar(stop_flag: bool):
    """Launch the macOS menu bar app."""
    if sys.platform != "darwin":
        console.print("[red]Error:[/red] Menu bar app is only available on macOS")
        sys.exit(1)

    if stop_flag:
        if stop_menubar():
            console.print("[green]Menu bar app stopped[/green]")
        else:
            console.print("[dim]Menu bar app not running[/dim]")
        return

    try:
        from .menubar import run_menubar
        run_menubar()
    except ImportError:
        console.print("[red]Error:[/red] rumps not installed")
        console.print("Install with: [cyan]pip install rumps[/cyan]")
        sys.exit(1)


@main.command()
def stop():
    """Stop all running mcp-secrets processes (menubar, server)."""
    stopped = []

    # Stop menubar
    if stop_menubar():
        stopped.append("menubar")

    # Stop server (if running standalone)
    result = subprocess.run(["pkill", "-f", "mcp-secrets.*serve"], capture_output=True)
    if result.returncode == 0:
        stopped.append("server")

    if stopped:
        console.print(f"[green]Stopped:[/green] {', '.join(stopped)}")
    else:
        console.print("[dim]No mcp-secrets processes running[/dim]")


@main.command()
def setup():
    """Set up menubar auto-start on login (macOS only)."""
    if sys.platform != "darwin":
        console.print("[red]Error:[/red] Setup is only available on macOS")
        sys.exit(1)

    console.print("[bold]Setting up mcp-secrets...[/bold]\n")

    # Ensure vault exists
    vault = Vault()
    vault.init()
    console.print(f"[green]✓[/green] Vault ready at {CONFIG_DIR}")

    # Install launchd agent
    if install_launchd_agent():
        console.print("[green]✓[/green] Auto-start installed (launches on login)")
    else:
        console.print("[red]✗[/red] Failed to install auto-start")

    # Start menubar now
    if start_menubar_background():
        console.print("[green]✓[/green] Menu bar app started")
    else:
        console.print("[yellow]![/yellow] Menu bar may already be running")

    console.print("\n[bold green]Setup complete![/bold green]")


@main.command()
@click.option("--keep-vault", is_flag=True, default=True, hidden=True)
@click.option("--delete-vault", is_flag=True, help="Also delete the vault and all secrets")
def uninstall(keep_vault: bool, delete_vault: bool):
    """Uninstall mcp-secrets (keeps your secrets by default)."""
    console.print("[bold]Uninstalling mcp-secrets...[/bold]\n")

    # Stop running processes
    if stop_menubar():
        console.print("[green]✓[/green] Stopped menu bar app")

    subprocess.run(["pkill", "-f", "mcp-secrets.*serve"], capture_output=True)

    # Remove launchd agent
    if sys.platform == "darwin":
        if uninstall_launchd_agent():
            console.print("[green]✓[/green] Removed auto-start")
        else:
            console.print("[dim]·[/dim] No auto-start to remove")

    # Uninstall Claude Code plugin
    if is_claude_code_installed():
        success, msg = uninstall_claude_plugin()
        if success:
            console.print("[green]✓[/green] Removed Claude Code plugin")
        else:
            console.print(f"[dim]·[/dim] Claude Code plugin: {msg}")

    # Handle vault
    if delete_vault:
        if Confirm.ask("[red]Delete vault and ALL secrets?[/red]", default=False):
            if CONFIG_DIR.exists():
                shutil.rmtree(CONFIG_DIR)
                console.print("[green]✓[/green] Deleted vault and secrets")
        else:
            console.print("[dim]·[/dim] Kept vault")
    else:
        console.print("[dim]·[/dim] Kept vault at ~/.mcp-secrets (your secrets are safe)")

    console.print("\n[bold green]Uninstall complete![/bold green]")


@main.command()
def status():
    """Show status of mcp-secrets components."""
    console.print("[bold]mcp-secrets status[/bold]\n")

    # Vault
    vault_exists = (CONFIG_DIR / "vault.enc").exists()
    if vault_exists:
        vault = Vault()
        vault.load()
        count = len(vault.list_all())
        console.print(f"[green]✓[/green] Vault: {count} secrets")
    else:
        console.print("[yellow]![/yellow] Vault: not initialized")

    # Menubar
    if is_menubar_running():
        console.print("[green]✓[/green] Menubar: running")
    else:
        console.print("[dim]·[/dim] Menubar: not running")

    # Auto-start
    if sys.platform == "darwin":
        if LAUNCHD_PLIST.exists():
            console.print("[green]✓[/green] Auto-start: enabled")
        else:
            console.print("[dim]·[/dim] Auto-start: not configured")


if __name__ == "__main__":
    main()
