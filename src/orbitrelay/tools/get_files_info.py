import os
import stat

from .path_safety import resolve_path_within

def get_files_info(working_directory, directory="."):
	try:
		_working_dir, target_dir, valid_target_dir = resolve_path_within(
			working_directory, directory
		)
		if not valid_target_dir:
			return f'Error: Cannot list "{directory}" as it is outside the permitted working directory'

		if not os.path.isdir(target_dir):
			return f'Error: "{directory}" is not a directory'

		entries = []
		for name in sorted(os.listdir(target_dir)):
			item_path = os.path.join(target_dir, name)
			item_stat = os.lstat(item_path)
			file_size = item_stat.st_size
			is_dir = stat.S_ISDIR(item_stat.st_mode)
			entries.append(f"- {name}: file_size={file_size} bytes, is_dir={is_dir}")

		return "\n".join(entries)
	except Exception as e:
		return f"Error: {e}"
