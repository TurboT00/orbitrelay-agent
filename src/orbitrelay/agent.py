# story: e02s03
# story: e02s06
# story: e04s01
# story: e04s02
# story: e04s03
# story: e04s05

import json
import sys
from collections.abc import Callable, Iterator, Sequence
from typing import Any, TextIO

from .approval_format import format_approval_record
from .approvals import ApprovalDecision, ApprovalSession
from .context_budget import DEFAULT_MAX_CONTEXT_CHARS, apply_context_budget
from .events import EventCollector, EventType
from .prompts import system_prompt
from .streaming import assemble_chat_completion
from .tools import (
    TOOL_DEFINITIONS,
    PreparedToolCall,
    execute_prepared_tool,
    prepare_tool,
)

MAX_MODEL_RESPONSES = 8
ValidatedToolCall = tuple[str, str, str]
PreparedToolResult = PreparedToolCall | str


class TurnLimitError(RuntimeError):
    pass


def _field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _serialize_assistant_message(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        serialized = {key: value for key, value in message.items() if value is not None}
    elif hasattr(message, "model_dump"):
        serialized = message.model_dump(exclude_none=True)
        model_extra = getattr(message, "model_extra", None)
        if isinstance(model_extra, dict):
            serialized.update(
                {key: value for key, value in model_extra.items() if value is not None}
            )
    else:
        raise RuntimeError("API response message could not be serialized")

    if not isinstance(serialized, dict):
        raise RuntimeError("API response message did not serialize to an object")
    if serialized.get("role") != "assistant":
        raise RuntimeError("API response message did not have the assistant role")
    return serialized


def _validate_tool_calls(tool_calls: Any) -> list[ValidatedToolCall]:
    if not isinstance(tool_calls, (list, tuple)):
        raise RuntimeError("API response tool_calls was not a list")
    validated: list[tuple[str, str, str]] = []
    seen_ids: set[str] = set()
    for index, tool_call in enumerate(tool_calls):
        validated_call = _validated_tool_call(index, tool_call)
        call_id = validated_call[0]
        if call_id in seen_ids:
            raise RuntimeError(f'Tool call id "{call_id}" was duplicated')
        seen_ids.add(call_id)
        validated.append(validated_call)
    return validated


def _validated_tool_call(index: int, tool_call: Any) -> ValidatedToolCall:
    call_id, call_type, function, name, arguments = _tool_call_parts(tool_call)
    if not isinstance(call_id, str) or not call_id:
        raise RuntimeError(f"Tool call {index} did not include a nonempty id")
    if call_type != "function":
        raise RuntimeError(f"Tool call {index} was not a function call")
    if function is None:
        raise RuntimeError(f"Tool call {index} did not include a function")
    if not isinstance(name, str) or not name:
        raise RuntimeError(f"Tool call {index} did not include a function name")
    if not isinstance(arguments, str):
        raise RuntimeError(f"Tool call {index} arguments was not a JSON string")
    return call_id, name, arguments


def _tool_call_parts(tool_call: Any) -> tuple[Any, Any, Any, Any, Any]:
    function = _field(tool_call, "function")
    return (
        _field(tool_call, "id"),
        _field(tool_call, "type"),
        function,
        _field(function, "name"),
        _field(function, "arguments"),
    )


def _print_usage(response_number: int, response: Any) -> None:
    usage = _field(response, "usage")
    if usage is None:
        print(f"Response {response_number}: usage unavailable")
        return

    prompt_tokens = _field(usage, "prompt_tokens")
    completion_tokens = _field(usage, "completion_tokens")
    print(
        f"Response {response_number}: "
        f"prompt tokens={prompt_tokens if prompt_tokens is not None else 'unknown'}, "
        f"completion tokens={completion_tokens if completion_tokens is not None else 'unknown'}"
    )


def _emit_usage(
    collector: EventCollector | None, response_number: int, response: Any
) -> None:
    usage = _field(response, "usage")
    if collector is None:
        return
    if usage is None:
        collector.emit(
            EventType.USAGE_REPORTED,
            response_number=response_number,
            available=False,
        )
        return
    collector.emit(
        EventType.USAGE_REPORTED,
        response_number=response_number,
        available=True,
        prompt_tokens=_field(usage, "prompt_tokens"),
        completion_tokens=_field(usage, "completion_tokens"),
    )


def run_agent(
    client: Any,
    user_prompt: str,
    model: str,
    *,
    working_directory: str,
    verbose: bool = False,
    stream: bool = False,
    approval_session: ApprovalSession | None = None,
    audit_stream: TextIO | None = None,
    event_collector: EventCollector | None = None,
    initial_messages: Sequence[Any] | None = None,
    on_messages_update: Callable[[list[Any]], None] | None = None,
    max_context_chars: int | None = DEFAULT_MAX_CONTEXT_CHARS,
) -> str:
    collector = event_collector
    messages = _starting_messages(user_prompt, initial_messages)
    if collector is not None:
        collector.emit(
            EventType.RUN_STARTED,
            model=model,
            workspace=working_directory,
            stream=stream,
        )
    if on_messages_update is not None:
        on_messages_update(list(messages))
    try:
        final_text = _run_response_loop(
            client,
            model,
            messages,
            working_directory,
            verbose,
            stream,
            approval_session or ApprovalSession(),
            sys.stderr if audit_stream is None else audit_stream,
            collector,
            on_messages_update,
            max_context_chars,
        )
    except Exception as exc:
        if collector is not None:
            collector.emit(
                EventType.RUN_ERROR,
                error_type=type(exc).__name__,
                message=str(exc),
            )
            collector.emit(EventType.RUN_COMPLETED, status="error")
        raise
    if collector is not None:
        collector.emit(
            EventType.MODEL_MESSAGE,
            role="assistant",
            content=final_text,
        )
        collector.emit(EventType.RUN_COMPLETED, status="completed")
    if on_messages_update is not None:
        # Persist final assistant message into conversation history.
        final_messages = list(messages)
        if not final_messages or final_messages[-1].get("role") != "assistant":
            final_messages.append({"role": "assistant", "content": final_text})
        on_messages_update(final_messages)
    return final_text


def _initial_messages(user_prompt: str) -> list[Any]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _starting_messages(
    user_prompt: str, initial_messages: Sequence[Any] | None
) -> list[Any]:
    if initial_messages is None:
        return _initial_messages(user_prompt)
    history = [message for message in initial_messages]
    history.append({"role": "user", "content": user_prompt})
    return history


def _create_model_response(
    client: Any,
    model: str,
    messages: list[Any],
    *,
    stream: bool,
    collector: EventCollector | None,
    response_number: int,
    max_context_chars: int | None,
) -> Any:
    outbound = (
        messages
        if max_context_chars is None
        else apply_context_budget(messages, max_chars=max_context_chars)
    )
    if not stream:
        return client.chat.completions.create(
            model=model, messages=outbound, tools=TOOL_DEFINITIONS
        )
    stream_response = client.chat.completions.create(
        model=model,
        messages=outbound,
        tools=TOOL_DEFINITIONS,
        stream=True,
    )
    return assemble_chat_completion(
        stream_response,
        collector=collector,
        response_number=response_number,
    )


def _run_response_loop(
    client: Any,
    model: str,
    messages: list[Any],
    working_directory: str,
    verbose: bool,
    stream: bool,
    approval_session: ApprovalSession,
    audit_stream: TextIO,
    event_collector: EventCollector | None,
    on_messages_update: Callable[[list[Any]], None] | None = None,
    max_context_chars: int | None = DEFAULT_MAX_CONTEXT_CHARS,
) -> str:
    context = (
        working_directory,
        verbose,
        approval_session,
        audit_stream,
        event_collector,
        on_messages_update,
    )
    for response_number in range(1, MAX_MODEL_RESPONSES + 1):
        response = _create_model_response(
            client,
            model,
            messages,
            stream=stream,
            collector=event_collector,
            response_number=response_number,
            max_context_chars=max_context_chars,
        )
        final_text = _process_response(response, response_number, messages, context)
        if final_text is not None:
            return final_text
    raise AssertionError("Unreachable response loop state")


def _process_response(
    response: Any,
    response_number: int,
    messages: list[Any],
    context: tuple[
        str,
        bool,
        ApprovalSession,
        TextIO,
        EventCollector | None,
        Callable[[list[Any]], None] | None,
    ],
) -> str | None:
    _workspace, verbose, _session, _audit, collector, on_messages_update = context
    if verbose:
        _print_usage(response_number, response)
    _emit_usage(collector, response_number, response)
    message = _response_message(response)
    tool_calls = _field(message, "tool_calls") or []
    if not tool_calls:
        return _final_text(message)
    messages.extend(_tool_round_messages(message, tool_calls, response_number, context))
    if on_messages_update is not None:
        on_messages_update(list(messages))
    return None


def _response_message(response: Any) -> Any:
    choices = _field(response, "choices")
    if not isinstance(choices, (list, tuple)) or not choices:
        raise RuntimeError("API response did not include any choices")
    message = _field(choices[0], "message")
    if message is None:
        raise RuntimeError("API response choice did not include a message")
    return message


def _final_text(message: Any) -> str:
    content = _field(message, "content")
    if not isinstance(content, str) or not content:
        raise RuntimeError("API response did not include final text")
    return content


def _tool_round_messages(
    message: Any,
    tool_calls: Any,
    response_number: int,
    context: tuple[
        str,
        bool,
        ApprovalSession,
        TextIO,
        EventCollector | None,
        Callable[[list[Any]], None] | None,
    ],
) -> list[dict[str, Any]]:
    workspace, verbose, session, audit_stream, collector, _on_messages_update = context
    if response_number == MAX_MODEL_RESPONSES:
        raise TurnLimitError(
            f"Model requested more tools after the {MAX_MODEL_RESPONSES}-response "
            f"limit; those calls were not executed"
        )
    validated = _validate_tool_calls(tool_calls)
    if collector is not None:
        for call_id, name, _arguments in validated:
            collector.emit(
                EventType.TOOL_REQUESTED,
                tool_call_id=call_id,
                tool=name,
            )
            collector.emit(
                EventType.TOOL_PROGRESS,
                tool_call_id=call_id,
                tool=name,
                phase="preparing",
            )
    prepared = _prepare_calls(validated, workspace)
    if collector is not None:
        for call_id, name, _arguments in validated:
            collector.emit(
                EventType.TOOL_PROGRESS,
                tool_call_id=call_id,
                tool=name,
                phase="authorizing",
            )
    start = len(session.records)
    decisions = _authorize_calls(prepared, session)
    if verbose:
        _emit_approval_records(session.records[start:], audit_stream)
    if collector is not None:
        for record in session.records[start:]:
            collector.emit(
                EventType.APPROVAL_DECIDED,
                tool_call_id=record.call_id,
                tool=record.tool_name,
                disposition=record.disposition.value,
                reason=record.reason,
            )
            collector.emit(
                EventType.TOOL_PROGRESS,
                tool_call_id=record.call_id,
                tool=record.tool_name,
                phase="executing",
            )
    results = _tool_result_messages(
        validated, prepared, decisions, verbose, collector
    )
    return [_serialize_assistant_message(message), *results]


def _emit_approval_records(
    records: tuple[Any, ...], audit_stream: TextIO
) -> None:
    for record in records:
        print(format_approval_record(record), file=audit_stream, flush=True)


def _prepare_calls(
    validated_calls: list[ValidatedToolCall], working_directory: str,
) -> list[PreparedToolResult]:
    return [
        prepare_tool(call_id, name, arguments, working_directory)
        for call_id, name, arguments in validated_calls
    ]


def _authorize_calls(
    prepared_calls: list[PreparedToolResult], approval_session: ApprovalSession,
) -> Iterator[ApprovalDecision]:
    requests = tuple(
        prepared.approval_request
        for prepared in prepared_calls
        if isinstance(prepared, PreparedToolCall)
    )
    return iter(approval_session.authorize(requests) if requests else ())


def _tool_result_messages(
    validated_calls: list[ValidatedToolCall],
    prepared_calls: list[PreparedToolResult],
    decisions: Iterator[ApprovalDecision],
    verbose: bool,
    collector: EventCollector | None = None,
) -> list[dict[str, str]]:
    messages = []
    for (call_id, name, _arguments), prepared in zip(
        validated_calls, prepared_calls, strict=True
    ):
        result = prepared if isinstance(prepared, str) else _execute_authorized_call(
            prepared, next(decisions), verbose
        )
        if collector is not None:
            # Do not include raw tool payload content in events (may be large/sensitive).
            collector.emit(
                EventType.TOOL_RESULT,
                tool_call_id=call_id,
                tool=name,
                status="error" if _looks_like_tool_error(result) else "ok",
                content_length=len(result),
            )
        messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
    return messages


def _looks_like_tool_error(result: str) -> bool:
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and "error" in payload


def _execute_authorized_call(
    prepared: PreparedToolCall,
    decision: ApprovalDecision,
    verbose: bool,
) -> str:
    if decision.approved:
        return execute_prepared_tool(prepared, verbose)

    request = prepared.approval_request
    return json.dumps(
        {
            "error": {
                "code": _denial_code(decision),
                "reason": decision.reason,
                "tool": request.tool_name,
                "tool_call_id": request.call_id,
            }
        },
        sort_keys=True,
    )


def _denial_code(decision: ApprovalDecision) -> str:
    if decision.reason in {"user_disabled_tool", "tool_disabled_for_run"}:
        return "tool_disabled"
    return "approval_denied"
