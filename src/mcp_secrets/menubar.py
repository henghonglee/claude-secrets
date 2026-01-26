"""macOS menu bar application for mcp-secrets."""

import os
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

import rumps

from .config import CONFIG_DIR, LOG_FILE
from .events import consume_events
from .vault import Vault
from .webui import WebUIServer


# === PUBLIC API === #


def run_menubar():
    """Run the menu bar application."""
    app = MCPSecretsMenuBar()
    app.run()


class MCPSecretsMenuBar(rumps.App):
    """Menu bar app for managing mcp-secrets."""

    def __init__(self):
        icon_path = _get_icon_path()
        super().__init__(
            "MCP Secrets",
            icon=str(icon_path),
            template=True,
            quit_button=None,
        )
        self.vault = Vault()
        self.server_process = None
        self._pending_secrets = []

        self._webui = WebUIServer(self.vault)
        self._webui_url = self._webui.start()

        self._build_menu()

    @rumps.timer(0.5)
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
                    _notify(
                        title="Secrets Captured",
                        subtitle=f"From: {command[:50]}",
                        message=f"New secrets: {', '.join(secrets)}",
                        sound=True,
                    )

            elif event_type == "secret_needed":
                secrets = data.get("secrets", [])
                if secrets:
                    if isinstance(secrets[0], dict):
                        secret_list = secrets
                    else:
                        secret_list = [{"name": s, "description": ""} for s in secrets]

                    for secret_info in secret_list:
                        name = secret_info.get("name", "")
                        description = secret_info.get("description", "")
                        self._add_secret_value_only(name, description)

            elif event_type == "secret_expiring":
                secrets = data.get("secrets", [])
                if secrets:
                    _notify(
                        title="Secrets Expiring Soon",
                        subtitle="Action may be needed",
                        message=f"Expiring: {', '.join(secrets)}",
                        sound=True,
                    )

    @rumps.timer(5)
    def refresh_status(self, _):
        """Periodically refresh server status."""
        self._build_menu()
        self._check_expiring_secrets()

    def add_pending_secrets(self, _):
        """Add all pending secrets that were requested."""
        secrets_to_add = self._pending_secrets.copy()
        self._pending_secrets = []
        self._build_menu()

        if secrets_to_add:
            first_secret = secrets_to_add[0]
            webbrowser.open(f"{self._webui_url}/add?name={first_secret}")

    def add_secret(self, _):
        """Open browser to add a new secret."""
        webbrowser.open(f"{self._webui_url}/add")

    def view_secrets(self, _):
        """Open browser to view all secrets."""
        webbrowser.open(f"{self._webui_url}/list")

    def view_logs(self, _):
        """Open the log file in Console.app."""
        if LOG_FILE.exists():
            subprocess.run(["open", "-a", "Console", str(LOG_FILE)])
        else:
            rumps.alert(title="No Logs", message="No audit logs found yet.")

    def quit_app(self, _):
        """Quit the menu bar app."""
        if hasattr(self, '_webui'):
            self._webui.stop()
        rumps.quit_application()

    # === PRIVATE METHODS === #

    def _build_menu(self):
        """Build the menu items."""
        self.menu.clear()

        running = self._is_server_running()
        status = "Running" if running else "Stopped"
        status_item = rumps.MenuItem(f"Status: {status}")
        status_item.set_callback(None)
        self.menu.add(status_item)

        self.menu.add(rumps.separator)

        if self._pending_secrets:
            add_missing = rumps.MenuItem(
                f"⚠️ Add Missing Secrets ({len(self._pending_secrets)})",
                callback=self.add_pending_secrets
            )
            self.menu.add(add_missing)
            self.menu.add(rumps.separator)

        self.menu.add(rumps.MenuItem("Add Secret...", callback=self.add_secret))
        self.menu.add(rumps.MenuItem("View Secrets...", callback=self.view_secrets))
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("View Logs...", callback=self.view_logs))
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("Quit", callback=self.quit_app))

    def _is_server_running(self):
        """Check if the MCP server is running."""
        pid_file = CONFIG_DIR / "server.pid"
        if not pid_file.exists():
            return False
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            return True
        except (ValueError, ProcessLookupError, PermissionError):
            pid_file.unlink(missing_ok=True)
            return False

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
                        if 0 < delta.total_seconds() < 1800:
                            expiring_soon.append(secret.name)
                    except (ValueError, TypeError):
                        pass

            if expiring_soon:
                marker_file = CONFIG_DIR / ".expiry_notified"
                already_notified = set()
                if marker_file.exists():
                    already_notified = set(marker_file.read_text().split("\n"))

                new_expiring = [s for s in expiring_soon if s not in already_notified]
                if new_expiring:
                    _notify(
                        title="Secrets Expiring Soon",
                        subtitle="Within 30 minutes",
                        message=f"{', '.join(new_expiring)}",
                        sound=True,
                    )
                    all_notified = already_notified | set(expiring_soon)
                    marker_file.write_text("\n".join(all_notified))
        except Exception:
            pass

    def _add_secret_value_only(self, name: str, description: str):
        """Add a secret - only prompt for value (name and description from LLM)."""
        value = _show_secret_request_dialog(name, description)
        if not value:
            return

        value = value.strip()

        try:
            self.vault.load()
            self.vault.add(name, value, description)
            _notify(
                title="MCP Secrets",
                subtitle="Secret Added",
                message=f"✓ Added: {name}",
            )
            self._build_menu()
        except Exception as e:
            _show_dialog("Error", f"Failed to add secret: {e}", "OK", "OK")


