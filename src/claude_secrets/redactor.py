"""Output redaction to hide secret values."""

import re
import json
from typing import Iterable, Optional


def redact_secrets(text: str, secret_values: Iterable[str], placeholder: str = "[REDACTED]") -> str:
    """Redact known secret values from text.

    Args:
        text: Text to redact
        secret_values: Iterable of secret values to redact
        placeholder: Replacement text

    Returns:
        Text with secrets replaced
    """
    result = text
    for value in secret_values:
        if value:
            escaped = re.escape(value)
            result = re.sub(escaped, placeholder, result)
    return result


def redact_patterns(text: str, patterns: Optional[list[str]] = None, placeholder: str = "[REDACTED]") -> str:
    """Redact text matching regex patterns.

    Args:
        text: Text to redact
        patterns: List of regex patterns to match and redact. If None, uses built-in patterns.
        placeholder: Replacement text

    Returns:
        Text with matches replaced
    """
    if patterns is None:
        # Built-in patterns for common secrets
        pattern_list = [
            # AWS keys
            (r"AKIA[0-9A-Z]{16}", "[AWS_ACCESS_KEY]"),
            # AWS secret keys (40 char base64)
            (r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])", placeholder),
            # GitHub tokens
            (r"ghp_[A-Za-z0-9]{36}", "[GITHUB_TOKEN]"),
            (r"gho_[A-Za-z0-9]{36}", "[GITHUB_TOKEN]"),
            (r"ghu_[A-Za-z0-9]{36}", "[GITHUB_TOKEN]"),
            (r"ghs_[A-Za-z0-9]{36}", "[GITHUB_TOKEN]"),
            (r"ghr_[A-Za-z0-9]{36}", "[GITHUB_TOKEN]"),
            # Slack tokens
            (r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24}", "[SLACK_TOKEN]"),
            # Generic API keys (be conservative)
            (r"(?i)api[_-]?key['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_-]{20,})['\"]?", placeholder),
            # Bearer tokens
            (r"Bearer\s+[A-Za-z0-9_-]{20,}", "[BEARER_TOKEN]"),
        ]
    else:
        # Use provided patterns
        pattern_list = [(p, placeholder) for p in patterns]

    result = text
    for pattern, replacement in pattern_list:
        try:
            result = re.sub(pattern, replacement, result)
        except re.error:
            # Skip invalid patterns
            pass
    return result


def redact_json_paths(
    text: str,
    json_paths: list[str],
    placeholder: str = "[REDACTED]"
) -> str:
    """Redact specific JSON paths in the output.

    Args:
        text: Text containing JSON
        json_paths: List of JSON paths like "$.Credentials.SecretAccessKey"
        placeholder: Replacement text

    Returns:
        Text with JSON values at paths replaced
    """
    result, _ = redact_json_paths_with_capture(text, json_paths, placeholder)
    return result


