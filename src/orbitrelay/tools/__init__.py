import json
from collections.abc import Callable
from typing import Any

from .get_file_content import get_file_content
from .get_files_info import get_files_info
from .run_python_file import run_python_file
from .write_file import write_file


FUNCTIONS: dict[str, Callable[..., str]] = {
    "get_files_info": get_files_info,
    "get_file_content": get_file_content,
    "run_python_file": run_python_file,
    "write_file": write_file,
}


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


def execute_tool(
    name: str,
    arguments_json: str,
    working_directory: str,
    verbose: bool = False,
) -> str:
    function = FUNCTIONS.get(name)
    if function is None:
        return f'Error: unknown function "{name}"'

    try:
        arguments = json.loads(arguments_json)
    except (json.JSONDecodeError, TypeError) as exc:
        return f'Error: invalid arguments for "{name}": {exc}'

    if not isinstance(arguments, dict):
        return f'Error: invalid arguments for "{name}": expected a JSON object'

    arguments["working_directory"] = working_directory

    if verbose:
        visible_arguments = {
            key: value for key, value in arguments.items() if key != "working_directory"
        }
        print(f"Calling function: {name}({visible_arguments})")
    else:
        print(f" - Calling function: {name}")

    try:
        return function(**arguments)
    except Exception as exc:
        return f'Error: invalid arguments for "{name}": {exc}'
