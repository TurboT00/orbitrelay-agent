"""Contracts for macOS Python 3.12-3.14 matrix qualification (e09s03)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.python_matrix import (
    MatrixError,
    apply_candidate_floor,
    read_python_classifiers,
    read_requires_python,
    stage_candidate_tree,
    validate_matrix_evidence,
    write_matrix_evidence,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_SCRIPT = REPO_ROOT / "scripts" / "check-python-matrix.sh"
HELPER = REPO_ROOT / "scripts" / "python_matrix.py"


class PythonMatrixHelperTests(unittest.TestCase):
    def test_tracked_metadata_currently_readable(self) -> None:
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        requires = read_requires_python(text)
        classifiers = read_python_classifiers(text)
        self.assertTrue(requires.startswith(">="))
        self.assertTrue(any(item.startswith("3.") for item in classifiers))

    def test_tracked_floor_is_qualified_range(self) -> None:
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertEqual(read_requires_python(text), ">=3.12")
        self.assertEqual(
            read_python_classifiers(text),
            ("3.12", "3.13", "3.14"),
        )
        evidence = REPO_ROOT / "specs" / "verifications" / "python-matrix-evidence.json"
        self.assertTrue(evidence.is_file())
        validate_matrix_evidence(evidence)

    def test_apply_candidate_floor_rewrites_requires_and_classifiers(self) -> None:
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        updated = apply_candidate_floor(text, "3.12")
        self.assertEqual(read_requires_python(updated), ">=3.12")
        self.assertEqual(
            read_python_classifiers(updated),
            ("3.12", "3.13", "3.14"),
        )
        self.assertIn('python_version = "3.12"', updated)
        # Original snapshot unchanged.
        original = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertEqual(original, text)

    def test_stage_candidate_does_not_mutate_tracked_tree(self) -> None:
        before = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        before_lock = (REPO_ROOT / "uv.lock").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "candidate"
            stage_candidate_tree(REPO_ROOT, destination, floor="3.12")
            staged = (destination / "pyproject.toml").read_text(encoding="utf-8")
            self.assertEqual(read_requires_python(staged), ">=3.12")
            self.assertTrue((destination / "src" / "orbitrelay").is_dir())
            self.assertFalse((destination / ".git").exists())
        after = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        after_lock = (REPO_ROOT / "uv.lock").read_bytes()
        self.assertEqual(before, after)
        self.assertEqual(before_lock, after_lock)

    def test_matrix_evidence_round_trip_and_secret_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "matrix.json"
            write_matrix_evidence(
                path,
                revision="abc123",
                floor="3.12",
                tracked_requires_python=">=3.14",
                results=[
                    {"python": "3.12", "status": "passed"},
                    {"python": "3.13", "status": "passed"},
                    {"python": "3.14", "status": "passed"},
                ],
            )
            validate_matrix_evidence(path, expected_revision="abc123")
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["results"][0]["api_key"] = "secret"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(MatrixError):
                validate_matrix_evidence(path, expected_revision="abc123")

    def test_matrix_script_is_executable_and_documents_candidate_mode(self) -> None:
        mode = MATRIX_SCRIPT.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)
        text = MATRIX_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("--candidate-floor", text)
        self.assertIn("--automated-only", text)
        self.assertIn("3.12", text)
        self.assertIn("3.13", text)
        self.assertIn("3.14", text)
        self.assertIn("uv sync --locked --python", text)

    def test_helper_cli_show_tracked(self) -> None:
        completed = subprocess.run(
            ["uv", "run", "python", str(HELPER), "show-tracked"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("requires-python=", completed.stdout)


if __name__ == "__main__":
    unittest.main()
