import os

from .path_safety import resolve_path_within


def validate_write_target(working_directory, file_path):
    try:
        _working_dir, target_file, valid_target_file = resolve_path_within(
            working_directory, file_path
        )
        if not valid_target_file:
            return f'Error: Cannot write to "{file_path}" as it is outside the permitted working directory'

        if os.path.isdir(target_file):
            return f'Error: Cannot write to "{file_path}" as it is a directory'
    except Exception as exc:
        return f"Error: {exc}"

    return None


def write_file(working_directory, file_path, content):
    try:
        validation_error = validate_write_target(working_directory, file_path)
        if validation_error is not None:
            return validation_error

        _working_dir, target_file, _valid_target_file = resolve_path_within(
            working_directory, file_path
        )

        parent_dir = os.path.dirname(target_file)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        with open(target_file, "w", encoding="utf-8") as file:
            file.write(content)

        return f'Successfully wrote to "{file_path}" ({len(content)} characters written)'
    except Exception as e:
        return f"Error: {e}"
