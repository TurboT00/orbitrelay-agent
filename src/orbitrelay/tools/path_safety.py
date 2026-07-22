import os


def resolve_path_within(
    working_directory: str, relative_path: str
) -> tuple[str, str, bool]:
    working_directory_real = os.path.realpath(working_directory)
    target_real = os.path.realpath(
        os.path.join(working_directory_real, relative_path)
    )

    try:
        is_within = (
            os.path.commonpath([working_directory_real, target_real])
            == working_directory_real
        )
    except ValueError:
        is_within = False

    return working_directory_real, target_real, is_within
