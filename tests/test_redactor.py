"""Tests for output redaction."""

import json
import pytest

from claude_secrets.redactor import redact_secrets, redact_patterns, redact_json_paths, apply_redaction


def test_redact_secrets_single():
    """Test redacting a single secret."""
    result = redact_secrets(
        "The password is secret123",
        ["secret123"]
    )
    assert result == "The password is [REDACTED]"


def test_redact_secrets_multiple():
    """Test redacting multiple secrets."""
    result = redact_secrets(
        "Key: abc123, Token: xyz789",
        ["abc123", "xyz789"]
    )
    assert result == "Key: [REDACTED], Token: [REDACTED]"


def test_redact_secrets_repeated():
    """Test redacting repeated occurrences."""
    result = redact_secrets(
        "secret123 and secret123 again",
        ["secret123"]
    )
    assert result == "[REDACTED] and [REDACTED] again"


def test_redact_secrets_special_chars():
    """Test redacting secrets with regex special characters."""
    result = redact_secrets(
        "Password is pass$word.123",
        ["pass$word.123"]
    )
    assert result == "Password is [REDACTED]"


def test_redact_secrets_empty():
    """Test with empty secrets list."""
    result = redact_secrets("Hello world", [])
    assert result == "Hello world"


def test_redact_patterns_aws_key():
    """Test pattern-based redaction of AWS keys."""
    result = redact_patterns("Access key: AKIAIOSFODNN7EXAMPLE")
    assert "AKIAIOSFODNN7EXAMPLE" not in result


def test_redact_patterns_github_token():
    """Test pattern-based redaction of GitHub tokens."""
    result = redact_patterns("Token: ghp_1234567890abcdefghijklmnopqrstuvwxyz")
    assert "ghp_" not in result


def test_redact_patterns_no_false_positives():
    """Test that normal text isn't redacted."""
    text = "Hello world, this is a normal message"
    result = redact_patterns(text)
    assert result == text


def test_redact_json_paths_simple():
    """Test redacting a simple JSON path."""
    data = {
        "Credentials": {
            "AccessKeyId": "AKIAEXAMPLE",
            "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        }
    }
    result = redact_json_paths(
        json.dumps(data),
        ["$.Credentials.SecretAccessKey"]
    )
    parsed = json.loads(result)
    assert parsed["Credentials"]["SecretAccessKey"] == "[REDACTED]"
    assert parsed["Credentials"]["AccessKeyId"] == "AKIAEXAMPLE"


def test_redact_json_paths_multiple():
    """Test redacting multiple JSON paths."""
    data = {
        "Credentials": {
            "AccessKeyId": "AKIAEXAMPLE",
            "SecretAccessKey": "secret1",
            "SessionToken": "token123"
        }
    }
    result = redact_json_paths(
        json.dumps(data),
        ["Credentials.SecretAccessKey", "Credentials.SessionToken"]
    )
    parsed = json.loads(result)
    assert parsed["Credentials"]["SecretAccessKey"] == "[REDACTED]"
    assert parsed["Credentials"]["SessionToken"] == "[REDACTED]"
    assert parsed["Credentials"]["AccessKeyId"] == "AKIAEXAMPLE"


def test_redact_json_paths_array_wildcard():
    """Test redacting with array wildcard."""
    data = {
        "users": [
            {"name": "alice", "password": "pass1"},
            {"name": "bob", "password": "pass2"}
        ]
    }
    result = redact_json_paths(
        json.dumps(data),
        ["users.*.password"]
    )
    parsed = json.loads(result)
    assert parsed["users"][0]["password"] == "[REDACTED]"
    assert parsed["users"][1]["password"] == "[REDACTED]"
    assert parsed["users"][0]["name"] == "alice"


def test_redact_json_paths_non_json():
    """Test that non-JSON text is returned unchanged."""
    text = "This is not JSON"
    result = redact_json_paths(text, ["$.foo.bar"])
    assert result == text


def test_apply_redaction_combined():
    """Test applying multiple redaction methods."""
    data = {
        "key": "AKIAIOSFODNN7EXAMPLE",
        "secret": "my-secret-value"
    }
    result = apply_redaction(
        json.dumps(data),
        secret_values=["my-secret-value"],
        json_paths=["$.secret"],
    )
    parsed = json.loads(result)
    # Both redaction methods should work
    assert "[REDACTED]" in result
    # AWS key should be caught by builtin patterns
    assert "AKIAIOSFODNN7EXAMPLE" not in result


def test_apply_redaction_custom_patterns():
    """Test applying custom regex patterns."""
    text = "API key: custom-key-12345-abcde"
    result = apply_redaction(
        text,
        patterns=[r"custom-key-[a-z0-9-]+"],
        use_builtin_patterns=False,
    )
    assert "custom-key-12345-abcde" not in result
    assert "[REDACTED]" in result
