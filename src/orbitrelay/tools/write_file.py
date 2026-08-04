# story: e02s01
# story: e08s06

from __future__ import annotations

import os
import tempfile
from contextlib import suppress

from .path_safety import resolve_path_within


def validate_write_target(working_directory: str, file_path: str) -> str | None:
    try:
        _working_dir, target_file, valid_target_file = resolve_path_within(
            working_directory, file_path
        )
        if not valid_target_file:
            return (
                f'Error: Cannot write to "{file_path}" as it is outside the '
                f"permitted working directory"
            )

        if os.path.isdir(target_file):
            return f'Error: Cannot write to "{file_path}" as it is a directory'
    except Exception as exc:
        return f"Error: {exc}"

    return None


def write_file(working_directory: str, file_path: str, content: str) -> str:
    """Write content atomically inside the workspace, or leave prior state intact."""
    temporary_path: str | None = None
    try:
        validation_error = validate_write_target(working_directory, file_path)
        if validation_error is not None:
            return validation_error

        working_dir_real, target_file, valid_target_file = resolve_path_within(
            working_directory, file_path
        )
        if not valid_target_file:
            return (
                f'Error: Cannot write to "{file_path}" as it is outside the '
                f"permitted working directory"
            )

        parent_dir = os.path.dirname(target_file) or working_dir_real
        confinement_error = _ensure_parent_within_workspace(
            working_directory, file_path, parent_dir, working_dir_real
        )
        if confinement_error is not None:
            return confinement_error

        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".orbitrelay-write-",
            suffix=".tmp",
            dir=parent_dir,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            with suppress(OSError):
                if temporary_path is not None:
                    os.unlink(temporary_path)
            raise

        # Re-validate immediately before commit (validation-to-use / TOCTOU).
        commit_error = _revalidate_before_replace(
            working_directory,
            file_path,
            expected_target=target_file,
            working_dir_real=working_dir_real,
        )
        if commit_error is not None:
            with suppress(OSError):
                os.unlink(temporary_path)
            return commit_error

        os.replace(temporary_path, target_file)
        temporary_path = None
        return (
            f'Successfully wrote to "{file_path}" '
            f"({len(content)} characters written)"
        )
    except Exception as exc:
        if temporary_path is not None:
            with suppress(OSError):
                os.unlink(temporary_path)
        return f"Error: {exc}"


def _ensure_parent_within_workspace(
    working_directory: str,
    file_path: str,
    parent_dir: str,
    working_dir_real: str,
) -> str | None:
    try:
        if not os.path.isdir(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        parent_real = os.path.realpath(parent_dir)
        if (
            os.path.commonpath([working_dir_real, parent_real])
            != working_dir_real
        ):
            return (
                f'Error: Cannot write to "{file_path}" as it is outside the '
                f"permitted working directory"
            )
    except Exception as exc:
        return f"Error: {exc}"
    return None


def _revalidate_before_replace(
    working_directory: str,
    file_path: str,
    *,
    expected_target: str,
    working_dir_real: str,
) -> str | None:
    """Fail closed when the path escapes or changes after initial validation."""
    try:
        # Reject symlink final component at the logical join path when present.
        logical = os.path.join(os.path.realpath(working_directory), file_path)
        if os.path.lexists(logical) and os.path.islink(logical):
            link_target = os.path.realpath(logical)
            if (
                os.path.commonpath([working_dir_real, link_target])
                != working_dir_real
            ):
                return (
                    f'Error: Cannot write to "{file_path}" as it is outside the '
                    f"permitted working directory"
                )

        again_working, again_target, again_valid = resolve_path_within(
            working_directory, file_path
        )
        del again_working
        if not again_valid:
            return (
                f'Error: Cannot write to "{file_path}" as it is outside the '
                f"permitted working directory"
            )
        if os.path.realpath(again_target) != os.path.realpath(expected_target):
            return (
                f'Error: Cannot write to "{file_path}" because the target path '
                f"changed after validation"
            )
        if os.path.isdir(again_target):
            return f'Error: Cannot write to "{file_path}" as it is a directory'
    except Exception as exc:
        return f"Error: {exc}"
    return None
