# story: e04s03
# story: e04s04

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .context_budget import (
    DEFAULT_MAX_REPLAY_CHARS,
    DEFAULT_MAX_SEGMENT_CHARS,
    HISTORY_FORMAT_VERSION,
    is_replay_safe,
    pack_segments,
    replay_safe_prefix,
    select_replay_messages,
    strip_system_messages,
)
from .events import EventCollector, RunEvent
from .redaction import redact_secrets

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
METADATA_NAME = "metadata.json"
MESSAGES_NAME = "messages.jsonl"
EVENTS_NAME = "events.jsonl"
MESSAGES_DIR_NAME = "messages"
EVENTS_DIR_NAME = "events"
LOCK_NAME = "session.lock"
ACTIVE_NAME = "active.json"


class SessionError(RuntimeError):
    """Session storage or resume failure."""


class SessionNotFoundError(SessionError):
    pass


class SessionCorruptionError(SessionError):
    pass


class SessionBusyError(SessionError):
    """Another process already owns the session lease."""


class SessionHealth(StrEnum):
    OK = "ok"
    CORRUPT = "corrupt"
    INACCESSIBLE = "inaccessible"


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """Secret-free inspection view for valid or corrupt sessions."""

    id: str
    health: SessionHealth
    updated_at: float | None = None
    model: str | None = None
    workspace: str | None = None
    sensitive: bool = False
    diagnostic: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "state": self.health.value,
        }
        if self.updated_at is not None:
            payload["updated_at"] = self.updated_at
        if self.model is not None:
            payload["model"] = self.model
        if self.workspace is not None:
            payload["workspace"] = self.workspace
        if self.sensitive:
            payload["sensitive"] = True
        if self.diagnostic:
            payload["diagnostic"] = self.diagnostic
        return payload


@dataclass(frozen=True, slots=True)
class DeleteAllResult:
    deleted: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]

    @property
    def complete(self) -> bool:
        return not self.failed

    @property
    def deleted_count(self) -> int:
        return len(self.deleted)


def _history_format_value(value: object) -> int:
    if isinstance(value, bool):
        raise SessionCorruptionError("history_format is invalid")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    if value is None:
        return 1
    raise SessionCorruptionError("history_format is invalid")


def _safe_diagnostic(exc: BaseException) -> str:
    """Return a short secret-free reason string for CLI/inspection."""
    text = str(exc).strip() or exc.__class__.__name__
    first = text.splitlines()[0].strip()
    if len(first) > 200:
        first = first[:197] + "..."
    return first


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
    directory = path.parent
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(directory),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if hasattr(os, "chmod"):
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        if hasattr(os, "chmod"):
            os.chmod(path, 0o600)
        _fsync_directory(directory)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _fsync_directory(directory: Path) -> None:
    try:
        dir_fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


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
    sensitive: bool = False
    sensitive_authority: tuple[str, ...] = ()
    history_format: int = 1

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "workspace": self.workspace,
            "model": self.model,
            "title": self.title,
            "sensitive": self.sensitive,
            "history_format": self.history_format,
        }
        if self.sensitive_authority:
            payload["sensitive_authority"] = list(self.sensitive_authority)
        return payload

    @classmethod
    def from_dict(cls, value: object) -> SessionMetadata:
        if not isinstance(value, dict):
            raise SessionCorruptionError("session metadata must be an object")
        try:
            authority_raw = value.get("sensitive_authority", ())
            if authority_raw in (None, (), []):
                authority: tuple[str, ...] = ()
            elif isinstance(authority_raw, (list, tuple)) and all(
                isinstance(item, str) for item in authority_raw
            ):
                authority = tuple(authority_raw)
            else:
                raise SessionCorruptionError("sensitive_authority must be a string list")
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
                sensitive=bool(value.get("sensitive", False)),
                sensitive_authority=authority,
                history_format=_history_format_value(value.get("history_format", 1)),
            )
        except (KeyError, TypeError, ValueError, SessionError) as exc:
            raise SessionCorruptionError("session metadata is invalid") from exc



