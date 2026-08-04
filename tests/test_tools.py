# story: e02s02

import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from orbitrelay.tools import (
    FUNCTIONS,
    TOOL_DEFINITIONS,
    PreparedToolCall,
    execute_prepared_tool,
    execute_tool,
    prepare_tool,
)

WORKING_DIRECTORY = "/workspace"


class ToolDefinitionsTests(unittest.TestCase):
    def test_defines_exactly_the_supported_functions(self):
        names = [definition["function"]["name"] for definition in TOOL_DEFINITIONS]

        self.assertEqual(
            names,
            [
                "get_files_info",
                "get_file_content",
                "run_python_file",
                "write_file",
            ],
        )
        self.assertEqual(set(names), set(FUNCTIONS))

    def test_each_definition_uses_an_object_parameter_schema(self):
        for definition in TOOL_DEFINITIONS:
            with self.subTest(name=definition["function"]["name"]):
                self.assertEqual(definition["type"], "function")
                parameters = definition["function"]["parameters"]
                self.assertEqual(parameters["type"], "object")
                self.assertIsInstance(parameters["properties"], dict)


class ExecuteToolTests(unittest.TestCase):
    def test_prepares_write_without_side_effect_until_execution(self):
        with tempfile.TemporaryDirectory() as workspace:
            target = Path(workspace, "notes.txt")

            prepared = prepare_tool(
                "call-1",
                "write_file",
                '{"file_path":"notes.txt","content":"hello"}',
                workspace,
            )

            if not isinstance(prepared, PreparedToolCall):
                self.fail(f"expected prepared call, got {prepared!r}")
            self.assertFalse(target.exists())

            result = execute_prepared_tool(prepared)

            self.assertEqual(
                result,
                'Successfully wrote to "notes.txt" (5 characters written)',
            )
            self.assertEqual(target.read_text(encoding="utf-8"), "hello")

    def test_prepares_python_execution_without_starting_a_process(self):
        with tempfile.TemporaryDirectory() as workspace:
            Path(workspace, "task.py").write_text("print('safe')", encoding="utf-8")

            with patch("orbitrelay.tools.run_python_file.run_bounded_subprocess") as run:
                prepared = prepare_tool(
                    "call-exec",
                    "run_python_file",
                    '{"file_path":"task.py","args":["--safe"]}',
                    workspace,
                )

            if not isinstance(prepared, PreparedToolCall):
                self.fail(f"expected prepared call, got {prepared!r}")
            run.assert_not_called()
            self.assertEqual(
                prepared.approval_request.safe_context,
                (
                    ("python", "current-interpreter"),
                    ("workspace", workspace),
                    ("file", "task.py"),
                    ("arguments", ("--safe",)),
                    ("argument_count", 1),
                ),
            )

    def test_rejects_invalid_python_execution_during_preparation(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root, "workspace")
            workspace.mkdir()
            Path(root, "outside.py").write_text("print('outside')", encoding="utf-8")
            Path(workspace, "notes.txt").write_text("not Python", encoding="utf-8")
            Path(workspace, "task.py").write_text("print('safe')", encoding="utf-8")
            cases = (
                ('{"file_path":"../outside.py"}', "outside the permitted"),
                ('{"file_path":"missing.py"}', "does not exist"),
                ('{"file_path":"notes.txt"}', "not a Python file"),
                ('{"file_path":"task.py","args":[7]}', "args must be a list of strings"),
            )

            with patch("orbitrelay.tools.run_python_file.run_bounded_subprocess") as run:
                for arguments, expected_error in cases:
                    with self.subTest(arguments=arguments):
                        prepared = prepare_tool(
                            "call-exec", "run_python_file", arguments, str(workspace)
                        )
                        if not isinstance(prepared, str):
                            self.fail(f"expected preparation error, got {prepared!r}")
                        self.assertIn(expected_error, prepared)

            run.assert_not_called()

    def test_rejects_unsafe_write_during_preparation(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root, "workspace")
            workspace.mkdir()
            outside_target = Path(root, "escaped.txt")

            prepared = prepare_tool(
                "call-1",
                "write_file",
                '{"file_path":"../escaped.txt","content":"blocked"}',
                str(workspace),
            )

            if not isinstance(prepared, str):
                self.fail(f"expected preparation error, got {prepared!r}")
            self.assertIn("outside the permitted working directory", prepared)
            self.assertFalse(outside_target.exists())

    def test_verbose_prepared_write_excludes_raw_content(self):
        secret_content = "provider-secret-value\x1b[31m"
        output = StringIO()

        with tempfile.TemporaryDirectory() as workspace:
            prepared = prepare_tool(
                "call-1",
                "write_file",
                '{"file_path":"notes.txt","content":"provider-secret-value\\u001b[31m"}',
                workspace,
            )
            if not isinstance(prepared, PreparedToolCall):
                self.fail(f"expected prepared call, got {prepared!r}")

            with redirect_stdout(output):
                execute_prepared_tool(prepared, verbose=True)

        visible_output = output.getvalue()
        self.assertNotIn(secret_content, visible_output)
        self.assertNotIn("provider-secret-value", visible_output)
        self.assertIn("notes.txt", visible_output)
        self.assertIn(str(len(secret_content)), visible_output)

    def test_verbose_prepared_execution_excludes_raw_arguments(self):
        secret_argument = "provider-secret-token"
        output = StringIO()

        with tempfile.TemporaryDirectory() as workspace:
            Path(workspace, "task.py").write_text("print('ok')", encoding="utf-8")
            prepared = prepare_tool(
                "call-exec",
                "run_python_file",
                '{"file_path":"task.py","args":["--token","provider-secret-token"]}',
                workspace,
            )
            if not isinstance(prepared, PreparedToolCall):
                self.fail(f"expected prepared call, got {prepared!r}")

            from orbitrelay.process_bounds import BoundedProcessResult

            with (
                patch(
                    "orbitrelay.tools.run_python_file.run_bounded_subprocess",
                    return_value=BoundedProcessResult(
                        returncode=0,
                        stdout="ok\n",
                        stderr="",
                        timed_out=False,
                        stdout_truncated=False,
                        stderr_truncated=False,
                        duration_seconds=0.01,
                        timeout_seconds=30.0,
                    ),
                ),
                redirect_stdout(output),
            ):
                execute_prepared_tool(prepared, verbose=True)

        visible_output = output.getvalue()
        self.assertNotIn(secret_argument, visible_output)
        self.assertNotIn("--token", visible_output)
        self.assertIn("task.py", visible_output)
        self.assertIn("argument_count=2", visible_output)

    def test_parses_arguments_and_injects_the_fixed_sandbox(self):
        received = {}

        def spy(**arguments):
            received.update(arguments)
            return "ok"

        with patch.dict(FUNCTIONS, {"get_file_content": spy}):
            result = execute_tool(
                "get_file_content",
                '{"file_path": "main.py"}',
                WORKING_DIRECTORY,
            )

        self.assertEqual(result, "ok")
        self.assertEqual(
            received,
            {"file_path": "main.py", "working_directory": WORKING_DIRECTORY},
        )

    def test_model_cannot_override_the_sandbox(self):
        received = {}

        def spy(**arguments):
            received.update(arguments)
            return "ok"

        with patch.dict(FUNCTIONS, {"get_files_info": spy}):
            execute_tool(
                "get_files_info",
                '{"directory": ".", "working_directory": "/tmp"}',
                WORKING_DIRECTORY,
            )

        self.assertEqual(received["working_directory"], WORKING_DIRECTORY)

    def test_unknown_function_returns_a_tool_error(self):
        result = execute_tool("missing", "{}", WORKING_DIRECTORY)

        self.assertEqual(result, 'Error: unknown function "missing"')

    def test_malformed_json_returns_a_tool_error(self):
        result = execute_tool("get_files_info", "{", WORKING_DIRECTORY)

        self.assertIn('Error: invalid arguments for "get_files_info"', result)

    def test_non_object_json_returns_a_tool_error(self):
        result = execute_tool("get_files_info", "[]", WORKING_DIRECTORY)

        self.assertEqual(
            result,
            'Error: invalid arguments for "get_files_info": expected a JSON object',
        )

    def test_missing_required_argument_returns_a_tool_error(self):
        result = execute_tool("get_file_content", "{}", WORKING_DIRECTORY)

        self.assertIn('Error: invalid arguments for "get_file_content"', result)
        self.assertIn("file_path", result)

    def test_unexpected_argument_returns_a_tool_error(self):
        result = execute_tool(
            "get_file_content",
            '{"file_path": "main.py", "extra": true}',
            WORKING_DIRECTORY,
        )

        self.assertIn('Error: invalid arguments for "get_file_content"', result)
        self.assertIn("extra", result)

    def test_handler_exception_returns_a_tool_error(self):
        def broken(**_arguments):
            raise ValueError("boom")

        with patch.dict(FUNCTIONS, {"get_files_info": broken}):
            result = execute_tool("get_files_info", "{}", WORKING_DIRECTORY)

        self.assertEqual(
            result, 'Error: invalid arguments for "get_files_info": boom'
        )

    def test_explicit_workspace_does_not_depend_on_process_cwd(self):
        original_directory = Path.cwd()
        with (
            tempfile.TemporaryDirectory() as workspace,
            tempfile.TemporaryDirectory() as other_directory,
        ):
            Path(workspace, "inside.txt").write_text("workspace data", encoding="utf-8")
            try:
                os.chdir(other_directory)
                result = execute_tool(
                    "get_file_content",
                    '{"file_path": "inside.txt"}',
                    workspace,
                )
            finally:
                os.chdir(original_directory)

        self.assertEqual(result, "workspace data")


    def test_write_is_atomic_on_replace_failure(self) -> None:
        from orbitrelay.tools.write_file import write_file

        with tempfile.TemporaryDirectory() as workspace:
            target = Path(workspace, "notes.txt")
            target.write_text("ORIGINAL", encoding="utf-8")
            with patch("orbitrelay.tools.write_file.os.replace", side_effect=OSError("interrupted")):
                result = write_file(workspace, "notes.txt", "NEW_CONTENT_SHOULD_NOT_LAND")
            self.assertTrue(result.startswith("Error:"))
            self.assertEqual(target.read_text(encoding="utf-8"), "ORIGINAL")
            # no leftover temp files with new content as the final name
            leftovers = list(Path(workspace).glob(".orbitrelay-write-*"))
            self.assertEqual(leftovers, [])

    def test_write_fails_if_target_becomes_outside_symlink(self) -> None:
        from orbitrelay.tools.write_file import write_file

        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root, "workspace")
            outside = Path(root, "outside")
            workspace.mkdir()
            outside.mkdir()
            outside_file = outside / "secret.txt"
            outside_file.write_text("SECRET", encoding="utf-8")
            # First create a normal file inside workspace
            inside = workspace / "target.txt"
            inside.write_text("inside", encoding="utf-8")

            real_resolve = __import__(
                "orbitrelay.tools.write_file", fromlist=["resolve_path_within"]
            ).resolve_path_within
            calls = {"n": 0}

            def flaky_resolve(working_directory, file_path):
                calls["n"] += 1
                # After initial validation/setup calls, swap target to outside symlink
                # so the pre-replace revalidation observes the escape.
                if calls["n"] >= 3 and inside.exists() and not inside.is_symlink():
                    inside.unlink()
                    try:
                        inside.symlink_to(outside_file)
                    except OSError as exc:
                        self.skipTest(f"symlinks unavailable: {exc}")
                return real_resolve(working_directory, file_path)

            with patch(
                "orbitrelay.tools.write_file.resolve_path_within",
                side_effect=flaky_resolve,
            ):
                result = write_file(str(workspace), "target.txt", "PWNED")
            self.assertIn("outside the permitted", result)
            self.assertEqual(outside_file.read_text(encoding="utf-8"), "SECRET")


if __name__ == "__main__":
    unittest.main()
