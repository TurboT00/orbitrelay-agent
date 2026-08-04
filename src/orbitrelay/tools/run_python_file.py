# story: e02s02
# story: e08s05

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence

from ..process_bounds import (
    DEFAULT_MAX_STDERR_CHARS,
    DEFAULT_MAX_STDOUT_CHARS,
    DEFAULT_PROCESS_TIMEOUT_SECONDS,
    BoundedProcessResult,
    run_bounded_subprocess,
)
from .path_safety import resolve_path_within

ProcessRunner = Callable[..., BoundedProcessResult]


def validate_python_target(
    working_directory: str,
    file_path: str,
    args: list[str] | None = None,
) -> str | None:
    try:
        _working_dir, absolute_file_path, valid_target_file = resolve_path_within(
            working_directory, file_path
        )
        if not valid_target_file:
            return _outside_workspace_error(file_path)
        if not os.path.isfile(absolute_file_path):
            return f'Error: "{file_path}" does not exist or is not a regular file'
        if not absolute_file_path.endswith(".py"):
            return f'Error: "{file_path}" is not a Python file'
        if not _valid_python_args(args):
            return "Error: args must be a list of strings"
    except Exception as exc:
        return f"Error: {exc}"
    return None


def run_python_file(
    working_directory: str,
    file_path: str,
    args: list[str] | None = None,
    *,
    runner: ProcessRunner | None = None,
    timeout: float = DEFAULT_PROCESS_TIMEOUT_SECONDS,
    max_stdout_chars: int = DEFAULT_MAX_STDOUT_CHARS,
    max_stderr_chars: int = DEFAULT_MAX_STDERR_CHARS,
) -> str:
    try:
        validation_error = validate_python_target(working_directory, file_path, args)
        if validation_error is not None:
            return validation_error
        return _execute_python_file(
            working_directory,
            file_path,
            args or [],
            runner=runner,
            timeout=timeout,
            max_stdout_chars=max_stdout_chars,
            max_stderr_chars=max_stderr_chars,
        )
    except Exception as exc:
        return f"Error: executing Python file: {exc}"


def _execute_python_file(
    working_directory: str,
    file_path: str,
    args: list[str],
    *,
    runner: ProcessRunner | None,
    timeout: float,
    max_stdout_chars: int,
    max_stderr_chars: int,
) -> str:
    working_dir_abs, absolute_file_path, valid_target_file = resolve_path_within(
        working_directory, file_path
    )
    if not valid_target_file:  # Recheck confinement at the execution boundary.
        return _outside_workspace_error(file_path)
    argv: Sequence[str] = [sys.executable, absolute_file_path, *args]
    active = runner or run_bounded_subprocess
    result = active(
        argv,
        cwd=working_dir_abs,
        timeout=timeout,
        max_stdout_chars=max_stdout_chars,
        max_stderr_chars=max_stderr_chars,
    )
    return result.format_tool_output()


def _outside_workspace_error(file_path: str) -> str:
    return (
        f'Error: Cannot execute "{file_path}" as it is outside the permitted '
        f"working directory"
    )


def _valid_python_args(args: list[str] | None) -> bool:
    return args is None or (
        isinstance(args, list) and all(isinstance(arg, str) for arg in args)
    )
