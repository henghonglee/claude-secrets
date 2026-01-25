"""macOS menu bar application for mcp-secrets."""

import os
import subprocess
from datetime import datetime

import rumps

from .vault import Vault
from .config import CONFIG_DIR, LOG_FILE, consume_events


def notify(title: str, subtitle: str = "", message: str = "", sound: bool = True):
    """Show a native macOS notification."""
    script = f'display notification "{message}"'
    if title:
        script += f' with title "{title}"'
    if subtitle:
        script += f' subtitle "{subtitle}"'
    if sound:
        script += ' sound name "default"'

    subprocess.run(["osascript", "-e", script], capture_output=True)


def show_dialog(title: str, message: str, ok_button: str = "OK", cancel_button: str = "Cancel", icon: str = "caution") -> bool:
    """Show a native macOS dialog box. Returns True if OK clicked.

    icon: 'caution', 'note', 'stop', or path to .icns file
    """
    script = f'''
    display dialog "{message}" with title "{title}" buttons {{"{cancel_button}", "{ok_button}"}} default button "{ok_button}" with icon {icon}
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return ok_button in result.stdout


def show_input_dialog(title: str, message: str, default_text: str = "", hidden: bool = False) -> str | None:
    """Show a native macOS input dialog. Returns text or None if cancelled."""
    hidden_arg = "with hidden answer" if hidden else ""
    script = f'''
    display dialog "{message}" with title "{title}" default answer "{default_text}" {hidden_arg} buttons {{"Cancel", "OK"}} default button "OK" with icon note
    text returned of result
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def show_secret_request_dialog(name: str, description: str) -> str | None:
    """Show a dialog for requesting a secret value."""
    # Escape special characters for AppleScript
    def escape(s: str) -> str:
        return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')

    script = f'''
    display dialog "{escape(name)}" with title "Enter Secret Value" default answer "" buttons {{"Cancel", "Save"}} default button "Save" with hidden answer with icon note
    text returned of result
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


class MCPSecretsMenuBar(rumps.App):
    """Menu bar app for managing mcp-secrets."""

    def __init__(self):
        super().__init__(
            "MCP Secrets",
            icon=None,  # Will set dynamically
            quit_button=None,  # Custom quit
        )
        self.vault = Vault()
        self.server_process = None
        self._pending_secrets = []  # Secrets that need to be added
        self._update_icon()
        self._build_menu()

    def _update_icon(self):
        """Update icon based on server status."""
        if self._is_server_running():
            self.title = "🔐"  # Lock icon when running
        else:
            self.title = "🔓"  # Unlocked when stopped

    def _is_server_running(self):
        """Check if the MCP server is running."""
        pid_file = CONFIG_DIR / "server.pid"
        if not pid_file.exists():
            return False
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # Check if process exists
            return True
        except (ValueError, ProcessLookupError, PermissionError):
            pid_file.unlink(missing_ok=True)
            return False

    def _build_menu(self):
        """Build the menu items."""
        self.menu.clear()

        # Status
        running = self._is_server_running()
        status = "Running" if running else "Stopped"
        status_item = rumps.MenuItem(f"Status: {status}")
        status_item.set_callback(None)  # Non-clickable
        self.menu.add(status_item)

        self.menu.add(rumps.separator)

        # Show pending secrets if any
        if self._pending_secrets:
            add_missing = rumps.MenuItem(
                f"⚠️ Add Missing Secrets ({len(self._pending_secrets)})",
                callback=self.add_pending_secrets
            )
            self.menu.add(add_missing)
            self.menu.add(rumps.separator)

        # Add Secret
        self.menu.add(rumps.MenuItem("Add Secret...", callback=self.add_secret))

        # List Secrets submenu
        secrets_menu = rumps.MenuItem("Secrets")
        try:
            self.vault.load()
            secrets = self.vault.list_all()
            if secrets:
                for secret in secrets:
                    desc = secret.description or "(no description)"
                    # Truncate description
                    if len(desc) > 40:
                        desc = desc[:37] + "..."

                    # Show expiry if set
                    if secret.expires_at:
                        try:
                            exp = datetime.fromisoformat(secret.expires_at.replace("Z", "+00:00"))
                            now = datetime.now(exp.tzinfo)
                            if exp < now:
                                desc += " [EXPIRED]"
                            else:
                                delta = exp - now
                                hours = delta.total_seconds() / 3600
                                if hours < 1:
                                    desc += f" [{int(delta.total_seconds()/60)}m left]"
                                elif hours < 24:
                                    desc += f" [{int(hours)}h left]"
                        except (ValueError, TypeError):
                            pass

                    item = rumps.MenuItem(f"{secret.name}: {desc}")
                    item.set_callback(None)
                    secrets_menu.add(item)
            else:
                no_secrets = rumps.MenuItem("(empty)")
                no_secrets.set_callback(None)
                secrets_menu.add(no_secrets)
        except Exception:
            error_item = rumps.MenuItem("(vault not initialized)")
            error_item.set_callback(None)
            secrets_menu.add(error_item)

        self.menu.add(secrets_menu)

        self.menu.add(rumps.separator)

        # View Logs
        self.menu.add(rumps.MenuItem("View Logs...", callback=self.view_logs))

        self.menu.add(rumps.separator)

        # Quit
        self.menu.add(rumps.MenuItem("Quit", callback=self.quit_app))

    @rumps.timer(0.5)  # Check frequently for permission requests
    def check_events(self, _):
        """Check for events from the server and show notifications."""
        events = consume_events()

        for event in events:
            event_type = event.get("type")
            data = event.get("data", {})

            if event_type == "secret_captured":
                secrets = data.get("secrets", [])
                command = data.get("command", "unknown command")
                if secrets:
                    notify(
                        title="Secrets Captured",
                        subtitle=f"From: {command[:50]}",
                        message=f"New secrets: {', '.join(secrets)}",
                        sound=True,
                    )

            elif event_type == "secret_needed":
                secrets = data.get("secrets", [])  # List of {name, description}
                if secrets:
                    # Build list of secret info
                    if isinstance(secrets[0], dict):
                        secret_list = secrets
                    else:
                        secret_list = [{"name": s, "description": ""} for s in secrets]

                    # Show each secret request individually
                    for secret_info in secret_list:
                        name = secret_info.get("name", "")
                        description = secret_info.get("description", "")
                        self._add_secret_value_only(name, description)

            elif event_type == "secret_expiring":
                secrets = data.get("secrets", [])
                if secrets:
                    notify(
                        title="Secrets Expiring Soon",
                        subtitle="Action may be needed",
                        message=f"Expiring: {', '.join(secrets)}",
                        sound=True,
                    )

    @rumps.timer(5)
    def refresh_status(self, _):
        """Periodically refresh server status."""
        self._update_icon()
        self._build_menu()
        self._check_expiring_secrets()

    def _check_expiring_secrets(self):
        """Check for secrets expiring within the next hour."""
        try:
            self.vault.load()
            secrets = self.vault.list_all(include_expired=False)
            expiring_soon = []

            for secret in secrets:
                if secret.expires_at:
                    try:
                        exp = datetime.fromisoformat(secret.expires_at.replace("Z", "+00:00"))
                        now = datetime.now(exp.tzinfo)
                        delta = exp - now
                        # Warn if expiring within 30 minutes
                        if 0 < delta.total_seconds() < 1800:
                            expiring_soon.append(secret.name)
                    except (ValueError, TypeError):
                        pass

            # Only notify once per secret (use a simple file marker)
            if expiring_soon:
                marker_file = CONFIG_DIR / ".expiry_notified"
                already_notified = set()
                if marker_file.exists():
                    already_notified = set(marker_file.read_text().split("\n"))

                new_expiring = [s for s in expiring_soon if s not in already_notified]
                if new_expiring:
                    notify(
                        title="Secrets Expiring Soon",
                        subtitle="Within 30 minutes",
                        message=f"{', '.join(new_expiring)}",
                        sound=True,
                    )
                    # Mark as notified
                    all_notified = already_notified | set(expiring_soon)
                    marker_file.write_text("\n".join(all_notified))
        except Exception:
            pass

    def add_pending_secrets(self, _):
        """Add all pending secrets that were requested."""
        secrets_to_add = self._pending_secrets.copy()
        self._pending_secrets = []
        self._build_menu()

        for secret_name in secrets_to_add:
            self._add_secret_dialog(secret_name)

    def add_secret(self, _):
        """Open dialog to add a new secret."""
        self._add_secret_dialog()

    def _add_secret_value_only(self, name: str, description: str):
        """Add a secret - only prompt for value (name and description from LLM)."""
        value = show_secret_request_dialog(name, description)
        if not value:
            return

        value = value.strip()

        # Save to vault
        try:
            self.vault.load()
            self.vault.add(name, value, description)
            notify(
                title="MCP Secrets",
                subtitle="Secret Added",
                message=f"✓ Added: {name}",
            )
            self._build_menu()
        except Exception as e:
            show_dialog("Error", f"Failed to add secret: {e}", "OK", "OK")

    def _add_secret_dialog(self, prefill_name: str = ""):
        """Show dialog to add a new secret manually."""
        # Get secret name
        name = show_input_dialog(
            "Add Secret",
            "Enter the secret name (e.g., AWS_API_KEY):",
            prefill_name
        )
        if not name:
            return

        name = name.strip().upper().replace(" ", "_")

        # Get secret value (hidden input)
        value = show_input_dialog(
            "Add Secret",
            f"Enter the secret value for {name}:",
            "",
            hidden=True
        )
        if not value:
            return

        value = value.strip()

        # Get description
        description = show_input_dialog(
            "Add Secret",
            "Description (help AI assistants understand what this secret is for):",
            ""
        )
        if description is None:
            return

        description = description.strip()

        # Save to vault
        try:
            self.vault.load()
            self.vault.add(name, value, description)
            notify(
                title="MCP Secrets",
                subtitle="Secret Added",
                message=f"Added: {name}",
            )
            self._build_menu()
        except Exception as e:
            show_dialog("Error", f"Failed to add secret: {e}", "OK", "OK")

    def view_logs(self, _):
        """Open the log file in Console.app."""
        if LOG_FILE.exists():
            subprocess.run(["open", "-a", "Console", str(LOG_FILE)])
        else:
            rumps.alert(
                title="No Logs",
                message="No audit logs found yet.",
            )

    def quit_app(self, _):
        """Quit the menu bar app."""
        rumps.quit_application()


def run_menubar():
    """Run the menu bar application."""
    app = MCPSecretsMenuBar()
    app.run()


if __name__ == "__main__":
    run_menubar()