class SessionLease:
    """Kernel-backed exclusive ownership for one session directory."""

    def __init__(self, session_id: str, lock_path: Path, descriptor: int) -> None:
        self.session_id = session_id
        self._lock_path = lock_path
        self._descriptor = descriptor
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        try:
            active = self._lock_path.parent / ACTIVE_NAME
            if active.exists() and not active.is_symlink():
                active.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        finally:
            os.close(self._descriptor)
            self._released = True

    def __enter__(self) -> SessionLease:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


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

    def acquire_lease(
        self,
        session_id: str,
        *,
        wait_seconds: float | None = None,
    ) -> SessionLease:
        """Acquire exclusive ownership before history load or mutation."""
        directory = self._require_session_dir(session_id)
        lock_path = directory / LOCK_NAME
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(lock_path, flags, 0o600)
        deadline = (
            None
            if wait_seconds is None
            else (float(self._clock()) + max(0.0, float(wait_seconds)))
        )
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if wait_seconds is None:
                    os.close(descriptor)
                    raise SessionBusyError(
                        f'Session "{session_id}" is already in use by another process'
                    ) from exc
                if deadline is not None and float(self._clock()) >= deadline:
                    os.close(descriptor)
                    raise SessionBusyError(
                        f'Session "{session_id}" remained busy until the wait deadline'
                    ) from exc
                time.sleep(0.05)
            except OSError as exc:
                os.close(descriptor)
                raise SessionError(
                    f'Could not lock session "{session_id}": {exc}'
                ) from exc
        if hasattr(os, "chmod"):
            os.chmod(lock_path, 0o600)
        with suppress(OSError):
            _write_text_secure(
                directory / ACTIVE_NAME,
                json.dumps({"active": True, "session_id": session_id}, sort_keys=True)
                + "\n",
            )
        return SessionLease(session_id, lock_path, descriptor)

    def is_session_active(self, session_id: str) -> bool:
        """Return True when another process currently holds the session lease."""
        try:
            directory = self._require_session_dir(session_id)
        except SessionNotFoundError:
            return False
        lock_path = directory / LOCK_NAME
        if not lock_path.exists():
            return False
        flags = os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(lock_path, flags, 0o600)
        except OSError:
            return False
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        except OSError:
            return False
        else:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return False
        finally:
            os.close(descriptor)


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
            history_format=HISTORY_FORMAT_VERSION,
        )
        self._write_metadata(directory, metadata)
        _secure_mkdir(directory / MESSAGES_DIR_NAME)
        _secure_mkdir(directory / EVENTS_DIR_NAME)
        _write_text_secure(directory / MESSAGES_DIR_NAME / "000001.jsonl", "")
        _write_text_secure(directory / EVENTS_DIR_NAME / "000001.jsonl", "")
        return metadata


    def mark_sensitive(
        self,
        session_id: str,
        authority: Sequence[str],
    ) -> SessionMetadata:
        """Mark a session as sensitive with secret-free authority descriptors."""
        directory = self._require_session_dir(session_id)
        metadata = self._read_metadata(directory)
        cleaned = tuple(
            sorted({item.strip() for item in authority if isinstance(item, str) and item.strip()})
        )
        if not cleaned:
            raise SessionError("sensitive authority descriptors cannot be empty")
        updated = SessionMetadata(
            id=metadata.id,
            created_at=metadata.created_at,
            updated_at=float(self._clock()),
            workspace=metadata.workspace,
            model=metadata.model,
            title=metadata.title,
            sensitive=True,
            sensitive_authority=cleaned,
            history_format=metadata.history_format,
        )
        self._write_metadata(directory, updated)
        return updated

    def require_sensitive_resume_authority(
        self,
        session_id: str,
        *,
        covers: Callable[[str], bool],
    ) -> None:
        """Fail closed when a sensitive session resumes without renewed authority."""
        metadata = self.get_metadata(session_id)
        if not metadata.sensitive:
            return
        missing = [
            descriptor
            for descriptor in metadata.sensitive_authority
            if not covers(descriptor)
        ]
        if missing:
            raise SessionError(
                f'Session "{session_id}" contains sensitive history; renew matching '
                "--allow-sensitive-read/--allow-sensitive-subtree authority before resume"
            )

    def get_metadata(self, session_id: str) -> SessionMetadata:
        directory = self._require_session_dir(session_id)
        return self._read_metadata(directory)

    def inspect_session(self, session_id: str) -> SessionSummary:
        """Return secret-free health for one session without loading history content."""
        try:
            directory = self._session_dir(session_id)
        except SessionError as exc:
            return SessionSummary(
                id=str(session_id),
                health=SessionHealth.INACCESSIBLE,
                diagnostic=_safe_diagnostic(exc),
            )
        if not directory.exists():
            raise SessionNotFoundError(f'Session "{session_id}" does not exist')
        return self._summarize_directory(directory)

    def list_sessions(self) -> tuple[SessionSummary, ...]:
        """List all session directories, including corrupt ones (never silent omit)."""
        if not self.root.exists():
            return ()
        self.ensure_root()
        summaries: list[SessionSummary] = []
        for child in sorted(self.root.iterdir()):
            if child.is_symlink():
                summaries.append(
                    SessionSummary(
                        id=child.name,
                        health=SessionHealth.INACCESSIBLE,
                        diagnostic="session path is a symbolic link",
                    )
                )
                continue
            if not child.is_dir():
                continue
            summaries.append(self._summarize_directory(child))
        return tuple(summaries)

    def _summarize_directory(self, directory: Path) -> SessionSummary:
        name = directory.name
        try:
            _validate_session_id(name)
        except SessionError:
            return SessionSummary(
                id=name,
                health=SessionHealth.INACCESSIBLE,
                diagnostic="unsafe session id",
            )
        try:
            _validate_path(directory)
        except SessionError as exc:
            return SessionSummary(
                id=name,
                health=SessionHealth.INACCESSIBLE,
                diagnostic=_safe_diagnostic(exc),
            )
        try:
            metadata = self._read_metadata(directory)
        except SessionCorruptionError as exc:
            return SessionSummary(
                id=name,
                health=SessionHealth.CORRUPT,
                diagnostic=_safe_diagnostic(exc) or "invalid metadata",
            )
        except SessionNotFoundError:
            return SessionSummary(
                id=name,
                health=SessionHealth.INACCESSIBLE,
                diagnostic="session metadata is missing",
            )
        except SessionError as exc:
            return SessionSummary(
                id=name,
                health=SessionHealth.INACCESSIBLE,
                diagnostic=_safe_diagnostic(exc),
            )
        try:
            self._validate_messages_file(directory / MESSAGES_NAME)
        except SessionCorruptionError as exc:
            return SessionSummary(
                id=metadata.id,
                health=SessionHealth.CORRUPT,
                updated_at=metadata.updated_at,
                model=metadata.model,
                workspace=metadata.workspace,
                sensitive=metadata.sensitive,
                diagnostic=_safe_diagnostic(exc) or "invalid messages",
            )
        except SessionError as exc:
            return SessionSummary(
                id=metadata.id,
                health=SessionHealth.INACCESSIBLE,
                updated_at=metadata.updated_at,
                model=metadata.model,
                workspace=metadata.workspace,
                sensitive=metadata.sensitive,
                diagnostic=_safe_diagnostic(exc),
            )
        return SessionSummary(
            id=metadata.id,
            health=SessionHealth.OK,
            updated_at=metadata.updated_at,
            model=metadata.model,
            workspace=metadata.workspace,
            sensitive=metadata.sensitive,
        )

    def _validate_messages_file(self, path: Path) -> None:
        """Fail closed on truncated/malformed JSONL without retaining payloads."""
        directory = path.parent
        segmented = directory / MESSAGES_DIR_NAME
        if segmented.exists() and segmented.is_dir() and not segmented.is_symlink():
            self._read_jsonl_segments(segmented, kind="messages")
            return
        if not path.exists():
            # New sessions may only have segmented history.
            if (directory / MESSAGES_DIR_NAME).exists():
                self._read_jsonl_segments(directory / MESSAGES_DIR_NAME, kind="messages")
            return
        self._read_jsonl_file(path, label="messages")

    def delete(self, session_id: str) -> None:
        """Delete one inactive session directory. Never repairs content."""
        if self.is_session_active(session_id):
            raise SessionBusyError(
                f'Session "{session_id}" is already in use by another process'
            )
        lease = self.acquire_lease(session_id)
        try:
            directory = self._require_session_dir(session_id)
            for child in list(directory.iterdir()):
                if (
                    child.is_file()
                    and not child.is_symlink()
                    and child.name != LOCK_NAME
                ):
                    child.unlink(missing_ok=True)
        finally:
            lease.release()
        directory = self._session_dir(session_id)
        if directory.exists():
            for child in list(directory.iterdir()):
                if child.is_symlink():
                    continue
                if child.is_file():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    for nested in list(child.iterdir()):
                        if nested.is_file() and not nested.is_symlink():
                            nested.unlink(missing_ok=True)
                    with suppress(OSError):
                        child.rmdir()
            directory.rmdir()

    def delete_all(self) -> DeleteAllResult:
        """Delete every listed session; report each failure without hiding remains."""
        deleted: list[str] = []
        failed: list[tuple[str, str]] = []
        for summary in self.list_sessions():
            try:
                self.delete(summary.id)
            except SessionError as exc:
                failed.append((summary.id, _safe_diagnostic(exc)))
            else:
                deleted.append(summary.id)
        return DeleteAllResult(deleted=tuple(deleted), failed=tuple(failed))

    def load_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Load full durable history (all segments). Prefer load_replay_messages for resume."""
        directory = self._require_session_dir(session_id)
        self._ensure_history_migratable(directory)
        messages = self._read_message_segments(directory)
        return replay_safe_prefix(messages)

    def load_replay_messages(
        self,
        session_id: str,
        *,
        max_chars: int = DEFAULT_MAX_REPLAY_CHARS,
    ) -> list[dict[str, Any]]:
        """Load newest complete groups within the resume-memory bound.

        System messages are omitted; callers inject current instructions.
        """
        directory = self._require_session_dir(session_id)
        self._ensure_history_migratable(directory)
        messages = self._read_message_segments(directory)
        safe = replay_safe_prefix(messages)
        return select_replay_messages(safe, max_chars=max_chars)

    def replace_messages(
        self, session_id: str, messages: Sequence[Mapping[str, Any]]
    ) -> None:
        self.commit_checkpoint(session_id, messages)

    def commit_checkpoint(
        self,
        session_id: str,
        messages: Sequence[Any],
        *,
        events: Sequence[RunEvent] | None = None,
        max_segment_chars: int = DEFAULT_MAX_SEGMENT_CHARS,
    ) -> None:
        """Persist one complete replay-safe generation into bounded segments."""
        directory = self._require_session_dir(session_id)
        normalized: list[Any] = []
        for message in messages:
            if isinstance(message, Mapping):
                normalized.append(dict(message))
            else:
                normalized.append(message)
        if not is_replay_safe(normalized):
            raise SessionError(
                f'Session "{session_id}" checkpoint refused: '
                "incomplete tool-call/result group"
            )
        durable = strip_system_messages(normalized)
        redacted = [
            redact_secrets(dict(message)) if isinstance(message, Mapping) else message
            for message in durable
        ]
        self._write_message_segments(
            directory, redacted, max_segment_chars=max_segment_chars
        )
        if events is not None:
            event_payloads = [event.to_dict() for event in events]
            self._write_event_segments(
                directory, event_payloads, max_segment_chars=max_segment_chars
            )
        metadata = self._read_metadata(directory)
        updated = SessionMetadata(
            id=metadata.id,
            created_at=metadata.created_at,
            updated_at=float(self._clock()),
            workspace=metadata.workspace,
            model=metadata.model,
            title=metadata.title,
            sensitive=metadata.sensitive,
            sensitive_authority=metadata.sensitive_authority,
            history_format=HISTORY_FORMAT_VERSION,
        )
        self._write_metadata(directory, updated)
        self._remove_legacy_history_files(directory)

    def append_events(self, session_id: str, events: Sequence[RunEvent]) -> None:
        directory = self._require_session_dir(session_id)
        if not events:
            return
        self._ensure_history_migratable(directory)
        existing = self._read_jsonl_segments(directory / EVENTS_DIR_NAME, kind="events")
        legacy = directory / EVENTS_NAME
        if legacy.exists() and not existing:
            existing = self._read_jsonl_file(legacy, label="events")
        existing.extend(event.to_dict() for event in events)
        self._write_event_segments(directory, existing)
        self._remove_legacy_history_files(directory)

    def _ensure_history_migratable(self, directory: Path) -> None:
        metadata = self._read_metadata(directory)
        if metadata.history_format > HISTORY_FORMAT_VERSION:
            raise SessionError(
                f'Session "{metadata.id}" history format '
                f"{metadata.history_format} is newer than supported "
                f"({HISTORY_FORMAT_VERSION}); upgrade OrbitRelay before resume"
            )

    def _remove_legacy_history_files(self, directory: Path) -> None:
        for name in (MESSAGES_NAME, EVENTS_NAME):
            path = directory / name
            if path.exists() and path.is_file() and not path.is_symlink():
                path.unlink(missing_ok=True)

    def _write_message_segments(
        self,
        directory: Path,
        messages: Sequence[Any],
        *,
        max_segment_chars: int = DEFAULT_MAX_SEGMENT_CHARS,
    ) -> None:
        segments = pack_segments(messages, max_segment_chars=max_segment_chars)
        self._replace_jsonl_segments(
            directory / MESSAGES_DIR_NAME, segments, kind="messages"
        )

    def _write_event_segments(
        self,
        directory: Path,
        events: Sequence[Mapping[str, Any]],
        *,
        max_segment_chars: int = DEFAULT_MAX_SEGMENT_CHARS,
    ) -> None:
        segments: list[list[Any]] = []
        current: list[Any] = []
        current_size = 0
        for event in events:
            payload = dict(event)
            size = len(
                json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
            )
            if current and current_size + size > max_segment_chars:
                segments.append(current)
                current = []
                current_size = 0
            current.append(payload)
            current_size += size
        if current:
            segments.append(current)
        self._replace_jsonl_segments(
            directory / EVENTS_DIR_NAME, segments, kind="events"
        )

    def _replace_jsonl_segments(
        self,
        target_dir: Path,
        segments: Sequence[Sequence[Any]],
        *,
        kind: str,
    ) -> None:
        parent = target_dir.parent
        _secure_mkdir(parent)
        temporary = parent / f".{target_dir.name}.tmp-{uuid.uuid4().hex}"
        if temporary.exists():
            raise SessionError(f"could not stage {kind} segments")
        _secure_mkdir(temporary)
        try:
            if not segments:
                _write_text_secure(temporary / "000001.jsonl", "")
            else:
                for index, segment in enumerate(segments, start=1):
                    body = "".join(
                        json.dumps(
                            dict(item) if isinstance(item, Mapping) else item,
                            sort_keys=True,
                            separators=(",", ":"),
                            default=str,
                        )
                        + "\n"
                        for item in segment
                    )
                    _write_text_secure(temporary / f"{index:06d}.jsonl", body)
            backup = parent / f".{target_dir.name}.bak-{uuid.uuid4().hex}"
            if target_dir.exists():
                target_dir.rename(backup)
            temporary.rename(target_dir)
            if backup.exists():
                for child in backup.iterdir():
                    if child.is_file():
                        child.unlink(missing_ok=True)
                with suppress(OSError):
                    backup.rmdir()
        except OSError as exc:
            if temporary.exists():
                for child in temporary.iterdir():
                    if child.is_file():
                        child.unlink(missing_ok=True)
                with suppress(OSError):
                    temporary.rmdir()
            raise SessionError(f"could not write {kind} segments: {exc}") from exc

    def _read_message_segments(self, directory: Path) -> list[dict[str, Any]]:
        segmented = directory / MESSAGES_DIR_NAME
        legacy = directory / MESSAGES_NAME
        if segmented.exists() and segmented.is_dir() and not segmented.is_symlink():
            return self._read_jsonl_segments(segmented, kind="messages")
        if legacy.exists():
            return self._read_jsonl_file(legacy, label="messages")
        return []

    def _read_jsonl_segments(
        self, directory: Path, *, kind: str
    ) -> list[dict[str, Any]]:
        if not directory.exists():
            return []
        _validate_path(directory)
        if directory.is_symlink():
            raise SessionError(f"{kind} segment directory cannot be a symbolic link")
        paths = sorted(
            path
            for path in directory.iterdir()
            if path.is_file()
            and not path.is_symlink()
            and path.name.endswith(".jsonl")
        )
        messages: list[dict[str, Any]] = []
        for path in paths:
            messages.extend(self._read_jsonl_file(path, label=kind))
        return messages

    def _read_jsonl_file(self, path: Path, *, label: str) -> list[dict[str, Any]]:
        _validate_path(path)
        rows: list[dict[str, Any]] = []
        try:
            with path.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise SessionCorruptionError(
                            f"session {label} line {line_number} is not valid JSON"
                        ) from exc
                    if not isinstance(payload, dict):
                        raise SessionCorruptionError(
                            f"session {label} line {line_number} must be an object"
                        )
                    rows.append(payload)
        except OSError as exc:
            raise SessionError(f'Could not read session {label}: "{path.name}"') from exc
        return rows

    def bind_collector(
        self, session_id: str, collector: EventCollector
    ) -> EventCollector:
        """Keep events in memory until a replay-safe checkpoint commits them."""
        del session_id
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
