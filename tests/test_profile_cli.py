import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from orbitrelay import cli
from orbitrelay.credentials import CredentialNotFoundError
from orbitrelay.profile_store import ProfileRepository


CAPABILITY_ARGS = [
    "--capability",
    "tool_calling",
    "--capability",
    "assistant_message_passthrough",
]


class FakeCredentialStore:
    def __init__(self):
        self.values = {}

    def set_secret(self, profile_name, secret):
        self.values[profile_name] = secret

    def get_secret(self, profile_name):
        try:
            return self.values[profile_name]
        except KeyError as exc:
            raise CredentialNotFoundError(profile_name) from exc

    def delete_secret(self, profile_name):
        self.values.pop(profile_name, None)


class ProfileCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "profiles.json"
        self.repository = ProfileRepository(self.path)
        self.credentials = FakeCredentialStore()

    def run_cli(self, arguments, *, prompt=None, stdin=None):
        output = StringIO()
        with redirect_stdout(output):
            exit_code = cli.main(
                arguments,
                profile_repository=self.repository,
                credential_store=self.credentials,
                secret_prompt=prompt or (lambda _: "prompt-secret"),
                input_stream=stdin or StringIO(),
            )
        self.assertEqual(exit_code, 0)
        return output.getvalue()

    def create_arguments(self, name="work"):
        return [
            "profile",
            "create",
            name,
            "--base-url",
            "https://example.test/v1",
            "--model",
            "test-model",
            "--auth-kind",
            "api_key",
            *CAPABILITY_ARGS,
        ]

    def test_create_prompts_for_secret_and_persists_only_metadata(self):
        output = self.run_cli(self.create_arguments())

        self.assertEqual(output, 'Created profile "work".\n')
        self.assertEqual(self.credentials.values, {"work": "prompt-secret"})
        self.assertNotIn("prompt-secret", self.path.read_text())

    def test_create_can_read_secret_from_standard_input(self):
        prompt_calls = []

        self.run_cli(
            [*self.create_arguments(), "--secret-stdin"],
            prompt=lambda message: prompt_calls.append(message),
            stdin=StringIO("stdin-secret\n"),
        )

        self.assertEqual(prompt_calls, [])
        self.assertEqual(self.credentials.values, {"work": "stdin-secret"})

    def test_list_show_select_and_delete_never_output_secret(self):
        self.run_cli(self.create_arguments())
        self.run_cli(["profile", "select", "work"])

        listing = self.run_cli(["profile", "list"])
        shown = self.run_cli(["profile", "show", "work"])

        self.assertIn("* work", listing)
        self.assertNotIn("prompt-secret", listing)
        shown_profile = json.loads(shown)
        self.assertEqual(shown_profile["name"], "work")
        self.assertTrue(shown_profile["selected"])
        self.assertNotIn("prompt-secret", shown)

        deleted = self.run_cli(["profile", "delete", "work"])
        self.assertEqual(deleted, 'Deleted profile "work".\n')
        self.assertEqual(self.repository.list_profiles(), ())
        self.assertEqual(self.credentials.values, {})

    def test_non_secret_profile_does_not_request_a_secret(self):
        prompt_calls = []
        output = self.run_cli(
            [
                "profile",
                "create",
                "ollama",
                "--base-url",
                "http://127.0.0.1:11434/v1",
                "--model",
                "qwen",
                "--auth-kind",
                "local_none",
                *CAPABILITY_ARGS,
            ],
            prompt=lambda message: prompt_calls.append(message),
        )

        self.assertEqual(output, 'Created profile "ollama".\n')
        self.assertEqual(prompt_calls, [])
        self.assertEqual(self.credentials.values, {})


if __name__ == "__main__":
    unittest.main()
