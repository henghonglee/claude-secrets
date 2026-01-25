"""Tests for placeholder injection."""

import pytest
from unittest.mock import MagicMock

from mcp_secrets.injector import extract_placeholders, inject_secrets, mask_command


def test_extract_placeholders_single():
    """Test extracting a single placeholder."""
    result = extract_placeholders("echo {{MY_SECRET}}")
    assert result == ["MY_SECRET"]


def test_extract_placeholders_multiple():
    """Test extracting multiple placeholders."""
    result = extract_placeholders("aws s3 ls --access-key {{AWS_KEY}} --secret {{AWS_SECRET}}")
    assert result == ["AWS_KEY", "AWS_SECRET"]


def test_extract_placeholders_none():
    """Test command with no placeholders."""
    result = extract_placeholders("echo hello")
    assert result == []


def test_extract_placeholders_repeated():
    """Test repeated placeholders."""
    result = extract_placeholders("echo {{KEY}} and {{KEY}} again")
    assert result == ["KEY", "KEY"]


def test_inject_secrets_success():
    """Test successful secret injection."""
    vault = MagicMock()
    vault.get_value.return_value = "secret123"

    result, missing = inject_secrets(
        "echo {{MY_SECRET}}",
        vault,
        allowed={"MY_SECRET"}
    )

    assert result == "echo secret123"
    assert missing == []


def test_inject_secrets_missing():
    """Test injection with missing secret."""
    vault = MagicMock()
    vault.get_value.return_value = None

    result, missing = inject_secrets(
        "echo {{MISSING}}",
        vault,
        allowed={"MISSING"}
    )

    assert result == "echo {{MISSING}}"
    assert missing == ["MISSING"]


def test_inject_secrets_not_allowed():
    """Test injection with secret not in allowed set."""
    vault = MagicMock()
    vault.get_value.return_value = "secret123"

    result, missing = inject_secrets(
        "echo {{MY_SECRET}}",
        vault,
        allowed=set()  # Empty allowed set
    )

    assert result == "echo {{MY_SECRET}}"
    assert missing == ["MY_SECRET"]


def test_mask_command():
    """Test command masking for logging."""
    result = mask_command("aws s3 ls --key {{AWS_KEY}}")
    assert result == "aws s3 ls --key [AWS_KEY]"
