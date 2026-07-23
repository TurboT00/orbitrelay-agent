from __future__ import annotations

import ipaddress
import json
import os
import re
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit
from pathlib import Path


PROFILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ProfileValidationError(ValueError):
    pass


class ProfileStorageError(RuntimeError):
    pass


class ProfileNotFoundError(ProfileStorageError):
    pass


class ProfileExistsError(ProfileStorageError):
    pass


class AuthKind(StrEnum):
    API_KEY = "api_key"
    EXTERNAL_FIRST_PARTY_CLI = "external_first_party_cli"
    LOCAL_NONE = "local_none"
    LOCAL_SERVICE_BEARER = "local_service_bearer"


class ProviderCapability(StrEnum):
    TOOL_CALLING = "tool_calling"
    ASSISTANT_MESSAGE_PASSTHROUGH = "assistant_message_passthrough"


REQUIRED_CAPABILITIES = frozenset(
    {
        ProviderCapability.TOOL_CALLING,
        ProviderCapability.ASSISTANT_MESSAGE_PASSTHROUGH,
    }
)


def _enum_value(enum_type, value: Any, field: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ProfileValidationError(f"Unknown {field}: {value!r}") from exc


def _validated_endpoint(value: Any, auth_kind: AuthKind) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileValidationError("base_url cannot be empty")
    base_url = value.strip()
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProfileValidationError("base_url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ProfileValidationError("base_url cannot contain credentials")
    if auth_kind is AuthKind.LOCAL_NONE and not _is_loopback(parsed.hostname):
        raise ProfileValidationError("local_none base_url must use a loopback host")
    return base_url


def _is_loopback(hostname: str) -> bool:
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


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
        if not isinstance(name, str) or not PROFILE_NAME_PATTERN.fullmatch(name):
            raise ProfileValidationError(
                "name must start with an alphanumeric character and contain only "
                "letters, numbers, dots, underscores, or hyphens (maximum 64)"
            )
        validated_auth_kind = _enum_value(AuthKind, auth_kind, "auth_kind")
        if not isinstance(model, str) or not model.strip():
            raise ProfileValidationError("model cannot be empty")
        try:
            validated_capabilities = frozenset(
                _enum_value(ProviderCapability, item, "capability")
                for item in capabilities
            )
        except TypeError as exc:
            raise ProfileValidationError("capabilities must be a list") from exc
        missing = REQUIRED_CAPABILITIES - validated_capabilities
        if missing:
            names = ", ".join(sorted(item.value for item in missing))
            raise ProfileValidationError(f"Missing required capabilities: {names}")

        return cls(
            name=name,
            base_url=_validated_endpoint(base_url, validated_auth_kind),
            model=model.strip(),
            auth_kind=validated_auth_kind,
            capabilities=validated_capabilities,
        )

    @classmethod
    def from_dict(cls, value: Any) -> ProviderProfile:
        if not isinstance(value, Mapping):
            raise ProfileValidationError("profile metadata must be an object")
        expected = {"name", "base_url", "model", "auth_kind", "capabilities"}
        unknown = set(value) - expected
        missing = expected - set(value)
        if unknown:
            raise ProfileValidationError(
                f"profile metadata contains unknown fields: {', '.join(sorted(unknown))}"
            )
        if missing:
            raise ProfileValidationError(
                f"profile metadata is missing fields: {', '.join(sorted(missing))}"
            )
        capabilities = value["capabilities"]
        if not isinstance(capabilities, list):
            raise ProfileValidationError("capabilities must be a list")
        return cls.create(
            name=value["name"],
            base_url=value["base_url"],
            model=value["model"],
            auth_kind=value["auth_kind"],
            capabilities=capabilities,
        )

    def to_dict(self) -> dict[str, Any]:
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
        }


class ProfileRepository:
    """Owns versioned, secret-free profile metadata in one per-user file."""

    VERSION = 1

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def list_profiles(self) -> tuple[ProviderProfile, ...]:
        state = self._read()
        return tuple(state["profiles"][name] for name in sorted(state["profiles"]))

    def get(self, name: str) -> ProviderProfile:
        state = self._read()
        try:
            return state["profiles"][name]
        except KeyError as exc:
            raise ProfileNotFoundError(f'Profile "{name}" does not exist') from exc

    def save(self, profile: ProviderProfile, *, replace: bool = False) -> None:
        state = self._read()
        if profile.name in state["profiles"] and not replace:
            raise ProfileExistsError(f'Profile "{profile.name}" already exists')
        state["profiles"][profile.name] = profile
        self._write(state)

    def select(self, name: str) -> None:
        state = self._read()
        if name not in state["profiles"]:
            raise ProfileNotFoundError(f'Profile "{name}" does not exist')
        state["selected"] = name
        self._write(state)

    def selected_name(self) -> str | None:
        return self._read()["selected"]

    def delete(self, name: str) -> ProviderProfile:
        state = self._read()
        try:
            profile = state["profiles"].pop(name)
        except KeyError as exc:
            raise ProfileNotFoundError(f'Profile "{name}" does not exist') from exc
        if state["selected"] == name:
            state["selected"] = None
        self._write(state)
        return profile

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"selected": None, "profiles": {}}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProfileStorageError(
                f'Profile metadata at "{self.path}" is not valid JSON'
            ) from exc
        except OSError as exc:
            raise ProfileStorageError(
                f'Could not read profile metadata at "{self.path}": {exc}'
            ) from exc

        if not isinstance(raw, dict):
            raise ProfileStorageError("Profile metadata root must be an object")
        expected = {"version", "selected", "profiles"}
        if set(raw) != expected:
            raise ProfileStorageError("Profile metadata contains invalid fields")
        if raw["version"] != self.VERSION:
            raise ProfileStorageError(
                f"Unsupported profile metadata version: {raw['version']!r}"
            )
        if not isinstance(raw["profiles"], dict):
            raise ProfileStorageError("Profile metadata profiles must be an object")

        profiles: dict[str, ProviderProfile] = {}
        try:
            for name, value in raw["profiles"].items():
                profile = ProviderProfile.from_dict(value)
                if name != profile.name:
                    raise ProfileStorageError(
                        f'Profile key "{name}" does not match embedded name'
                    )
                profiles[name] = profile
        except ProfileValidationError as exc:
            raise ProfileStorageError(f"Stored profile is invalid: {exc}") from exc

        selected = raw["selected"]
        if selected is not None and not isinstance(selected, str):
            raise ProfileStorageError("Selected profile must be a string or null")
        if selected is not None and selected not in profiles:
            raise ProfileStorageError(
                f'Selected profile "{selected}" does not exist in metadata'
            )
        return {"selected": selected, "profiles": profiles}

    def _write(self, state: Mapping[str, Any]) -> None:
        raw = {
            "version": self.VERSION,
            "selected": state["selected"],
            "profiles": {
                name: profile.to_dict()
                for name, profile in sorted(state["profiles"].items())
            },
        }
        temporary_path: str | None = None
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                delete=False,
            ) as temporary:
                temporary_path = temporary.name
                os.chmod(temporary.name, 0o600)
                json.dump(raw, temporary, indent=2, sort_keys=True)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        except OSError as exc:
            raise ProfileStorageError(
                f'Could not write profile metadata at "{self.path}": {exc}'
            ) from exc
        finally:
            if temporary_path is not None:
                try:
                    Path(temporary_path).unlink(missing_ok=True)
                except OSError:
                    pass
