import os
import stat

from .path_safety import resolve_path_within
from .workspace_privacy import (
    OMITTED_ENTRIES_LINE,
    deny_protected_listing,
    filter_listing_names,
    workspace_privacy_policy,
)


def get_files_info(working_directory, directory="."):
    try:
        _working_dir, target_dir, valid_target_dir = resolve_path_within(
            working_directory, directory
        )
        if not valid_target_dir:
            return (
                f'Error: Cannot list "{directory}" as it is outside the '
                "permitted working directory"
            )

        if not os.path.isdir(target_dir):
            return f'Error: "{directory}" is not a directory'

        policy_error = workspace_privacy_policy(working_directory).policy_error_message()
        if policy_error is not None:
            return policy_error

        denial = deny_protected_listing(working_directory, directory)
        if denial is not None:
            return denial

        names = sorted(os.listdir(target_dir))
        visible_names, omitted = filter_listing_names(
            working_directory, directory, names
        )
        entries = []
        for name in visible_names:
            item_path = os.path.join(target_dir, name)
            item_stat = os.lstat(item_path)
            file_size = item_stat.st_size
            is_dir = stat.S_ISDIR(item_stat.st_mode)
            entries.append(
                f"- {name}: file_size={file_size} bytes, is_dir={is_dir}"
            )
        if omitted:
            entries.append(f"- ({omitted} {OMITTED_ENTRIES_LINE})")
        return "\n".join(entries)
    except Exception as e:
        return f"Error: {e}"
