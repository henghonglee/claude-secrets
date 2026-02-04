"""Session-based permission management with time-based expiry."""

import subprocess
import time
from dataclasses import dataclass
from typing import Optional

from .config import load_config


# === DATA STRUCTURES === #


@dataclass
class Permission:
    """A granted permission for a secret."""
    secret_name: str
    granted_at: float  # Kept for audit trail
    expires_at: float

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


# === PUBLIC API === #


class PermissionManager:
    """Manages session permissions for secret access."""

    def __init__(self, timeout_seconds: Optional[int] = None):
        config = load_config()
        self.timeout = timeout_seconds or config.get("session_timeout", 3600)
        self._permissions: dict[str, Permission] = {}

    def is_granted(self, secret_name: str) -> bool:
        """Check if permission is granted and not expired."""
        perm = self._permissions.get(secret_name)
        if perm is None:
            return False
        if perm.is_expired():
            del self._permissions[secret_name]
            return False
        return True

    def grant(self, secret_name: str) -> None:
        """Grant permission for a secret."""
        now = time.time()
        self._permissions[secret_name] = Permission(
            secret_name=secret_name,
            granted_at=now,
            expires_at=now + self.timeout,
        )

    def revoke(self, secret_name: str) -> None:
        """Revoke permission for a secret."""
        self._permissions.pop(secret_name, None)

    def revoke_all(self) -> None:
        """Revoke all permissions."""
        self._permissions.clear()

    def get_status(self) -> list[dict]:
        """Get status of all permissions."""
        now = time.time()
        result = []
        expired = []

        for name, perm in self._permissions.items():
            if perm.is_expired():
                expired.append(name)
            else:
                result.append({
                    "name": name,
                    "status": "granted",
                    "expires_in": int(perm.expires_at - now),
                })

        for name in expired:
            del self._permissions[name]

        return result

    def get_pending_secrets(self, requested: list[str]) -> list[str]:
        """Get list of secrets that need permission from requested list."""
        return [name for name in requested if not self.is_granted(name)]


# === MODULE HELPERS === #


def request_permission(secret_name: str, description: str, command: str) -> bool:
    """Request permission via native macOS dialog. Blocks until user responds."""
    script = f'''
    display dialog "{_escape_applescript(secret_name)}" with title "Allow Secret Access?" buttons {{"Deny", "Allow"}} default button "Allow" cancel button "Deny" with icon caution
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def _escape_applescript(s: str) -> str:
    """Escape special characters for AppleScript."""
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')
