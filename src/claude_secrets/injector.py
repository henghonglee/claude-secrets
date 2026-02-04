"""Placeholder substitution for secrets in commands."""

import re
from typing import Optional

from .vault import Vault

# Pattern to match {{SECRET_NAME}} placeholders
PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def extract_placeholders(command: str) -> list[str]:
    """Extract all secret placeholder names from a command."""
    return PLACEHOLDER_PATTERN.findall(command)


def inject_secrets(command: str, vault: Vault, allowed: Optional[set[str]] = None) -> tuple[str, list[str]]:
    """Substitute secret placeholders with actual values.

    Args:
        command: Command string with {{SECRET_NAME}} placeholders
        vault: Vault instance to get secret values from
        allowed: Optional set of allowed secret names (for permission checking)

    Returns:
        Tuple of (substituted command, list of missing secret names)
    """
    missing = []

    def replace(match: re.Match) -> str:
        name = match.group(1)

        # Check if allowed
        if allowed is not None and name not in allowed:
            missing.append(name)
            return match.group(0)  # Keep placeholder

        # Get secret value
        value = vault.get_value(name)
        if value is None:
            missing.append(name)
            return match.group(0)  # Keep placeholder

        return value

    result = PLACEHOLDER_PATTERN.sub(replace, command)
    return result, missing


def mask_command(command: str) -> str:
    """Mask secret placeholders in a command for display.

    Replaces {{SECRET_NAME}} with [SECRET_NAME] for safe logging.
    """
    return PLACEHOLDER_PATTERN.sub(r"[\1]", command)
