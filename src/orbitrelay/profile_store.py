# story: e01s01

from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TextIO, cast

import fcntl

from .profiles import ProfileValidationError, ProviderProfile


class ProfileStorageError(RuntimeError):
    pass


class ProfileNotFoundError(ProfileStorageError):
    pass


class ProfileExistsError(ProfileStorageError):
    pass


_PROCESS_TRANSACTION_LOCK = threading.RLock()


def default_profile_path(environ: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    configured_home = values.get("ORBITRELAY_HOME", "").strip()
    application_home = (
        Path(configured_home).expanduser()
        if configured_home
        else Path.home() / ".orbitrelay"
    )
    return application_home / "profiles.json"


def _reject_symlink(path: Path) -> None:
    if path.is_symlink():
        raise ProfileStorageError(f'Profile storage cannot use symbolic link "{path}"')


def _reject_insecure_permissions(path: Path) -> None:
    if not path.exists() or not hasattr(os, "getuid"):
        return
    metadata = path.stat(follow_symlinks=False)
    if metadata.st_uid != os.getuid():
        raise ProfileStorageError(f'Profile storage is not owned by this user: "{path}"')
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ProfileStorageError(f'Profile storage is group/world writable: "{path}"')


def _validate_storage_path(path: Path) -> None:
    _reject_symlink(path.parent)
    _reject_symlink(path)
    _reject_insecure_permissions(path.parent)
    _reject_insecure_permissions(path)


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
        self._lock_depth = 0
        self._lock_stream: TextIO | None = None

    def credential_key(self, profile_name: str) -> str:
        _validate_storage_path(self.path)
        namespace = sha256(
            str(self.path.resolve(strict=False)).encode("utf-8")
        ).hexdigest()[:16]
        return f"{namespace}:{profile_name}"

    def _open_lock(self) -> TextIO:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _validate_storage_path(self.path)
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        _reject_symlink(lock_path)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(lock_path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        return os.fdopen(descriptor, "a+", encoding="utf-8")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._lock_depth:
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
            return
        with _PROCESS_TRANSACTION_LOCK:
            stream = self._open_lock()
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                self._lock_stream, self._lock_depth = stream, 1
                yield
            finally:
                self._lock_depth, self._lock_stream = 0, None
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                stream.close()

    def list_profiles(self) -> tuple[ProviderProfile, ...]:
        state = self._read()
        return tuple(state.profiles[name] for name in sorted(state.profiles))

    def get(self, name: str) -> ProviderProfile:
        try:
            return self._read().profiles[name]
        except KeyError as exc:
            raise ProfileNotFoundError(f'Profile "{name}" does not exist') from exc

    def save(self, profile: ProviderProfile, *, replace: bool = False) -> None:
        with self.transaction():
            state = self._read()
            if profile.name in state.profiles and not replace:
                raise ProfileExistsError(f'Profile "{profile.name}" already exists')
            state.profiles[profile.name] = profile
            self._write(state)

    def select(self, name: str) -> None:
        with self.transaction():
            state = self._read()
            if name not in state.profiles:
                raise ProfileNotFoundError(f'Profile "{name}" does not exist')
            state.selected = name
            self._write(state)

    def selected_name(self) -> str | None:
        return self._read().selected

    def delete(self, name: str) -> ProviderProfile:
        with self.transaction():
            state = self._read()
            try:
                profile = state.profiles.pop(name)
            except KeyError as exc:
                raise ProfileNotFoundError(f'Profile "{name}" does not exist') from exc
            state.selected = None if state.selected == name else state.selected
            self._write(state)
            return profile

    def _read(self) -> _ProfileState:
        _validate_storage_path(self.path)
        if not self.path.exists():
            return _ProfileState(None, {})
        return _decode_state(_load_json(self.path), self.VERSION)

    def _write(self, state: _ProfileState) -> None:
        _write_json_atomically(self.path, _encoded_state(state, self.VERSION))
