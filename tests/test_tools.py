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


if __name__ == "__main__":
    unittest.main()
