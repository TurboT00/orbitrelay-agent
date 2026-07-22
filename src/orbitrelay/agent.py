from typing import Any

from .prompts import system_prompt
from .tools import TOOL_DEFINITIONS, execute_tool


MAX_MODEL_RESPONSES = 8


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


def _validate_tool_calls(tool_calls: Any) -> list[tuple[str, str, str]]:
    if not isinstance(tool_calls, (list, tuple)):
        raise RuntimeError("API response tool_calls was not a list")

    validated: list[tuple[str, str, str]] = []
    seen_ids: set[str] = set()

    for index, tool_call in enumerate(tool_calls):
        call_id = _field(tool_call, "id")
        call_type = _field(tool_call, "type")
        function = _field(tool_call, "function")
        function_name = _field(function, "name")
        arguments = _field(function, "arguments")

        if not isinstance(call_id, str) or not call_id:
            raise RuntimeError(f"Tool call {index} did not include a nonempty id")
        if call_id in seen_ids:
            raise RuntimeError(f'Tool call id "{call_id}" was duplicated')
        if call_type != "function":
            raise RuntimeError(f"Tool call {index} was not a function call")
        if function is None:
            raise RuntimeError(f"Tool call {index} did not include a function")
        if not isinstance(function_name, str) or not function_name:
            raise RuntimeError(f"Tool call {index} did not include a function name")
        if not isinstance(arguments, str):
            raise RuntimeError(f"Tool call {index} arguments was not a JSON string")

        seen_ids.add(call_id)
        validated.append((call_id, function_name, arguments))

    return validated


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
) -> str:
    messages: list[Any] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for response_number in range(1, MAX_MODEL_RESPONSES + 1):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_DEFINITIONS,
        )

        if verbose:
            _print_usage(response_number, response)

        choices = _field(response, "choices")
        if not isinstance(choices, (list, tuple)) or not choices:
            raise RuntimeError("API response did not include any choices")

        message = _field(choices[0], "message")
        if message is None:
            raise RuntimeError("API response choice did not include a message")

        tool_calls = _field(message, "tool_calls") or []
        if tool_calls:
            if response_number == MAX_MODEL_RESPONSES:
                raise TurnLimitError(
                    f"Model requested more tools after the "
                    f"{MAX_MODEL_RESPONSES}-response limit; those calls were not executed"
                )

            validated_calls = _validate_tool_calls(tool_calls)
            assistant_message = _serialize_assistant_message(message)
            messages.append(assistant_message)

            for call_id, function_name, arguments in validated_calls:
                result = execute_tool(
                    function_name,
                    arguments,
                    working_directory,
                    verbose,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result,
                    }
                )
            continue

        content = _field(message, "content")
        if not isinstance(content, str) or not content:
            raise RuntimeError("API response did not include final text")
        return content

    raise AssertionError("Unreachable response loop state")
