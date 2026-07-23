# story: e01s01

from collections.abc import Mapping
from typing import Any


REDACTED = "<redacted>"
SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
)


def _is_sensitive_key(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.casefold().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def redact_secrets(value: Any) -> Any:
    """Return a recursively redacted copy suitable for diagnostics."""
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _is_sensitive_key(key) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    return value