# === PRIVATE MODULE HELPERS === #


def _get_icon_path() -> Path:
    """Get path to menubar icon, creating it if needed."""
    icon_path = CONFIG_DIR / "icon.png"
    if not icon_path.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        icon_data = _create_icon()
        icon_path.write_bytes(icon_data)
    return icon_path


def _create_icon() -> bytes:
    """Create a simple AI-themed menubar icon (18x18 PNG template)."""
    import struct
    import zlib

    width, height = 18, 18

    pattern = [
        "000000000000000000",
        "000000111100000000",
        "000001100110000000",
        "000011000011000000",
        "000011000011000000",
        "000011000011000000",
        "001111111111110000",
        "001110000001110000",
        "001100000000110000",
        "001100011000110000",
        "001100111100110000",
        "001100111100110000",
        "001100011000110000",
        "001100000000110000",
        "001110000001110000",
        "001111111111110000",
        "000000000000000000",
        "000000000000000000",
    ]

    pixels = []
    for row in pattern:
        row_pixels = []
        for char in row:
            if char == '1':
                row_pixels.extend([0, 0, 0, 255])
            else:
                row_pixels.extend([0, 0, 0, 0])
        pixels.append(bytes(row_pixels))

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk_len = struct.pack(">I", len(data))
        chunk_crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xffffffff)
        return chunk_len + chunk_type + data + chunk_crc

    png_signature = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = png_chunk(b'IHDR', ihdr_data)

    raw_data = b''
    for row in pixels:
        raw_data += b'\x00' + row
    compressed = zlib.compress(raw_data, 9)
    idat = png_chunk(b'IDAT', compressed)

    iend = png_chunk(b'IEND', b'')

    return png_signature + ihdr + idat + iend


def _notify(title: str, subtitle: str = "", message: str = "", sound: bool = True):
    """Show a native macOS notification."""
    script = f'display notification "{message}"'
    if title:
        script += f' with title "{title}"'
    if subtitle:
        script += f' subtitle "{subtitle}"'
    if sound:
        script += ' sound name "default"'

    subprocess.run(["osascript", "-e", script], capture_output=True)


def _show_dialog(title: str, message: str, ok_button: str = "OK", cancel_button: str = "Cancel", icon: str = "caution") -> bool:
    """Show a native macOS dialog box. Returns True if OK clicked."""
    script = f'''
    display dialog "{message}" with title "{title}" buttons {{"{cancel_button}", "{ok_button}"}} default button "{ok_button}" with icon {icon}
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return ok_button in result.stdout


def _show_secret_request_dialog(name: str, description: str) -> str | None:
    """Show a dialog for requesting a secret value."""
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


if __name__ == "__main__":
    run_menubar()
