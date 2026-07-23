import json
from collections.abc import Iterator
from typing import Any

from .approvals import ApprovalDecision, ApprovalSession
from .prompts import system_prompt
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


def run_agent(
    client: Any,
    user_prompt: str,
    model: str,
    *,
    working_directory: str,
    verbose: bool = False,
    approval_session: ApprovalSession | None = None,
) -> str:
    return _run_response_loop(
        client,
        model,
        _initial_messages(user_prompt),
        working_directory,
        verbose,
        approval_session or ApprovalSession(),
    )


def _initial_messages(user_prompt: str) -> list[Any]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _run_response_loop(
    client: Any, model: str, messages: list[Any], working_directory: str,
    verbose: bool, approval_session: ApprovalSession,
) -> str:
    for response_number in range(1, MAX_MODEL_RESPONSES + 1):
        response = client.chat.completions.create(
            model=model, messages=messages, tools=TOOL_DEFINITIONS
        )
        final_text = _process_response(
            response, response_number, messages, working_directory,
            verbose, approval_session,
        )
        if final_text is not None:
            return final_text
    raise AssertionError("Unreachable response loop state")


def _process_response(
    response: Any, response_number: int, messages: list[Any],
    working_directory: str, verbose: bool, approval_session: ApprovalSession,
) -> str | None:
    if verbose:
        _print_usage(response_number, response)
    message = _response_message(response)
    tool_calls = _field(message, "tool_calls") or []
    if not tool_calls:
        return _final_text(message)
    messages.extend(
        _tool_round_messages(
            message, tool_calls, response_number, working_directory,
            verbose, approval_session,
        )
    )
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
    message: Any, tool_calls: Any, response_number: int, working_directory: str,
    verbose: bool, approval_session: ApprovalSession,
) -> list[dict[str, Any]]:
    if response_number == MAX_MODEL_RESPONSES:
        raise TurnLimitError(
            f"Model requested more tools after the {MAX_MODEL_RESPONSES}-response "
            f"limit; those calls were not executed"
        )
    validated_calls = _validate_tool_calls(tool_calls)
    prepared_calls = _prepare_calls(validated_calls, working_directory)
    decisions = _authorize_calls(prepared_calls, approval_session)
    return [_serialize_assistant_message(message), *_tool_result_messages(
        validated_calls, prepared_calls, decisions, verbose
    )]


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
) -> list[dict[str, str]]:
    messages = []
    for (call_id, _name, _arguments), prepared in zip(
        validated_calls, prepared_calls, strict=True
    ):
        result = prepared if isinstance(prepared, str) else _execute_authorized_call(
            prepared, next(decisions), verbose
        )
        messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
    return messages


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
