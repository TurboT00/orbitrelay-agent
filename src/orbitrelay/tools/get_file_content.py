import os
from ..config import MAX_CHARS
from .path_safety import resolve_path_within


def get_file_content(working_directory, file_path):
    try:
        _working_dir, target_file, valid_target_file = resolve_path_within(
            working_directory, file_path
        )
        if not valid_target_file:
            return f'Error: Cannot read "{file_path}" as it is outside the permitted working directory'

        if not os.path.isfile(target_file):
            return f'Error: File not found or is not a regular file: "{file_path}"'

        with open(target_file, "r", encoding="utf-8") as file:
            content = file.read(MAX_CHARS)
            if file.read(1):
                content += f'[...File "{file_path}" truncated at {MAX_CHARS} characters]'
            return content
    except Exception as e:
        return f"Error: {e}"
