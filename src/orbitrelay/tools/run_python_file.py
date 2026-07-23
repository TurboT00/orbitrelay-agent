import os
import subprocess
import sys

from .path_safety import resolve_path_within


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
            return f'Error: Cannot execute "{file_path}" as it is outside the permitted working directory'
        if not os.path.isfile(absolute_file_path):
            return f'Error: "{file_path}" does not exist or is not a regular file'
        if not absolute_file_path.endswith(".py"):
            return f'Error: "{file_path}" is not a Python file'
        if args is not None and (
            not isinstance(args, list) or not all(isinstance(arg, str) for arg in args)
        ):
            return "Error: args must be a list of strings"
    except Exception as exc:
        return f"Error: {exc}"
    return None


def run_python_file(
    working_directory: str,
    file_path: str,
    args: list[str] | None = None,
) -> str:
    try:
        validation_error = validate_python_target(working_directory, file_path, args)
        if validation_error is not None:
            return validation_error
        if args is None:
            args = []

        working_dir_abs, absolute_file_path, valid_target_file = resolve_path_within(
            working_directory, file_path
        )
        if not valid_target_file:  # Recheck confinement at the execution boundary.
            return f'Error: Cannot execute "{file_path}" as it is outside the permitted working directory'

        command = [sys.executable, absolute_file_path]
        if args:
            command.extend(args)

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=working_dir_abs,
            timeout=30,
        )

        output_parts = []
        if completed.returncode != 0:
            output_parts.append(f"Process exited with code {completed.returncode}")

        if completed.stdout:
            output_parts.append(f"STDOUT:\n{completed.stdout}")

        if completed.stderr:
            output_parts.append(f"STDERR:\n{completed.stderr}")

        if not completed.stdout and not completed.stderr:
            output_parts.append("No output produced")

        return "\n".join(output_parts)
    except Exception as exc:
        return f"Error: executing Python file: {exc}"
