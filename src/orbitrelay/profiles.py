# story: e01s01

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar, cast
from urllib.parse import urlsplit


PROFILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ProfileValidationError(ValueError):
    pass


class AuthKind(StrEnum):
    API_KEY = "api_key"
    EXTERNAL_FIRST_PARTY_CLI = "external_first_party_cli"
    LOCAL_NONE = "local_none"
    LOCAL_SERVICE_BEARER = "local_service_bearer"
    SUBSCRIPTION_OAUTH = "subscription_oauth"


class ProviderCapability(StrEnum):
    TOOL_CALLING = "tool_calling"
    ASSISTANT_MESSAGE_PASSTHROUGH = "assistant_message_passthrough"


REQUIRED_CAPABILITIES = frozenset(
    {
        ProviderCapability.TOOL_CALLING,
        ProviderCapability.ASSISTANT_MESSAGE_PASSTHROUGH,
    }
)
EnumValue = TypeVar("EnumValue", bound=StrEnum)


def _enum_value(
    enum_type: type[EnumValue], value: object, field: str
) -> EnumValue:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ProfileValidationError(f"Unknown {field}: {value!r}") from exc


def _is_loopback(hostname: str) -> bool:
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _reject_unsafe_transport(
    scheme: str, hostname: str, auth_kind: AuthKind
) -> None:
    is_loopback = _is_loopback(hostname)
    if auth_kind is AuthKind.LOCAL_NONE and not is_loopback:
        raise ProfileValidationError("local_none base_url must use a loopback host")
    authenticated = auth_kind is not AuthKind.LOCAL_NONE
    if authenticated and scheme != "https" and not is_loopback:
        raise ProfileValidationError(
            "authenticated profiles require HTTPS or loopback"
        )


def _validated_endpoint(value: object, auth_kind: AuthKind) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileValidationError("base_url cannot be empty")
    base_url = value.strip()
    if any(character.isspace() or ord(character) < 32 for character in base_url):
        raise ProfileValidationError("base_url cannot contain whitespace or controls")
    try:
        parsed = urlsplit(base_url)
        parsed.port
    except ValueError as exc:
        raise ProfileValidationError("base_url port or authority is invalid") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProfileValidationError("base_url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ProfileValidationError("base_url cannot contain credentials")
    if parsed.query or parsed.fragment:
        raise ProfileValidationError("base_url cannot contain a query or fragment")
    _reject_unsafe_transport(parsed.scheme, parsed.hostname, auth_kind)
    return base_url


def _validated_name(value: object) -> str:
    if isinstance(value, str) and PROFILE_NAME_PATTERN.fullmatch(value):
        return value
    raise ProfileValidationError(
        "name must start with an alphanumeric character and contain only "
        "letters, numbers, dots, underscores, or hyphens (maximum 64)"
    )


def _validated_model(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ProfileValidationError("model cannot be empty")


def _validated_capabilities(
    values: Iterable[ProviderCapability | str],
) -> frozenset[ProviderCapability]:
    try:
        capabilities = frozenset(
            _enum_value(ProviderCapability, item, "capability") for item in values
        )
    except TypeError as exc:
        raise ProfileValidationError("capabilities must be a list") from exc
    missing = REQUIRED_CAPABILITIES - capabilities
    if missing:
        names = ", ".join(sorted(item.value for item in missing))
        raise ProfileValidationError(f"Missing required capabilities: {names}")
    return capabilities


def _metadata_fields(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise ProfileValidationError("profile metadata must be an object")
    fields = cast(Mapping[str, object], value)
    expected = {"name", "base_url", "model", "auth_kind", "capabilities"}
    unknown, missing = set(fields) - expected, expected - set(fields)
    if unknown:
        raise ProfileValidationError(
            f"profile metadata contains unknown fields: {', '.join(sorted(unknown))}"
        )
    if missing:
        raise ProfileValidationError(
            f"profile metadata is missing fields: {', '.join(sorted(missing))}"
        )
    return fields


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    base_url: str
    model: str
    auth_kind: AuthKind
    capabilities: frozenset[ProviderCapability]

    @classmethod
    def create(
        cls,
        *,
        name: str,
        base_url: str,
        model: str,
        auth_kind: AuthKind | str,
        capabilities: Iterable[ProviderCapability | str],
    ) -> ProviderProfile:
        validated_auth = _enum_value(AuthKind, auth_kind, "auth_kind")
        return cls(
            name=_validated_name(name),
            base_url=_validated_endpoint(base_url, validated_auth),
            model=_validated_model(model),
            auth_kind=validated_auth,
            capabilities=_validated_capabilities(capabilities),
        )

    @classmethod
    def from_dict(cls, value: object) -> ProviderProfile:
        fields = _metadata_fields(value)
        capabilities = fields["capabilities"]
        if not isinstance(capabilities, list) or not all(
            isinstance(item, str) for item in capabilities
        ):
            raise ProfileValidationError("capabilities must be a list")
        capability_values = cast(list[str], capabilities)
        return cls.create(
            name=cast(str, fields["name"]),
            base_url=cast(str, fields["base_url"]),
            model=cast(str, fields["model"]),
            auth_kind=cast(str, fields["auth_kind"]),
            capabilities=capability_values,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "model": self.model,
            "auth_kind": self.auth_kind.value,
            "capabilities": sorted(item.value for item in self.capabilities),
        }

    @property
    def requires_secret(self) -> bool:
        return self.auth_kind in {
            AuthKind.API_KEY,
            AuthKind.LOCAL_SERVICE_BEARER,
            AuthKind.SUBSCRIPTION_OAUTH,
        }
