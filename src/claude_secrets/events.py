"""Event system for inter-process communication.

Events allow the MCP server to communicate with the menubar app
without direct coupling. Events are stored in a JSON file and
consumed by the menubar's polling loop.
"""

import json
from datetime import datetime
from pathlib import Path

from .config import CONFIG_DIR, ensure_config_dir

EVENTS_FILE = CONFIG_DIR / "events.json"


def emit_event(event_type: str, data: dict) -> None:
    """Emit an event for the menubar to consume.

    Event types:
    - "secret_captured": New secret was captured from command output
    - "secret_expiring": A secret is about to expire
    - "secret_needed": A command needs a secret that doesn't exist
    - "permission_requested": A command needs permission to use a secret
    """
    ensure_config_dir()

    events = []
    if EVENTS_FILE.exists():
        try:
            events = json.loads(EVENTS_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            events = []

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
