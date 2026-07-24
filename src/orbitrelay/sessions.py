# story: e04s03
# story: e04s04

from __future__ import annotations

import json
import os
import re
import stat
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .events import EventCollector, RunEvent
from .redaction import redact_secrets


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
METADATA_NAME = "metadata.json"
MESSAGES_NAME = "messages.jsonl"
EVENTS_NAME = "events.jsonl"


class SessionError(RuntimeError):
    """Session storage or resume failure."""


class SessionNotFoundError(SessionError):
    pass


class SessionCorruptionError(SessionError):
    pass


def default_sessions_root(environ: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    configured_home = values.get("ORBITRELAY_HOME", "").strip()
    application_home = (
        Path(configured_home).expanduser()
        if configured_home
        else Path.home() / ".orbitrelay"
    )
    return application_home / "sessions"


def _reject_symlink(path: Path) -> None:
    if path.is_symlink():
        raise SessionError(f'Session storage cannot use symbolic link "{path}"')


def _reject_insecure_permissions(path: Path) -> None:
    if not path.exists() or not hasattr(os, "getuid"):
        return
    metadata = path.stat(follow_symlinks=False)
    if metadata.st_uid != os.getuid():
        raise SessionError(f'Session storage is not owned by this user: "{path}"')
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise SessionError(f'Session storage is group/world writable: "{path}"')


def _validate_path(path: Path) -> None:
    _reject_symlink(path)
    if path.exists():
        _reject_insecure_permissions(path)


def _validate_session_id(session_id: str) -> str:
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise SessionError(
            "session id must start with an alphanumeric character and contain only "
            "letters, numbers, dots, underscores, or hyphens (maximum 64)"
        )
    return session_id


def _secure_mkdir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    _validate_path(path)
    if hasattr(os, "chmod"):
        os.chmod(path, 0o700)


def _write_text_secure(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if hasattr(os, "chmod"):
            os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _append_text_secure(path: Path, content: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if hasattr(os, "chmod"):
            os.chmod(path, 0o600)
    finally:
        pass


@dataclass(frozen=True)
class SessionMetadata:
    id: str
    created_at: float
    updated_at: float
    workspace: str | None = None
    model: str | None = None
    title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "workspace": self.workspace,
            "model": self.model,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, value: object) -> SessionMetadata:
        if not isinstance(value, dict):
            raise SessionCorruptionError("session metadata must be an object")
        try:
            return cls(
                id=_validate_session_id(str(value["id"])),
                created_at=float(value["created_at"]),
                updated_at=float(value["updated_at"]),
                workspace=value.get("workspace")
                if isinstance(value.get("workspace"), str) or value.get("workspace") is None
                else None,
                model=value.get("model")
                if isinstance(value.get("model"), str) or value.get("model") is None
                else None,
                title=value.get("title")
                if isinstance(value.get("title"), str) or value.get("title") is None
                else None,
            )
        except (KeyError, TypeError, ValueError, SessionError) as exc:
            raise SessionCorruptionError("session metadata is invalid") from exc


class SessionStore:
    def __init__(
        self,
        root: Path | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.root = (root or default_sessions_root(environ)).expanduser()
        self._clock = clock

    def ensure_root(self) -> Path:
        _secure_mkdir(self.root)
        _validate_path(self.root)
        return self.root

    def _session_dir(self, session_id: str) -> Path:
        safe_id = _validate_session_id(session_id)
        path = (self.root / safe_id).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError as exc:
            raise SessionError("session path escapes sessions root") from exc
        return path

    def create(
        self,
        *,
        session_id: str | None = None,
        workspace: str | None = None,
        model: str | None = None,
        title: str | None = None,
    ) -> SessionMetadata:
        self.ensure_root()
        sid = _validate_session_id(session_id or uuid.uuid4().hex)
        directory = self._session_dir(sid)
        if directory.exists():
            raise SessionError(f'Session "{sid}" already exists')
        _secure_mkdir(directory)
        now = float(self._clock())
        metadata = SessionMetadata(
            id=sid,
            created_at=now,
            updated_at=now,
            workspace=workspace,
            model=model,
            title=title,
        )
        self._write_metadata(directory, metadata)
        # touch empty append files with secure perms
        for name in (MESSAGES_NAME, EVENTS_NAME):
            path = directory / name
            _write_text_secure(path, "")
        return metadata

    def get_metadata(self, session_id: str) -> SessionMetadata:
        directory = self._require_session_dir(session_id)
        return self._read_metadata(directory)

    def list_sessions(self) -> tuple[SessionMetadata, ...]:
        if not self.root.exists():
            return ()
        self.ensure_root()
        sessions: list[SessionMetadata] = []
        for child in sorted(self.root.iterdir()):
            if not child.is_dir() or child.is_symlink():
                continue
            try:
                sessions.append(self._read_metadata(child))
            except SessionError:
                continue
        return tuple(sessions)

    def delete(self, session_id: str) -> None:
        directory = self._require_session_dir(session_id)
        for child in directory.iterdir():
            if child.is_file() and not child.is_symlink():
                child.unlink()
        directory.rmdir()

    def delete_all(self) -> int:
        count = 0
        for metadata in self.list_sessions():
            self.delete(metadata.id)
            count += 1
        return count

    def load_messages(self, session_id: str) -> list[dict[str, Any]]:
        directory = self._require_session_dir(session_id)
        path = directory / MESSAGES_NAME
        _validate_path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SessionError(f'Could not read session messages: "{path}"') from exc
        messages: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SessionCorruptionError(
                    f"session messages line {line_number} is not valid JSON"
                ) from exc
            if not isinstance(payload, dict):
                raise SessionCorruptionError(
                    f"session messages line {line_number} must be an object"
                )
            messages.append(payload)
        return messages

    def replace_messages(
        self, session_id: str, messages: Sequence[Mapping[str, Any]]
    ) -> None:
        directory = self._require_session_dir(session_id)
        redacted = [redact_secrets(dict(message)) for message in messages]
        body = "".join(
            json.dumps(message, sort_keys=True, separators=(",", ":")) + "\n"
            for message in redacted
            if isinstance(message, dict)
        )
        _write_text_secure(directory / MESSAGES_NAME, body)
        metadata = self._read_metadata(directory)
        updated = SessionMetadata(
            id=metadata.id,
            created_at=metadata.created_at,
            updated_at=float(self._clock()),
            workspace=metadata.workspace,
            model=metadata.model,
            title=metadata.title,
        )
        self._write_metadata(directory, updated)

    def append_events(self, session_id: str, events: Sequence[RunEvent]) -> None:
        directory = self._require_session_dir(session_id)
        if not events:
            return
        body = "".join(
            json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
            for event in events
        )
        _append_text_secure(directory / EVENTS_NAME, body)

    def bind_collector(
        self, session_id: str, collector: EventCollector
    ) -> EventCollector:
        """Wrap collector emissions so new events are appended durably."""
        original_emit = collector.emit
        store = self
        start = len(collector.events)

        def emit(event_type, **data):  # type: ignore[no-untyped-def]
            event = original_emit(event_type, **data)
            # append only the newly emitted event
            store.append_events(session_id, (event,))
            return event

        collector.emit = emit  # type: ignore[method-assign]
        del start
        return collector

    def _require_session_dir(self, session_id: str) -> Path:
        self.ensure_root()
        directory = self._session_dir(session_id)
        if not directory.exists() or not directory.is_dir():
            raise SessionNotFoundError(f'Session "{session_id}" was not found')
        _validate_path(directory)
        return directory

    def _write_metadata(self, directory: Path, metadata: SessionMetadata) -> None:
        _write_text_secure(
            directory / METADATA_NAME,
            json.dumps(metadata.to_dict(), indent=2, sort_keys=True) + "\n",
        )

    def _read_metadata(self, directory: Path) -> SessionMetadata:
        path = directory / METADATA_NAME
        _validate_path(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SessionCorruptionError(
                f'session metadata missing at "{path}"'
            ) from exc
        except json.JSONDecodeError as exc:
            raise SessionCorruptionError(
                f'session metadata at "{path}" is not valid JSON'
            ) from exc
        except OSError as exc:
            raise SessionError(f'Could not read session metadata at "{path}"') from exc
        return SessionMetadata.from_dict(payload)
