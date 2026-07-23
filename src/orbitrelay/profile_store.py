from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .profiles import ProfileValidationError, ProviderProfile


class ProfileStorageError(RuntimeError):
    pass


class ProfileNotFoundError(ProfileStorageError):
    pass


class ProfileExistsError(ProfileStorageError):
    pass


def default_profile_path(environ: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    configured_home = values.get("ORBITRELAY_HOME", "").strip()
    application_home = (
        Path(configured_home).expanduser()
        if configured_home
        else Path.home() / ".orbitrelay"
    )
    return application_home / "profiles.json"


@dataclass
class _ProfileState:
    selected: str | None
    profiles: dict[str, ProviderProfile]


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileStorageError(
            f'Profile metadata at "{path}" is not valid JSON'
        ) from exc
    except OSError as exc:
        raise ProfileStorageError(
            f'Could not read profile metadata at "{path}": {exc}'
        ) from exc


def _decode_profiles(value: object) -> dict[str, ProviderProfile]:
    if not isinstance(value, dict) or not all(
        isinstance(name, str) for name in value
    ):
        raise ProfileStorageError("Profile metadata profiles must be an object")
    profiles: dict[str, ProviderProfile] = {}
    try:
        for name, metadata in value.items():
            profile = ProviderProfile.from_dict(metadata)
            if name != profile.name:
                raise ProfileStorageError(
                    f'Profile key "{name}" does not match embedded name'
                )
            profiles[cast(str, name)] = profile
    except ProfileValidationError as exc:
        raise ProfileStorageError(f"Stored profile is invalid: {exc}") from exc
    return profiles


def _selected_profile(value: object, profiles: dict[str, ProviderProfile]) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ProfileStorageError("Selected profile must be a string or null")
    if value is not None and value not in profiles:
        raise ProfileStorageError(f'Selected profile "{value}" does not exist in metadata')
    return value


def _decode_state(raw: object, version: int) -> _ProfileState:
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise ProfileStorageError("Profile metadata root must be an object")
    record = cast(dict[str, object], raw)
    if set(record) != {"version", "selected", "profiles"}:
        raise ProfileStorageError("Profile metadata contains invalid fields")
    if record["version"] != version:
        raise ProfileStorageError(
            f"Unsupported profile metadata version: {record['version']!r}"
        )
    profiles = _decode_profiles(record["profiles"])
    return _ProfileState(_selected_profile(record["selected"], profiles), profiles)


def _encoded_state(state: _ProfileState, version: int) -> dict[str, object]:
    return {
        "version": version,
        "selected": state.selected,
        "profiles": {
            name: profile.to_dict()
            for name, profile in sorted(state.profiles.items())
        },
    }


def _write_temporary(path: Path, value: dict[str, object]) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary:
        try:
            os.chmod(temporary.name, 0o600)
            json.dump(value, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            return temporary.name
        except OSError:
            Path(temporary.name).unlink(missing_ok=True)
            raise


def _write_json_atomically(path: Path, value: dict[str, object]) -> None:
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary_path = _write_temporary(path, value)
    except OSError as exc:
        raise ProfileStorageError(
            f'Could not write profile metadata at "{path}": {exc}'
        ) from exc
    try:
        os.replace(temporary_path, path)
    except OSError as exc:
        raise ProfileStorageError(
            f'Could not write profile metadata at "{path}": {exc}'
        ) from exc
    finally:
        try:
            Path(temporary_path).unlink(missing_ok=True)
        except OSError:
            pass


class ProfileRepository:
    """Owns versioned, secret-free profile metadata in one per-user file."""

    VERSION = 1

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def list_profiles(self) -> tuple[ProviderProfile, ...]:
        state = self._read()
        return tuple(state.profiles[name] for name in sorted(state.profiles))

    def get(self, name: str) -> ProviderProfile:
        try:
            return self._read().profiles[name]
        except KeyError as exc:
            raise ProfileNotFoundError(f'Profile "{name}" does not exist') from exc

    def save(self, profile: ProviderProfile, *, replace: bool = False) -> None:
        state = self._read()
        if profile.name in state.profiles and not replace:
            raise ProfileExistsError(f'Profile "{profile.name}" already exists')
        state.profiles[profile.name] = profile
        self._write(state)

    def select(self, name: str) -> None:
        state = self._read()
        if name not in state.profiles:
            raise ProfileNotFoundError(f'Profile "{name}" does not exist')
        state.selected = name
        self._write(state)

    def selected_name(self) -> str | None:
        return self._read().selected

    def delete(self, name: str) -> ProviderProfile:
        state = self._read()
        try:
            profile = state.profiles.pop(name)
        except KeyError as exc:
            raise ProfileNotFoundError(f'Profile "{name}" does not exist') from exc
        state.selected = None if state.selected == name else state.selected
        self._write(state)
        return profile

    def _read(self) -> _ProfileState:
        if not self.path.exists():
            return _ProfileState(None, {})
        return _decode_state(_load_json(self.path), self.VERSION)

    def _write(self, state: _ProfileState) -> None:
        _write_json_atomically(self.path, _encoded_state(state, self.VERSION))
