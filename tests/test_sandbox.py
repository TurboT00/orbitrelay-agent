import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orbitrelay.tools.get_file_content import get_file_content
from orbitrelay.tools.get_files_info import get_files_info
from orbitrelay.tools.run_python_file import run_python_file
from orbitrelay.tools.write_file import write_file


class SandboxSymlinkTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_root = Path(self.temporary_directory.name)
        self.sandbox = temporary_root / "sandbox"
        self.outside = temporary_root / "outside"
        self.sandbox.mkdir()
        self.outside.mkdir()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def make_symlink(self, target: Path, link: Path):
        try:
            link.symlink_to(target, target_is_directory=target.is_dir())
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")

    def test_read_rejects_symlink_to_outside_file(self):
        outside_file = self.outside / "secret.txt"
        outside_file.write_text("secret", encoding="utf-8")
        self.make_symlink(outside_file, self.sandbox / "secret-link.txt")

        result = get_file_content(str(self.sandbox), "secret-link.txt")

        self.assertIn("outside the permitted working directory", result)
        self.assertNotEqual(result, "secret")

    def test_listing_rejects_symlink_to_outside_directory(self):
        (self.outside / "secret.txt").write_text("secret", encoding="utf-8")
        self.make_symlink(self.outside, self.sandbox / "outside-link")

        result = get_files_info(str(self.sandbox), "outside-link")

        self.assertIn("outside the permitted working directory", result)
        self.assertNotIn("secret.txt", result)

    def test_execution_rejects_symlink_to_outside_script(self):
        outside_script = self.outside / "outside.py"
        outside_script.write_text("print('escaped')", encoding="utf-8")
        self.make_symlink(outside_script, self.sandbox / "outside.py")

        result = run_python_file(str(self.sandbox), "outside.py")

        self.assertIn("outside the permitted working directory", result)
        self.assertNotIn("escaped", result)

    def test_execution_uses_current_interpreter_without_python_on_path(self):
        script = self.sandbox / "inside.py"
        script.write_text("print('worked')", encoding="utf-8")

        with patch.dict(os.environ, {"PATH": ""}):
            result = run_python_file(str(self.sandbox), "inside.py")

        self.assertEqual(result, "STDOUT:\nworked\n")

    def test_write_rejects_symlink_to_outside_file(self):
        outside_file = self.outside / "secret.txt"
        outside_file.write_text("original", encoding="utf-8")
        self.make_symlink(outside_file, self.sandbox / "secret-link.txt")

        result = write_file(str(self.sandbox), "secret-link.txt", "overwritten")

        self.assertIn("outside the permitted working directory", result)
        self.assertEqual(outside_file.read_text(encoding="utf-8"), "original")

    def test_write_rejects_symlinked_parent_directory(self):
        self.make_symlink(self.outside, self.sandbox / "outside-link")

        result = write_file(
            str(self.sandbox), "outside-link/new.txt", "must not escape"
        )

        self.assertIn("outside the permitted working directory", result)
        self.assertFalse((self.outside / "new.txt").exists())

    def test_listing_does_not_follow_symlink_entries(self):
        outside_directory = self.outside / "directory"
        outside_directory.mkdir()
        self.make_symlink(outside_directory, self.sandbox / "directory-link")

        result = get_files_info(str(self.sandbox))

        self.assertIn("directory-link", result)
        self.assertIn("is_dir=False", result)


if __name__ == "__main__":
    unittest.main()
