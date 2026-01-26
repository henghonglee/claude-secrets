"""Encrypted secret storage using Fernet."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict, field

from cryptography.fernet import Fernet

from .config import CONFIG_DIR, VAULT_FILE, ensure_config_dir

KEY_FILE = CONFIG_DIR / "key"


@dataclass
class Secret:
    """A stored secret with metadata."""
    name: str
    value: str
    description: str
    tags: list[str] = field(default_factory=list)
    expires_at: Optional[str] = None  # ISO 8601 timestamp

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Secret":
        # Handle old secrets without expires_at
        if "expires_at" not in data:
            data["expires_at"] = None
        if "tags" not in data:
            data["tags"] = []
        return cls(**data)

    def is_expired(self) -> bool:
        """Check if the secret has expired."""
        if not self.expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.now(expiry.tzinfo) > expiry
        except (ValueError, TypeError):
            return False


class Vault:
    """Encrypted secret storage."""

    def __init__(self):
        self._fernet: Optional[Fernet] = None
        self._secrets: dict[str, Secret] = {}

    def _get_or_create_key(self) -> bytes:
        """Get encryption key from file, or create if not exists."""
        ensure_config_dir()
        if KEY_FILE.exists():
            return KEY_FILE.read_bytes()

        # Generate new key
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
        KEY_FILE.chmod(0o600)  # Owner read/write only
        return key

    def _get_fernet(self) -> Fernet:
        """Get or create Fernet instance."""
        if self._fernet is None:
            key = self._get_or_create_key()
            self._fernet = Fernet(key)
        return self._fernet

    def init(self) -> bool:
        """Initialize the vault. Returns True if newly created."""
        ensure_config_dir()
        if VAULT_FILE.exists():
            self.load()
            return False
        # Create empty vault
        self._secrets = {}
        self.save()
        return True

    def load(self) -> None:
        """Load secrets from encrypted vault file."""
        if not VAULT_FILE.exists():
            self._secrets = {}
            return

        fernet = self._get_fernet()
        encrypted_data = VAULT_FILE.read_bytes()
        decrypted_data = fernet.decrypt(encrypted_data)
        data = json.loads(decrypted_data.decode())

        self._secrets = {
            name: Secret.from_dict(secret_data)
            for name, secret_data in data.get("secrets", {}).items()
        }

    def save(self) -> None:
        """Save secrets to encrypted vault file."""
        ensure_config_dir()
        fernet = self._get_fernet()

        data = {
            "secrets": {
                name: secret.to_dict()
                for name, secret in self._secrets.items()
            }
        }

        encrypted_data = fernet.encrypt(json.dumps(data).encode())
        VAULT_FILE.write_bytes(encrypted_data)
        VAULT_FILE.chmod(0o600)

    def add(
        self,
        name: str,
        value: str,
        description: str,
        tags: Optional[list[str]] = None,
        expires_at: Optional[str] = None,
    ) -> None:
        """Add or update a secret."""
        self._secrets[name] = Secret(
            name=name,
            value=value,
            description=description,
            tags=tags or [],
            expires_at=expires_at,
        )
        self.save()

    def get(self, name: str) -> Optional[Secret]:
        """Get a secret by name. Returns None if expired."""
        secret = self._secrets.get(name)
        if secret and secret.is_expired():
            return None
        return secret

    def get_value(self, name: str) -> Optional[str]:
        """Get just the secret value by name. Returns None if expired."""
        secret = self.get(name)
        return secret.value if secret else None

    def remove(self, name: str) -> bool:
        """Remove a secret. Returns True if it existed."""
        if name in self._secrets:
            del self._secrets[name]
            self.save()
            return True
        return False

    def list_all(self, include_expired: bool = False) -> list[Secret]:
        """List all secrets (metadata only, not values)."""
        if include_expired:
            return list(self._secrets.values())
        return [s for s in self._secrets.values() if not s.is_expired()]

    def list_by_tag(self, tag: str) -> list[Secret]:
        """List secrets filtered by tag."""
        return [s for s in self._secrets.values() if tag in s.tags and not s.is_expired()]

    def export_encrypted(self) -> bytes:
        """Export all secrets as encrypted blob."""
        fernet = self._get_fernet()
        data = {
            "secrets": {
                name: secret.to_dict()
                for name, secret in self._secrets.items()
            }
        }
        return fernet.encrypt(json.dumps(data).encode())

    def import_encrypted(self, data: bytes) -> int:
        """Import secrets from encrypted blob. Returns count imported."""
        fernet = self._get_fernet()
        decrypted = fernet.decrypt(data)
        imported_data = json.loads(decrypted.decode())

        count = 0
        for name, secret_data in imported_data.get("secrets", {}).items():
            self._secrets[name] = Secret.from_dict(secret_data)
            count += 1

        self.save()
        return count
