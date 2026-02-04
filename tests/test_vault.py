"""Tests for vault functionality."""

import pytest
from pathlib import Path
from unittest.mock import patch

from claude_secrets.vault import Vault, Secret


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory."""
    with patch("claude_secrets.vault.CONFIG_DIR", tmp_path):
        with patch("claude_secrets.vault.VAULT_FILE", tmp_path / "vault.enc"):
            with patch("claude_secrets.vault.KEY_FILE", tmp_path / "key"):
                yield tmp_path


def test_secret_dataclass():
    """Test Secret dataclass."""
    secret = Secret(
        name="TEST",
        value="secret123",
        description="A test secret",
        tags=["test", "dev"]
    )

    assert secret.name == "TEST"
    assert secret.value == "secret123"
    assert secret.tags == ["test", "dev"]


def test_secret_to_dict():
    """Test Secret serialization."""
    secret = Secret(
        name="TEST",
        value="secret123",
        description="Test",
        tags=[]
    )

    d = secret.to_dict()
    assert d["name"] == "TEST"
    assert d["value"] == "secret123"


def test_secret_from_dict():
    """Test Secret deserialization."""
    d = {
        "name": "TEST",
        "value": "secret123",
        "description": "Test",
        "tags": ["a"]
    }

    secret = Secret.from_dict(d)
    assert secret.name == "TEST"
    assert secret.value == "secret123"
    assert secret.tags == ["a"]


def test_vault_init_new(temp_config_dir):
    """Test initializing a new vault."""
    vault = Vault()
    is_new = vault.init()

    assert is_new is True
    assert (temp_config_dir / "vault.enc").exists()
    assert (temp_config_dir / "key").exists()


def test_vault_init_existing(temp_config_dir):
    """Test initializing existing vault."""
    vault = Vault()
    vault.init()

    vault2 = Vault()
    is_new = vault2.init()

    assert is_new is False


def test_vault_add_get(temp_config_dir):
    """Test adding and retrieving a secret."""
    vault = Vault()
    vault.init()

    vault.add("TEST_KEY", "secret123", "Test secret", ["test"])

    secret = vault.get("TEST_KEY")
    assert secret is not None
    assert secret.value == "secret123"
    assert secret.description == "Test secret"


def test_vault_get_value(temp_config_dir):
    """Test getting just the secret value."""
    vault = Vault()
    vault.init()
    vault.add("TEST", "myvalue", "Test", [])

    assert vault.get_value("TEST") == "myvalue"
    assert vault.get_value("NONEXISTENT") is None


def test_vault_remove(temp_config_dir):
    """Test removing a secret."""
    vault = Vault()
    vault.init()
    vault.add("TEST", "value", "Test", [])

    assert vault.remove("TEST") is True
    assert vault.get("TEST") is None
    assert vault.remove("TEST") is False


def test_vault_list_all(temp_config_dir):
    """Test listing all secrets."""
    vault = Vault()
    vault.init()
    vault.add("A", "v1", "First", ["x"])
    vault.add("B", "v2", "Second", ["y"])

    secrets = vault.list_all()
    names = [s.name for s in secrets]

    assert "A" in names
    assert "B" in names


def test_vault_list_by_tag(temp_config_dir):
    """Test filtering by tag."""
    vault = Vault()
    vault.init()
    vault.add("A", "v1", "First", ["prod"])
    vault.add("B", "v2", "Second", ["dev"])
    vault.add("C", "v3", "Third", ["prod", "aws"])

    prod_secrets = vault.list_by_tag("prod")
    names = [s.name for s in prod_secrets]

    assert "A" in names
    assert "C" in names
    assert "B" not in names


def test_vault_persistence(temp_config_dir):
    """Test that secrets persist across vault instances."""
    vault1 = Vault()
    vault1.init()
    vault1.add("PERSIST", "value123", "Persistent secret", [])

    # Create new vault instance
    vault2 = Vault()
    vault2.load()

    secret = vault2.get("PERSIST")
    assert secret is not None
    assert secret.value == "value123"
