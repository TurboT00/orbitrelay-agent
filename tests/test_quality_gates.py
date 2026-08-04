"""Contracts for terminal Ruff/mypy release gates (e09s01)."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check.sh"


class QualityGateConfigurationTests(unittest.TestCase):
    def test_check_script_runs_ruff_and_mypy_as_named_stages(self) -> None:
        text = CHECK_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('section "Running Ruff"', text)
        self.assertIn("uv run ruff check .", text)
        self.assertIn('section "Running mypy"', text)
        self.assertIn("uv run mypy src/orbitrelay", text)
        self.assertNotIn("ruff check . || true", text)
        self.assertNotIn("mypy src/orbitrelay || true", text)

    def test_check_script_is_executable(self) -> None:
        mode = CHECK_SCRIPT.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)


class QualityGateRegressionTests(unittest.TestCase):
    def test_ruff_fails_on_controlled_lint_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "bad_lint.py"
            fixture.write_text("import os\n\nprint(undefined_name)\n", encoding="utf-8")
            completed = subprocess.run(
                ["uv", "run", "ruff", "check", str(fixture)],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertTrue(
            "F821" in completed.stdout
            or "F821" in completed.stderr
            or "undefined" in (completed.stdout + completed.stderr).lower()
        )

    def test_mypy_fails_on_controlled_type_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "bad_types.py"
            fixture.write_text(
                "def add(a: int, b: int) -> int:\n    return a + b\n\nreveal = add('x', 1)\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                ["uv", "run", "mypy", str(fixture)],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        combined = completed.stdout + completed.stderr
        self.assertTrue(
            "error:" in combined.lower() or "incompatible" in combined.lower(),
            combined,
        )


if __name__ == "__main__":
    unittest.main()
