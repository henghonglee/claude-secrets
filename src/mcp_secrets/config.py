"""Configuration management for mcp-secrets."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = {
    "session_timeout": 3600,  # 1 hour in seconds
}

CONFIG_DIR = Path.home() / ".mcp-secrets"
CONFIG_FILE = CONFIG_DIR / "config.json"
VAULT_FILE = CONFIG_DIR / "vault.enc"
LOG_FILE = CONFIG_DIR / "audit.log"
EVENTS_FILE = CONFIG_DIR / "events.json"


def ensure_config_dir() -> None:
    """Ensure the config directory exists."""
    CONFIG_DIR.mkdir(mode=0o700, exist_ok=True)


def load_config() -> dict[str, Any]:
    """Load configuration from file, creating defaults if needed."""
    ensure_config_dir()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            config = json.load(f)
            # Merge with defaults for any missing keys
            return {**DEFAULT_CONFIG, **config}
    return DEFAULT_CONFIG.copy()


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to file."""
    ensure_config_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    CONFIG_FILE.chmod(0o600)


def get_config_value(key: str) -> Any:
    """Get a config value by dot-notation key (e.g., 'llm.base_url')."""
    config = load_config()
    parts = key.split(".")
    value = config
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    return value


def set_config_value(key: str, value: str) -> None:
    """Set a config value by dot-notation key."""
    config = load_config()
    parts = key.split(".")
    target = config
    for part in parts[:-1]:
        if part not in target:
            target[part] = {}
        target = target[part]

    # Try to parse as JSON for complex values, otherwise use string
    try:
        parsed = json.loads(value)
        target[parts[-1]] = parsed
    except json.JSONDecodeError:
        # Try to parse as number
        try:
            if "." in value:
                target[parts[-1]] = float(value)
            else:
                target[parts[-1]] = int(value)
        except ValueError:
            target[parts[-1]] = value

    save_config(config)


def emit_event(event_type: str, data: dict) -> None:
    """Emit an event for the menubar to consume.

    Event types:
    - "secret_captured": New secret was captured from command output
    - "secret_expiring": A secret is about to expire
    - "secret_needed": A command needs a secret that doesn't exist
    - "permission_requested": A command needs permission to use a secret
    """
    ensure_config_dir()

    # Load existing events
    events = []
    if EVENTS_FILE.exists():
        try:
            events = json.loads(EVENTS_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            events = []

    # Add new event
    events.append({
        "type": event_type,
        "data": data,
        "timestamp": datetime.now().isoformat(),
    })

    # Keep only last 50 events
    events = events[-50:]

    EVENTS_FILE.write_text(json.dumps(events, indent=2))


def consume_events() -> list[dict]:
    """Consume all pending events (returns and clears them)."""
    ensure_config_dir()

    if not EVENTS_FILE.exists():
        return []

    try:
        events = json.loads(EVENTS_FILE.read_text())
        EVENTS_FILE.write_text("[]")
        return events
    except (json.JSONDecodeError, IOError):
        return []


def peek_events() -> list[dict]:
    """Peek at events without consuming them."""
    if not EVENTS_FILE.exists():
        return []

    try:
        return json.loads(EVENTS_FILE.read_text())
    except (json.JSONDecodeError, IOError):
        return []




def request_permission(secret_name: str, description: str, command: str) -> bool:
    """Request permission via native macOS dialog. Blocks until user responds."""
    import subprocess

    # Escape special characters for AppleScript
    def escape(s: str) -> str:
        return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')

    script = f'''
    display dialog "{escape(secret_name)}" with title "Allow Secret Access?" buttons {{"Deny", "Allow"}} default button "Allow" cancel button "Deny" with icon caution
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
        # osascript returns 0 if OK/Allow clicked, non-zero if Cancel/Deny
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