def redact_json_paths_with_capture(
    text: str,
    json_paths: list[str],
    placeholder: str = "[REDACTED]",
    capture_names: Optional[dict[str, str]] = None,
) -> tuple[str, dict[str, str]]:
    """Redact specific JSON paths and optionally capture values.

    Args:
        text: Text containing JSON
        json_paths: List of JSON paths like "$.Credentials.SecretAccessKey"
        placeholder: Replacement text (used if no capture name provided)
        capture_names: Optional dict mapping JSON paths to capture names.
                      If provided, redacted values are replaced with {{SECRET:name}}
                      and the actual values are returned in the captures dict.

    Returns:
        Tuple of (redacted text, captured values dict)
    """
    if not json_paths:
        return text, {}

    # Try to parse as JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Not valid JSON, return as-is
        return text, {}

    captures: dict[str, str] = {}

    def get_path_parts(path: str) -> list[str]:
        """Parse a JSON path into parts."""
        # Remove leading $. if present
        if path.startswith("$."):
            path = path[2:]
        elif path.startswith("$"):
            path = path[1:]
        return path.split(".")

    def redact_at_path(obj, parts: list[str], path: str, index_suffix: str = "") -> bool:
        """Recursively redact value at path. Returns True if redacted."""
        if not parts:
            return False

        key = parts[0]
        remaining = parts[1:]

        if isinstance(obj, dict):
            if key in obj:
                if remaining:
                    return redact_at_path(obj[key], remaining, path, index_suffix)
                else:
                    # Capture and redact this value
                    original_value = obj[key]
                    if capture_names and path in capture_names:
                        name = capture_names[path]
                        if index_suffix:
                            name = f"{name}{index_suffix}"
                        captures[name] = str(original_value)
                        obj[key] = f"{{{{SECRET:{name}}}}}"
                    else:
                        obj[key] = placeholder
                    return True
        elif isinstance(obj, list):
            # Handle array indices or wildcards
            if key == "*":
                # Wildcard - apply to all elements
                redacted = False
                for i, item in enumerate(obj):
                    if remaining:
                        suffix = f"_{i}" if index_suffix == "" else f"{index_suffix}_{i}"
                        redacted = redact_at_path(item, remaining, path, suffix) or redacted
                return redacted
            else:
                try:
                    idx = int(key)
                    if 0 <= idx < len(obj):
                        if remaining:
                            return redact_at_path(obj[idx], remaining, path, index_suffix)
                        else:
                            original_value = obj[idx]
                            if capture_names and path in capture_names:
                                name = capture_names[path]
                                if index_suffix:
                                    name = f"{name}{index_suffix}"
                                captures[name] = str(original_value)
                                obj[idx] = f"{{{{SECRET:{name}}}}}"
                            else:
                                obj[idx] = placeholder
                            return True
                except ValueError:
                    pass

        return False

    # Apply all paths
    for path in json_paths:
        parts = get_path_parts(path)
        redact_at_path(data, parts, path)

    return json.dumps(data, indent=2), captures


def apply_redaction(
    text: str,
    secret_values: Optional[list[str]] = None,
    json_paths: Optional[list[str]] = None,
    patterns: Optional[list[str]] = None,
    use_builtin_patterns: bool = True,
) -> str:
    """Apply all redaction methods to text.

    Args:
        text: Text to redact
        secret_values: Known secret values to redact
        json_paths: JSON paths to redact (e.g., ["$.Credentials.SecretAccessKey"])
        patterns: Custom regex patterns to redact
        use_builtin_patterns: Whether to also apply built-in secret patterns

    Returns:
        Redacted text
    """
    result = text

    # First, redact known secret values
    if secret_values:
        result = redact_secrets(result, secret_values)

    # Then, redact JSON paths
    if json_paths:
        result = redact_json_paths(result, json_paths)

    # Apply custom patterns
    if patterns:
        result = redact_patterns(result, patterns)

    # Apply built-in patterns as safety net
    if use_builtin_patterns:
        result = redact_patterns(result)

    return result


def apply_redaction_with_capture(
    text: str,
    secret_values: Optional[list[str]] = None,
    capture_config: Optional[dict[str, dict]] = None,
    patterns: Optional[list[str]] = None,
    use_builtin_patterns: bool = True,
) -> tuple[str, dict[str, str]]:
    """Apply redaction with capture support.

    Args:
        text: Text to redact
        secret_values: Known secret values to redact
        capture_config: Dict mapping JSON paths to capture specs:
                       {"$.Credentials.SecretAccessKey": {"name": "AWS_SECRET", ...}}
        patterns: Custom regex patterns to redact
        use_builtin_patterns: Whether to also apply built-in secret patterns

    Returns:
        Tuple of (redacted text, captured values dict)
    """
    result = text
    captured: dict[str, str] = {}

    # First, redact known secret values
    if secret_values:
        result = redact_secrets(result, secret_values)

    # Then, capture and redact JSON paths
    if capture_config:
        json_paths = list(capture_config.keys())
        capture_names = {path: spec["name"] for path, spec in capture_config.items()}
        result, captured = redact_json_paths_with_capture(
            result, json_paths, capture_names=capture_names
        )

    # Apply custom patterns
    if patterns:
        result = redact_patterns(result, patterns)

    # Apply built-in patterns as safety net
    if use_builtin_patterns:
        result = redact_patterns(result)

    return result, captured
