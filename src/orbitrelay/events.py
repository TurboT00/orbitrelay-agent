# story: e04s01

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .redaction import redact_secrets


class EventType(StrEnum):
    RUN_STARTED = "run.started"
    MODEL_MESSAGE = "model.message"
    TOOL_REQUESTED = "tool.requested"
    APPROVAL_DECIDED = "approval.decided"
    TOOL_RESULT = "tool.result"
    USAGE_REPORTED = "usage.reported"
    RUN_ERROR = "run.error"
    RUN_COMPLETED = "run.completed"


@dataclass(frozen=True)
class RunEvent:
    type: EventType
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = redact_secrets(dict(self.data))
        if not isinstance(payload, dict):
            raise TypeError("event data must redact to a mapping")
        return {"type": self.type.value, "data": payload}


class EventCollector:
    """Ordered, secret-redacting event sink for a single run."""

    def __init__(self) -> None:
        self._events: list[RunEvent] = []

    @property
    def events(self) -> tuple[RunEvent, ...]:
        return tuple(self._events)

    def emit(self, event_type: EventType | str, **data: Any) -> RunEvent:
        typed = event_type if isinstance(event_type, EventType) else EventType(event_type)
        event = RunEvent(type=typed, data=dict(data))
        self._events.append(event)
        return event

    def as_dicts(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self._events]

    def of_type(self, event_type: EventType | str) -> tuple[RunEvent, ...]:
        typed = event_type if isinstance(event_type, EventType) else EventType(event_type)
        return tuple(event for event in self._events if event.type is typed)


def null_collector() -> EventCollector:
    """Return a collector instance; callers may ignore events."""
    return EventCollector()


def summarize_tool_names(events: Sequence[RunEvent]) -> tuple[str, ...]:
    names: list[str] = []
    for event in events:
        if event.type is EventType.TOOL_REQUESTED:
            name = event.data.get("tool")
            if isinstance(name, str):
                names.append(name)
    return tuple(names)
