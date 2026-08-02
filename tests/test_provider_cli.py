from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orbitrelay.connection_service import ConnectionError, ConnectionService
from orbitrelay.credentials import CredentialNotFoundError
from orbitrelay.profile_store import ProfileRepository
from orbitrelay.provider_cli import parse_provider_args, run_provider_cli
from orbitrelay.providers import ProviderId


class FakeCredentialStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set_secret(self, key: str, secret: str) -> None:
        self.values[key] = secret

    def get_secret(self, key: str) -> str:
        try:
            return self.values[key]
        except KeyError as exc:
            raise CredentialNotFoundError(key) from exc

    def delete_secret(self, key: str) -> None:
        self.values.pop(key, None)


class ProviderCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.repository = ProfileRepository(Path(self.directory.name) / "profiles.json")
        self.store = FakeCredentialStore()
        self.output = io.StringIO()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def execute(
        self,
        argv: list[str],
        secret: str = "test-key",
        environment: dict[str, str] | None = None,
    ) -> int:
        return run_provider_cli(
            argv,
            self.repository,
            self.store,
            lambda _prompt: secret,
            output=self.output,
            environment=environment,
            dotenv_environment={},
        )

    def test_connects_an_api_key_provider_and_selects_it(self) -> None:
        self.assertEqual(self.execute(["connect", "deepseek", "--method", "api_key"]), 0)
        self.assertEqual(self.repository.selected_name(), "deepseek")
        self.assertIn('Connected and selected provider "deepseek".', self.output.getvalue())
        self.assertNotIn("test-key", self.output.getvalue())

    def test_list_includes_every_required_provider(self) -> None:
        self.assertEqual(self.execute(["list"]), 0)

        for provider in ("openai", "codex", "gemini", "grok", "deepseek"):
            self.assertIn(provider, self.output.getvalue())

    def test_environment_import_command_is_not_available(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            parse_provider_args(["import-env", "--provider", "openai"])

        self.assertEqual(raised.exception.code, 2)

    def test_rejects_unsupported_grok_subscription(self) -> None:
        self.assertEqual(self.execute(["connect", "grok", "--method", "subscription"]), 1)
        self.assertIn("No documented", self.output.getvalue())
        self.assertEqual(self.store.values, {})

    def test_failed_codex_login_does_not_change_selected_provider(self) -> None:
        self.assertEqual(self.execute(["connect", "openai", "--method", "api_key"]), 0)
        self.output.seek(0)
        self.output.truncate(0)

        with patch("orbitrelay.provider_cli.run_codex_cli", return_value=1):
            self.assertEqual(
                self.execute(["connect", "codex", "--method", "subscription"]),
                1,
            )

        self.assertEqual(self.repository.selected_name(), "openai")
        with self.assertRaisesRegex(ConnectionError, "not connected"):
            ConnectionService(self.repository, self.store).profile_for_provider(
                ProviderId.CODEX
            )

    def test_imports_exactly_one_provider_from_environment(self) -> None:
        self.assertEqual(
            self.execute(
                ["import-env", "--provider", "gemini"],
                environment={"GEMINI_API_KEY": "gemini-key", "GEMINI_MODEL": "gemini-test"},
            ),
            0,
        )

        self.assertEqual(self.repository.selected_name(), "gemini")
        self.assertIn('Imported and selected provider "gemini".', self.output.getvalue())
        self.assertNotIn("gemini-key", self.output.getvalue())

    def test_import_rejects_more_than_one_api_key(self) -> None:
        self.assertEqual(
            self.execute(
                ["import-env", "--provider", "openai"],
                environment={"OPENAI_API_KEY": "openai-key", "XAI_API_KEY": "grok-key"},
            ),
            1,
        )
        self.assertIn("ambiguous", self.output.getvalue())
        self.assertEqual(self.store.values, {})


if __name__ == "__main__":
    unittest.main()
