# story: e02s02

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from inspect import signature
from typing import Any

from orbitrelay.approval_format import format_prepared_call
from orbitrelay.approvals import ApprovalRequest, ToolCategory

from .get_file_content import get_file_content
from .get_files_info import get_files_info
from .run_python_file import run_python_file, validate_python_target
from .write_file import validate_write_target, write_file

FUNCTIONS: dict[str, Callable[..., str]] = {
    "get_files_info": get_files_info,
    "get_file_content": get_file_content,
    "run_python_file": run_python_file,
    "write_file": write_file,
}

TOOL_CATEGORIES: dict[str, ToolCategory] = {
    "get_files_info": ToolCategory.READ,
    "get_file_content": ToolCategory.READ,
    "run_python_file": ToolCategory.EXECUTE,
    "write_file": ToolCategory.WRITE,
}


@dataclass(frozen=True, slots=True)
class PreparedToolCall:
    name: str
    approval_request: ApprovalRequest
    _function: Callable[..., str] = field(repr=False)
    _arguments: tuple[tuple[str, Any], ...] = field(repr=False)


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_files_info",
            "description": "Lists files in a specified directory relative to the working directory, providing file size and directory status",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory path to list files from, relative to the working directory (default is the working directory itself)",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_content",
            "description": "Reads content from a file relative to the working directory, with truncation for very large files",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "File path to read from, relative to the working directory",
                    }
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python_file",
            "description": "Executes a Python file relative to the working directory with optional command-line arguments",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the Python file to execute, relative to the working directory",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of command-line arguments passed to the Python file",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Writes content to a file path relative to the working directory, creating missing parent directories as needed",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "File path to write to, relative to the working directory",
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content to write into the target file",
                    },
                },
                "required": ["file_path", "content"],
            },
        },
    },
]


def prepare_tool(
    call_id: str,
    name: str,
    arguments_json: str,
    working_directory: str,
) -> PreparedToolCall | str:
    function = FUNCTIONS.get(name)
    if function is None:
        return f'Error: unknown function "{name}"'
    arguments = _validated_arguments(name, arguments_json, working_directory, function)
    if isinstance(arguments, str):
        return arguments
    approval_request = _approval_request(call_id, name, arguments)
    if isinstance(approval_request, str):
        return approval_request
    return _prepared_call(name, approval_request, function, arguments)


def _prepared_call(
    name: str,
    approval_request: ApprovalRequest,
    function: Callable[..., str],
    arguments: dict[str, Any],
) -> PreparedToolCall:
    return PreparedToolCall(
        name=name,
        approval_request=approval_request,
        _function=function,
        _arguments=tuple(arguments.items()),
    )


def _validated_arguments(
    name: str,
    arguments_json: str,
    working_directory: str,
    function: Callable[..., str],
) -> dict[str, Any] | str:
    try:
        arguments = json.loads(arguments_json)
    except (json.JSONDecodeError, TypeError) as exc:
        return f'Error: invalid arguments for "{name}": {exc}'
    if not isinstance(arguments, dict):
        return f'Error: invalid arguments for "{name}": expected a JSON object'
    arguments["working_directory"] = working_directory
    try:
        signature(function).bind(**arguments)
    except TypeError as exc:
        return f'Error: invalid arguments for "{name}": {exc}'
    return arguments


def _approval_request(
    call_id: str,
    name: str,
    arguments: dict[str, Any],
) -> ApprovalRequest | str:
    if name == "write_file":
        return _write_approval_request(call_id, name, arguments)
    if name == "run_python_file":
        return _execution_approval_request(call_id, name, arguments)
    return ApprovalRequest(
        call_id=call_id,
        tool_name=name,
        category=TOOL_CATEGORIES[name],
        safe_context=(),
    )


def _write_approval_request(
    call_id: str,
    name: str,
    arguments: dict[str, Any],
) -> ApprovalRequest | str:
    file_path, content = arguments["file_path"], arguments["content"]
    if not isinstance(file_path, str):
        return f'Error: invalid arguments for "{name}": file_path must be a string'
    if not isinstance(content, str):
        return f'Error: invalid arguments for "{name}": content must be a string'
    validation_error = validate_write_target(arguments["working_directory"], file_path)
    if validation_error is not None:
        return validation_error
    return ApprovalRequest.for_write(
        call_id=call_id,
        target=file_path,
        content_length=len(content),
    )


def _execution_approval_request(
    call_id: str,
    name: str,
    arguments: dict[str, Any],
) -> ApprovalRequest | str:
    file_path, execution_args = arguments["file_path"], arguments.get("args")
    if not isinstance(file_path, str):
        return f'Error: invalid arguments for "{name}": file_path must be a string'
    normalized_args = _execution_arguments(execution_args)
    if normalized_args is None:
        return f'Error: invalid arguments for "{name}": args must be a list of strings'
    error = validate_python_target(arguments["working_directory"], file_path, normalized_args)
    if error is not None:
        return error
    return ApprovalRequest.for_execution(
        call_id=call_id,
        workspace=arguments["working_directory"],
        target=file_path,
        arguments=normalized_args,
    )


def _execution_arguments(value: Any) -> list[str] | None:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(arg, str) for arg in value):
        return None
    return value


def execute_prepared_tool(
    prepared: PreparedToolCall,
    verbose: bool = False,
) -> str:
    if verbose:
        print(f"Calling function: {format_prepared_call(prepared.approval_request)}")
    else:
        print(f" - Calling function: {prepared.name}")

    arguments = dict(prepared._arguments)
    try:
        return prepared._function(**arguments)
    except Exception as exc:
        return f'Error: invalid arguments for "{prepared.name}": {exc}'


def execute_tool(
    name: str,
    arguments_json: str,
    working_directory: str,
    verbose: bool = False,
) -> str:
    prepared = prepare_tool("direct-call", name, arguments_json, working_directory)
    if isinstance(prepared, str):
        return prepared
    return execute_prepared_tool(prepared, verbose)
