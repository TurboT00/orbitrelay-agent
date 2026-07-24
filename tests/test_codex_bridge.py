# story: e03s04
# story: e03s05
# story: e03s06

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orbitrelay import cli
from orbitrelay.codex_bridge import (
    CODEX_INSTALL_GUIDANCE,
    FORBIDDEN_EXEC_FLAGS,
    CodexBridge,
    CodexBridgeError,
)
from orbitrelay.codex_cli import run_codex_cli


class RecordingRunner:
    def __init__(self, behaviors=None) -> None:
        self.calls: list[list[str]] = []
        self.behaviors = list(behaviors or [])

    def __call__(self, argv, **kwargs):
        command = list(argv)
        self.calls.append(command)
        if self.behaviors:
            behavior = self.behaviors.pop(0)
            if callable(behavior):
                return behavior(command, **kwargs)
            return behavior
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def _completed(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class CodexBridgeTests(unittest.TestCase):
    def test_detect_available_version(self) -> None:
        runner = RecordingRunner(
            behaviors=[_completed(stdout="codex-cli 0.1.0-test\n")]
        )
        bridge = CodexBridge(
            which=lambda name: "/tmp/fake-codex" if name == "codex" else None,
            runner=runner,
        )

        installation = bridge.detect()

        self.assertTrue(installation.available)
        self.assertEqual(installation.path, "/tmp/fake-codex")
        self.assertEqual(installation.version, "codex-cli 0.1.0-test")
        self.assertEqual(runner.calls, [["/tmp/fake-codex", "--version"]])

    def test_detect_missing_codex(self) -> None:
        bridge = CodexBridge(which=lambda _name: None, runner=RecordingRunner())
        installation = bridge.detect()
        self.assertFalse(installation.available)
        self.assertIsNone(installation.path)
        text = "\n".join(installation.status_lines())
        self.assertIn("unavailable", text)
        self.assertIn(CODEX_INSTALL_GUIDANCE, text)

    def test_login_logout_status_argv(self) -> None:
        runner = RecordingRunner(
            behaviors=[
                _completed(stdout="codex-cli 1.0.0\n"),  # detect for login
                _completed(),  # login
                _completed(stdout="codex-cli 1.0.0\n"),  # detect for device login
                _completed(),  # device login
                _completed(stdout="codex-cli 1.0.0\n"),  # detect status
                _completed(returncode=0),  # login status
                _completed(stdout="codex-cli 1.0.0\n"),  # detect logout
                _completed(),  # logout
            ]
        )
        bridge = CodexBridge(
            which=lambda name: "/bin/codex" if name == "codex" else None,
            runner=runner,
        )

        self.assertEqual(bridge.login(), 0)
        self.assertEqual(bridge.login(device_auth=True), 0)
        self.assertEqual(bridge.login_status(), 0)
        self.assertEqual(bridge.logout(), 0)

        self.assertIn(["/bin/codex", "login"], runner.calls)
        self.assertIn(["/bin/codex", "login", "--device-auth"], runner.calls)
        self.assertIn(["/bin/codex", "login", "status"], runner.calls)
        self.assertIn(["/bin/codex", "logout"], runner.calls)

    def test_exec_success_jsonl_and_argv_shape(self) -> None:
        def exec_behavior(command, **kwargs):
            del kwargs
            if command[1] == "--version":
                return _completed(stdout="codex-cli 1.2.3\n")
            if command[1:3] == ["login", "status"]:
                return _completed(returncode=0)
            if command[1] == "exec":
                # write final message file from -o/--output-last-message
                output_flag = command.index("--output-last-message")
                Path(command[output_flag + 1]).write_text(
                    "final from codex\n", encoding="utf-8"
                )
                return _completed(
                    returncode=0,
                    stdout=(
                        '{"type":"item.completed","item":{"type":"agent_message",'
                        '"text":"from jsonl"}}\n'
                    ),
                )
            raise AssertionError(command)

        runner = RecordingRunner(
            behaviors=[exec_behavior, exec_behavior, exec_behavior, exec_behavior]
        )
        bridge = CodexBridge(
            which=lambda name: "/usr/local/bin/codex" if name == "codex" else None,
            runner=runner,
        )
        with tempfile.TemporaryDirectory() as workspace:
            result = bridge.exec("summarize repo", workspace)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.final_message, "final from codex")
        exec_call = next(call for call in runner.calls if call[1] == "exec")
        self.assertEqual(exec_call[0], "/usr/local/bin/codex")
        self.assertIn("exec", exec_call)
        self.assertIn("--json", exec_call)
        self.assertIn("--cd", exec_call)
        self.assertIn(str(Path(workspace).resolve()), exec_call)
        self.assertIn("summarize repo", exec_call)
        for flag in FORBIDDEN_EXEC_FLAGS:
            self.assertNotIn(flag, exec_call)

    def test_exec_requires_login(self) -> None:
        runner = RecordingRunner(
            behaviors=[
                _completed(stdout="codex-cli 1.0.0\n"),  # exec detect
                _completed(stdout="codex-cli 1.0.0\n"),  # login_status detect
                _completed(returncode=1, stderr="not logged in"),
            ]
        )
        bridge = CodexBridge(
            which=lambda name: "/bin/codex" if name == "codex" else None,
            runner=runner,
        )
        with tempfile.TemporaryDirectory() as workspace:
            with self.assertRaisesRegex(CodexBridgeError, "not logged in"):
                bridge.exec("task", workspace)

    def test_default_exec_argv_refuses_yolo(self) -> None:
        bridge = CodexBridge(
            which=lambda name: "/bin/codex" if name == "codex" else None,
            runner=RecordingRunner(),
        )
        argv = bridge.build_exec_argv(
            path="/bin/codex",
            prompt="hi",
            workspace="/tmp/ws",
        )
        for flag in FORBIDDEN_EXEC_FLAGS:
            self.assertNotIn(flag, argv)

    def test_cli_status_and_main_dispatch(self) -> None:
        runner = RecordingRunner(
            behaviors=[_completed(stdout="codex-cli 9.9.9\n")]
        )
        bridge = CodexBridge(
            which=lambda name: "/opt/codex" if name == "codex" else None,
            runner=runner,
        )
        output = StringIO()
        code = run_codex_cli(["status"], bridge=bridge, output=output)
        self.assertEqual(code, 0)
        self.assertIn("available", output.getvalue())
        self.assertIn("codex-cli 9.9.9", output.getvalue())

    def test_main_dispatches_codex_status_missing(self) -> None:
        output = StringIO()
        with redirect_stdout(output), patch(
            "orbitrelay.codex_bridge.shutil.which", return_value=None
        ):
            code = cli.main(["codex", "status"])
        self.assertEqual(code, 1)
        self.assertIn("unavailable", output.getvalue())
        self.assertIn("Install the official Codex CLI", output.getvalue())

    def test_fake_path_script_integration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "codex"
            binary.write_text(
                "#!/bin/sh\n"
                'if [ \"$1\" = \"--version\" ]; then echo \"codex-cli path-test\"; exit 0; fi\n'
                'if [ \"$1\" = \"login\" ] && [ \"$2\" = \"status\" ]; then exit 0; fi\n'
                'if [ \"$1\" = \"exec\" ]; then\n'
                '  while [ \"$#\" -gt 0 ]; do\n'
                '    if [ \"$1\" = \"--output-last-message\" ]; then echo path-exec-ok > \"$2\"; fi\n'
                '    shift\n'
                "  done\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
            bridge = CodexBridge(
                which=lambda name: str(binary) if name == "codex" else None
            )
            installation = bridge.detect()
            self.assertTrue(installation.available)
            self.assertEqual(installation.version, "codex-cli path-test")
            result = bridge.exec("do work", directory)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.final_message, "path-exec-ok")

    def test_source_never_reads_auth_json(self) -> None:
        source = Path("src/orbitrelay/codex_bridge.py").read_text(encoding="utf-8")
        self.assertNotIn("auth.json", source)
        self.assertNotIn("CODEX_HOME", source)


if __name__ == "__main__":
    unittest.main()
