# story: e04s05

"""Pair-preserving context budgeting for model message history.

Policy:
- Keep leading system messages when present.
- Treat an assistant message that contains tool_calls together with its
  following tool-result messages as one indivisible segment.
- Drop oldest segments first; prefer newest history.
- If a single retained segment (or the system prefix alone) cannot fit the
  budget, fail closed with ContextBudgetError rather than splitting pairs.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


DEFAULT_MAX_CONTEXT_CHARS = 200_000


class ContextBudgetError(RuntimeError):
    """Raised when history cannot fit the budget without splitting tool pairs."""


def message_size(message: Any) -> int:
    """Approximate serialized size used for budgeting."""
    if isinstance(message, Mapping):
        payload = dict(message)
    elif hasattr(message, "model_dump"):
        payload = message.model_dump(exclude_none=True)
    else:
        payload = {"value": repr(message)}
    return len(json.dumps(payload, sort_keys=True, default=str))


def _role(message: Any) -> str | None:
    if isinstance(message, Mapping):
        role = message.get("role")
    else:
        role = getattr(message, "role", None)
    return role if isinstance(role, str) else None


def _tool_calls(message: Any) -> list[Any]:
    if isinstance(message, Mapping):
        calls = message.get("tool_calls") or []
    else:
        calls = getattr(message, "tool_calls", None) or []
    return list(calls) if isinstance(calls, (list, tuple)) else []


def _tool_call_id(message: Any) -> str | None:
    if isinstance(message, Mapping):
        value = message.get("tool_call_id")
    else:
        value = getattr(message, "tool_call_id", None)
    return value if isinstance(value, str) else None


def _call_ids(tool_calls: Sequence[Any]) -> set[str]:
    ids: set[str] = set()
    for call in tool_calls:
        if isinstance(call, Mapping):
            call_id = call.get("id")
        else:
            call_id = getattr(call, "id", None)
        if isinstance(call_id, str) and call_id:
            ids.add(call_id)
    return ids


@dataclass(frozen=True)
class _Segment:
    messages: tuple[Any, ...]
    size: int


def _segmentize(messages: Sequence[Any]) -> tuple[list[_Segment], list[_Segment]]:
    """Split into (prefix_segments, body_segments)."""
    prefix: list[_Segment] = []
    body: list[_Segment] = []
    index = 0
    # Keep contiguous leading system messages as prefix.
    while index < len(messages) and _role(messages[index]) == "system":
        item = messages[index]
        prefix.append(_Segment(messages=(item,), size=message_size(item)))
        index += 1

    while index < len(messages):
        message = messages[index]
        tool_calls = _tool_calls(message)
        if _role(message) == "assistant" and tool_calls:
            ids = _call_ids(tool_calls)
            group = [message]
            size = message_size(message)
            index += 1
            while index < len(messages) and _role(messages[index]) == "tool":
                tool_message = messages[index]
                tool_id = _tool_call_id(tool_message)
                if ids and tool_id is not None and tool_id not in ids:
                    break
                group.append(tool_message)
                size += message_size(tool_message)
                index += 1
            body.append(_Segment(messages=tuple(group), size=size))
            continue
        body.append(_Segment(messages=(message,), size=message_size(message)))
        index += 1
    return prefix, body


def apply_context_budget(
    messages: Sequence[Any],
    *,
    max_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
) -> list[Any]:
    """Return a budgeted copy of messages that never splits tool pairs."""
    if max_chars <= 0:
        raise ContextBudgetError("context budget must be positive")
    if not messages:
        return []

    prefix, body = _segmentize(messages)
    prefix_size = sum(segment.size for segment in prefix)
    if prefix_size > max_chars:
        raise ContextBudgetError(
            "system prefix alone exceeds the context budget; cannot send request"
        )

    remaining = max_chars - prefix_size
    kept_reversed: list[_Segment] = []
    used = 0
    for segment in reversed(body):
        if used + segment.size <= remaining:
            kept_reversed.append(segment)
            used += segment.size
            continue
        if not kept_reversed and body:
            # Newest body segment cannot fit with prefix.
            raise ContextBudgetError(
                "newest conversation segment exceeds the context budget; "
                "refusing to split tool-call/result pairs"
            )
        # Older segment does not fit; stop (drop older history).
        break

    kept = list(reversed(kept_reversed))
    result: list[Any] = []
    for segment in prefix + kept:
        result.extend(segment.messages)
    return result


def assert_no_orphan_tool_results(messages: Sequence[Any]) -> None:
    """Test helper: ensure every tool message has a preceding assistant tool_call."""
    pending_ids: set[str] = set()
    for message in messages:
        role = _role(message)
        if role == "assistant":
            pending_ids = _call_ids(_tool_calls(message))
            continue
        if role == "tool":
            tool_id = _tool_call_id(message)
            if tool_id is None or tool_id not in pending_ids:
                raise AssertionError(f"orphan tool result: {tool_id!r}")
            continue
        pending_ids = set()
