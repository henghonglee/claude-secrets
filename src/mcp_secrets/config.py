"""Configuration management for mcp-secrets."""

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = {
    "session_timeout": 3600,  # 1 hour in seconds
}

CONFIG_DIR = Path.home() / ".mcp-secrets"
CONFIG_FILE = CONFIG_DIR / "config.json"
VAULT_FILE = CONFIG_DIR / "vault.enc"
LOG_FILE = CONFIG_DIR / "audit.log"


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

