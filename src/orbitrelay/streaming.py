# story: e04s02

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from types import SimpleNamespace
from typing import Any

from .events import EventCollector, EventType


def _field(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _delta_content(delta: Any) -> str | None:
    content = _field(delta, "content")
    if isinstance(content, str) and content:
        return content
    return None


def _object_fields(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        fields = dict(value)
    else:
        try:
            fields = dict(vars(value))
        except TypeError:
            fields = {}
        if not fields:
            model_dump = getattr(value, "model_dump", None)
            if callable(model_dump):
                dumped = model_dump(exclude_none=True)
                fields = dict(dumped) if isinstance(dumped, Mapping) else {}
    model_extra = getattr(value, "model_extra", None)
    if isinstance(model_extra, Mapping):
        fields.update(model_extra)
    return fields


def _merge_delta_value(field: str, current: Any, incoming: Any) -> Any:
    if current is None or field == "role":
        return incoming
    if isinstance(current, str) and isinstance(incoming, str):
        return current + incoming
    if isinstance(current, list) and isinstance(incoming, list):
        return [*current, *incoming]
    if isinstance(current, Mapping) and isinstance(incoming, Mapping):
        merged = dict(current)
        for key, value in incoming.items():
            merged[key] = _merge_delta_value(str(key), merged.get(key), value)
        return merged
    return incoming


def _merge_extension_delta(fields: dict[str, Any], delta: Any) -> None:
    for field, value in _object_fields(delta).items():
        if field in {"content", "tool_calls"} or value is None:
            continue
        fields[field] = _merge_delta_value(field, fields.get(field), value)


def _merge_tool_call_delta(
    buckets: dict[int, dict[str, Any]], tool_call: Any
) -> None:
    index = _field(tool_call, "index")
    if not isinstance(index, int):
        index = 0
    bucket = buckets.setdefault(
        index,
        {
            "id": "",
            "type": "function",
            "function": {"name_parts": [], "argument_parts": []},
        },
    )
    call_id = _field(tool_call, "id")
    if isinstance(call_id, str) and call_id:
        bucket["id"] = call_id
    call_type = _field(tool_call, "type")
    if isinstance(call_type, str) and call_type:
        bucket["type"] = call_type
    function = _field(tool_call, "function")
    if function is None:
        return
    name = _field(function, "name")
    if isinstance(name, str) and name:
        bucket["function"]["name_parts"].append(name)
    arguments = _field(function, "arguments")
    if isinstance(arguments, str) and arguments:
        bucket["function"]["argument_parts"].append(arguments)


def _tool_call_object(bucket: dict[str, Any]) -> Any:
    function = SimpleNamespace(
        name="".join(bucket["function"]["name_parts"]),
        arguments="".join(bucket["function"]["argument_parts"]),
    )
    tool_call = SimpleNamespace(
        id=bucket["id"],
        type=bucket["type"],
        function=function,
    )

    def model_dump(exclude_none: bool = True) -> dict[str, Any]:
        payload = {
            "id": tool_call.id,
            "type": tool_call.type,
            "function": {
                "name": function.name,
                "arguments": function.arguments,
            },
        }
        if exclude_none:
            return {key: value for key, value in payload.items() if value is not None}
        return payload

    tool_call.model_dump = model_dump
    return tool_call


def _assistant_message(
    content: str | None,
    tool_calls: list[Any],
    extension_fields: Mapping[str, Any],
) -> Any:
    payload: dict[str, Any] = dict(extension_fields)
    payload.setdefault("role", "assistant")
    payload["content"] = content
    payload["tool_calls"] = tool_calls
    message = SimpleNamespace(**payload)

    def model_dump(exclude_none: bool = True) -> dict[str, Any]:
        serialized: dict[str, Any] = {
            **extension_fields,
            "role": getattr(message, "role", "assistant"),
            "content": content,
            "tool_calls": [
                call.model_dump(exclude_none=True)
                if hasattr(call, "model_dump")
                else call
                for call in tool_calls
            ]
            if tool_calls
            else None,
        }
        if exclude_none:
            return {
                key: value for key, value in serialized.items() if value is not None
            }
        return serialized

    message.model_dump = model_dump
    return message


def assemble_chat_completion(
    stream: Iterable[Any],
    *,
    collector: EventCollector | None = None,
    response_number: int = 1,
) -> Any:
    """Normalize a Chat Completions stream into one response-shaped object."""
    content_parts: list[str] = []
    tool_buckets: dict[int, dict[str, Any]] = {}
    extension_fields: dict[str, Any] = {}
    usage: Any = None

    for chunk in stream:
        chunk_usage = _field(chunk, "usage")
        if chunk_usage is not None:
            usage = chunk_usage
        choices = _field(chunk, "choices") or []
        if not choices:
            continue
        delta = _field(choices[0], "delta")
        if delta is None:
            continue
        _merge_extension_delta(extension_fields, delta)
        text = _delta_content(delta)
        if text is not None:
            content_parts.append(text)
            if collector is not None:
                collector.emit(
                    EventType.MODEL_DELTA,
                    text=text,
                    response_number=response_number,
                )
        tool_calls = _field(delta, "tool_calls") or []
        for tool_call in tool_calls:
            _merge_tool_call_delta(tool_buckets, tool_call)

    content = "".join(content_parts) if content_parts else None
    assembled_calls = [
        _tool_call_object(tool_buckets[index]) for index in sorted(tool_buckets)
    ]
    message = _assistant_message(content, assembled_calls, extension_fields)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=usage,
    )


def iter_text_deltas(stream: Iterable[Any]) -> Iterator[str]:
    for chunk in stream:
        choices = _field(chunk, "choices") or []
        if not choices:
            continue
        text = _delta_content(_field(choices[0], "delta"))
        if text is not None:
            yield text
