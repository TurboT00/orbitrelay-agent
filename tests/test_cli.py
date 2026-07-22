import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from orbitrelay import cli
from orbitrelay.config import DEFAULT_BASE_URL, DEFAULT_MODEL


class CliTests(unittest.TestCase):
    def test_import_has_no_cli_or_network_side_effects(self):
        environment = os.environ.copy()
        environment.pop("OPENAI_API_KEY", None)
        result = subprocess.run(
            [sys.executable, "-c", "import orbitrelay; import orbitrelay.cli"],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_main_wires_environment_cli_and_agent_without_network(self):
        fake_client = Mock(name="client")
        output = StringIO()

        with tempfile.TemporaryDirectory() as workspace:
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=True),
                patch("orbitrelay.cli.load_dotenv") as load_dotenv,
                patch("orbitrelay.cli.OpenAI", return_value=fake_client) as openai,
                patch(
                    "orbitrelay.cli.run_agent", return_value="final answer"
                ) as run_agent,
                redirect_stdout(output),
            ):
                exit_code = cli.main(
                    [
                        "inspect the calculator",
                        "--workspace",
                        workspace,
                        "--verbose",
                    ]
                )

        load_dotenv.assert_called_once_with()
        openai.assert_called_once_with(
            api_key="secret", base_url=DEFAULT_BASE_URL
        )
        run_agent.assert_called_once_with(
            fake_client,
            "inspect the calculator",
            DEFAULT_MODEL,
            working_directory=str(Path(workspace).resolve()),
            verbose=True,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue(), "final answer\n")

    def test_main_rejects_missing_key_before_client_creation(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("orbitrelay.cli.load_dotenv"),
            patch("orbitrelay.cli.OpenAI") as openai,
        ):
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY is required"):
                cli.main(["inspect"])

        openai.assert_not_called()

    def test_workspace_defaults_to_current_directory(self):
        self.assertEqual(cli.resolve_workspace(None), str(Path.cwd().resolve()))

    def test_invalid_workspace_is_rejected_before_client_creation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing = Path(temporary_directory) / "missing"
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=True),
                patch("orbitrelay.cli.load_dotenv"),
                patch("orbitrelay.cli.OpenAI") as openai,
            ):
                with self.assertRaisesRegex(ValueError, "Workspace is not a directory"):
                    cli.main(["inspect", "--workspace", str(missing)])

        openai.assert_not_called()


if __name__ == "__main__":
    unittest.main()
