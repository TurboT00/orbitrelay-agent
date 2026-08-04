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
# Durable segment and resume-memory bounds (named contracts for e08s04).
DEFAULT_MAX_SEGMENT_CHARS = 256_000
DEFAULT_MAX_REPLAY_CHARS = DEFAULT_MAX_CONTEXT_CHARS
HISTORY_FORMAT_VERSION = 2


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
    role = message.get("role") if isinstance(message, Mapping) else getattr(message, "role", None)
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
        call_id = call.get("id") if isinstance(call, Mapping) else getattr(call, "id", None)
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


def is_replay_safe(messages: Sequence[Any]) -> bool:
    """Return True when every assistant tool-call group has all correlated results."""
    index = 0
    items = list(messages)
    while index < len(items):
        message = items[index]
        tool_calls = _tool_calls(message)
        if _role(message) == "assistant" and tool_calls:
            ids = _call_ids(tool_calls)
            index += 1
            seen: set[str] = set()
            while index < len(items) and _role(items[index]) == "tool":
                tool_id = _tool_call_id(items[index])
                if tool_id is None or (ids and tool_id not in ids):
                    return False
                if tool_id in seen:
                    return False
                seen.add(tool_id)
                index += 1
            if ids and seen != ids:
                return False
            continue
        if _role(message) == "tool":
            return False
        index += 1
    return True


def replay_safe_prefix(messages: Sequence[Any]) -> list[Any]:
    """Return the longest prefix that is replay-safe (drop incomplete trailing groups)."""
    items = list(messages)
    while items and not is_replay_safe(items):
        # Drop trailing incomplete assistant/tool tail one message at a time.
        items.pop()
    return items


def strip_system_messages(messages: Sequence[Any]) -> list[Any]:
    """Remove system-role messages so current instructions can replace them."""
    return [message for message in messages if _role(message) != "system"]


def partition_history(messages: Sequence[Any]) -> list[tuple[Any, ...]]:
    """Partition history into indivisible prefix/body segments (tool-pair safe)."""
    prefix, body = _segmentize(messages)
    return [segment.messages for segment in prefix + body]


def pack_segments(
    messages: Sequence[Any],
    *,
    max_segment_chars: int = DEFAULT_MAX_SEGMENT_CHARS,
) -> list[list[Any]]:
    """Pack complete groups into segment files without splitting tool pairs.

    A single oversized group becomes its own segment (file may exceed the nominal
    bound) rather than splitting the group.
    """
    if max_segment_chars <= 0:
        raise ContextBudgetError("segment bound must be positive")
    groups = partition_history(messages)
    if not groups:
        return []
    segments: list[list[Any]] = []
    current: list[Any] = []
    current_size = 0
    for group in groups:
        group_list = list(group)
        size = sum(message_size(item) for item in group_list)
        if size > max_segment_chars:
            if current:
                segments.append(current)
                current = []
                current_size = 0
            segments.append(group_list)
            continue
        if current and current_size + size > max_segment_chars:
            segments.append(current)
            current = []
            current_size = 0
        current.extend(group_list)
        current_size += size
    if current:
        segments.append(current)
    return segments


def select_replay_messages(
    messages: Sequence[Any],
    *,
    max_chars: int = DEFAULT_MAX_REPLAY_CHARS,
) -> list[Any]:
    """Return newest complete groups within the resume-memory bound.

    System messages are stripped; callers inject current instructions separately.
    """
    if max_chars <= 0:
        raise ContextBudgetError("replay memory bound must be positive")
    body = strip_system_messages(messages)
    if not body:
        return []
    # Reuse pair-preserving budget without a system prefix.
    return apply_context_budget(body, max_chars=max_chars)
