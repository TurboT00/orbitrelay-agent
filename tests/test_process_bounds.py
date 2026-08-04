from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from orbitrelay.codex_bridge import CodexBridge, CodexBridgeError
from orbitrelay.process_bounds import (
    bound_text,
    run_bounded_subprocess,
)
from orbitrelay.tools.run_python_file import run_python_file


class ProcessBoundsUnitTests(unittest.TestCase):
    def test_bound_text_reports_truncation(self) -> None:
        text, truncated = bound_text("abcdef", 4)
        self.assertEqual(text, "abcd")
        self.assertTrue(truncated)
        text, truncated = bound_text("hi", 10)
        self.assertEqual(text, "hi")
        self.assertFalse(truncated)

    def test_run_bounded_subprocess_truncates_and_drains(self) -> None:
        script = textwrap.dedent(
            """
            import sys
            sys.stdout.write("S" * 1000 + "SENTINEL_STDOUT_TAIL")
            sys.stderr.write("E" * 1000 + "SENTINEL_STDERR_TAIL")
            """
        )
        result = run_bounded_subprocess(
            ["python", "-c", script],
            max_stdout_chars=50,
            max_stderr_chars=40,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.stdout_truncated)
        self.assertTrue(result.stderr_truncated)
        self.assertEqual(len(result.stdout), 50)
        self.assertEqual(len(result.stderr), 40)
        self.assertNotIn("SENTINEL_STDOUT_TAIL", result.stdout)
        self.assertNotIn("SENTINEL_STDERR_TAIL", result.stderr)
        formatted = result.format_tool_output()
        self.assertIn("stdout truncated", formatted)
        self.assertIn("stderr truncated", formatted)
        self.assertNotIn("SENTINEL_STDOUT_TAIL", formatted)
        self.assertNotIn("SENTINEL_STDERR_TAIL", formatted)

    def test_run_bounded_subprocess_timeout(self) -> None:
        result = run_bounded_subprocess(
            ["python", "-c", "import time; time.sleep(5)"],
            timeout=0.2,
            max_stdout_chars=100,
            max_stderr_chars=100,
        )
        self.assertTrue(result.timed_out)
        self.assertIn("timed out", result.format_tool_output().lower())
        self.assertNotIn("SECRET", result.format_tool_output())


class RunPythonBoundsTests(unittest.TestCase):
    def test_python_tool_bounds_large_output(self) -> None:
        with tempfile.TemporaryDirectory() as workspace:
            path = Path(workspace) / "big.py"
            path.write_text(
                'print("HEAD" + "X" * 5000 + "TAIL_SENTINEL")\n'
                'import sys\n'
                'print("EHEAD" + "Y" * 5000 + "ETAIL_SENTINEL", file=sys.stderr)\n',
                encoding="utf-8",
            )
            output = run_python_file(
                workspace,
                "big.py",
                max_stdout_chars=80,
                max_stderr_chars=60,
            )
            self.assertIn("HEAD", output)
            self.assertIn("truncated", output.lower())
            self.assertNotIn("TAIL_SENTINEL", output)
            self.assertNotIn("ETAIL_SENTINEL", output)
            self.assertLessEqual(len(output), 80 + 60 + 400)

    def test_python_tool_timeout_is_truthful(self) -> None:
        with tempfile.TemporaryDirectory() as workspace:
            path = Path(workspace) / "slow.py"
            path.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
            output = run_python_file(workspace, "slow.py", timeout=0.2)
            self.assertIn("timed out", output.lower())
            self.assertNotIn("Traceback", output)


class CodexBoundsTests(unittest.TestCase):
    def test_codex_exec_bounds_error_detail_without_discarded_sentinel(self) -> None:
        huge = "KEEP" + ("Z" * 5000) + "DISCARD_SENTINEL"

        def runner(argv, **kwargs):
            command = list(argv)
            if command[1:2] == ["--version"]:
                return subprocess.CompletedProcess(
                    args=command, returncode=0, stdout="codex-cli 1.0.0\n", stderr=""
                )
            completed = subprocess.CompletedProcess(
                args=command,
                returncode=2,
                stdout="",
                stderr=huge,
            )
            completed.timed_out = False
            completed.stdout_truncated = False
            completed.stderr_truncated = True
            return completed

        bridge = CodexBridge(
            which=lambda name: "/bin/codex" if name == "codex" else None,
            runner=runner,
        )
        with tempfile.TemporaryDirectory() as workspace:
            with self.assertRaises(CodexBridgeError) as raised:
                bridge.exec("do work", workspace, require_login=False)
        message = str(raised.exception)
        self.assertIn("KEEP", message)
        self.assertNotIn("DISCARD_SENTINEL", message)
        self.assertLessEqual(len(message), 400)


if __name__ == "__main__":
    unittest.main()
