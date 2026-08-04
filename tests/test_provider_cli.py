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
    ) -> int:
        return run_provider_cli(
            argv,
            self.repository,
            self.store,
            lambda _prompt: secret,
            output=self.output,
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



    def test_status_reports_offline_readiness_facts(self) -> None:
        self.assertEqual(self.execute(["connect", "openai", "--method", "api_key"]), 0)
        self.output.seek(0)
        self.output.truncate(0)
        self.assertEqual(self.execute(["status", "openai"]), 0)
        text = self.output.getvalue()
        self.assertIn("provider: openai", text)
        self.assertIn("configured: yes", text)
        self.assertIn("selected: yes", text)
        self.assertIn("credential: present", text)
        self.assertIn("readiness: local-ready", text)
        self.assertNotIn("test-key", text)
        self.assertNotIn("is connected as", text)

    def test_status_selected_without_argument(self) -> None:
        self.assertEqual(self.execute(["connect", "deepseek", "--method", "api_key"]), 0)
        self.output.seek(0)
        self.output.truncate(0)
        self.assertEqual(self.execute(["status"]), 0)
        text = self.output.getvalue()
        self.assertIn("provider: deepseek", text)
        self.assertIn("readiness: local-ready", text)

    def test_status_credential_unavailable_without_traceback(self) -> None:
        self.assertEqual(self.execute(["connect", "gemini", "--method", "api_key"]), 0)
        self.output.seek(0)
        self.output.truncate(0)

        class UnavailableStore:
            def set_secret(self, key: str, secret: str) -> None:
                raise AssertionError("unused")

            def get_secret(self, key: str) -> str:
                from orbitrelay.credentials import CredentialStoreError

                raise CredentialStoreError("Native credential store is unavailable")

            def delete_secret(self, key: str) -> None:
                raise AssertionError("unused")

        code = run_provider_cli(
            ["status", "gemini"],
            self.repository,
            UnavailableStore(),
            lambda _prompt: "x",
            output=self.output,
        )
        self.assertEqual(code, 0)
        text = self.output.getvalue()
        self.assertIn("credential: unavailable", text)
        self.assertIn("readiness: unknown", text)
        self.assertNotIn("Traceback", text)

    def test_list_does_not_initialize_credential_backend(self) -> None:
        class BoomStore:
            def __init__(self) -> None:
                raise AssertionError("credential backend must stay lazy for list")

        with patch(
            "orbitrelay.connection_service.credential_store_or_default",
            side_effect=AssertionError("credential backend must stay lazy for list"),
        ):
            code = run_provider_cli(
                ["list"],
                self.repository,
                None,
                lambda _prompt: "x",
                output=self.output,
            )
        self.assertEqual(code, 0)
        self.assertIn("openai", self.output.getvalue())




    def test_codex_status_reports_delegated_readiness(self) -> None:
        from types import SimpleNamespace

        from orbitrelay.codex_bridge import CodexBridge
        from orbitrelay.connection_service import ConnectionService

        def _completed(returncode=0, stdout="", stderr=""):
            return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

        class RecordingRunner:
            def __init__(self, behaviors=None) -> None:
                self.behaviors = list(behaviors or [])

            def __call__(self, argv, **kwargs):
                if self.behaviors:
                    return self.behaviors.pop(0)
                return _completed()

        service = ConnectionService(self.repository, self.store)
        service.connect_subscription(ProviderId.CODEX)
        runner = RecordingRunner(
            behaviors=[
                _completed(stdout="codex-cli 9.9.9\n"),
                _completed(returncode=0, stdout="account: leak@example.com\n"),
            ]
        )
        bridge = CodexBridge(
            which=lambda name: "/bin/codex" if name == "codex" else None,
            runner=runner,
        )
        service = ConnectionService(self.repository, self.store, codex_bridge=bridge)
        # monkeypatch ConnectionService used by CLI
        def factory(repository, credential_store):
            return ConnectionService(repository, credential_store, codex_bridge=bridge)

        with patch("orbitrelay.provider_cli.ConnectionService", side_effect=factory):
            code = run_provider_cli(
                ["status", "codex"],
                self.repository,
                self.store,
                lambda _prompt: "x",
                output=self.output,
            )
        self.assertEqual(code, 0)
        text = self.output.getvalue()
        self.assertIn("provider: codex", text)
        self.assertIn("configured: yes", text)
        self.assertIn("installation: available", text)
        self.assertIn("authentication: authenticated", text)
        self.assertIn("readiness: local-ready", text)
        self.assertNotIn("leak@example.com", text)
        self.assertNotIn("account:", text)

    def test_codex_status_unknown_does_not_claim_ready(self) -> None:
        from types import SimpleNamespace

        from orbitrelay.codex_bridge import CodexBridge
        from orbitrelay.connection_service import ConnectionService

        def _completed(returncode=0, stdout="", stderr=""):
            return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

        class RecordingRunner:
            def __init__(self, behaviors=None) -> None:
                self.behaviors = list(behaviors or [])

            def __call__(self, argv, **kwargs):
                if self.behaviors:
                    return self.behaviors.pop(0)
                return _completed()

        ConnectionService(self.repository, self.store).connect_subscription(ProviderId.CODEX)
        runner = RecordingRunner(
            behaviors=[
                _completed(stdout="codex-cli 1.0.0\n"),
                _completed(returncode=99, stderr="unexpected failure mode\n"),
            ]
        )
        bridge = CodexBridge(
            which=lambda name: "/bin/codex" if name == "codex" else None,
            runner=runner,
        )

        def factory(repository, credential_store):
            return ConnectionService(repository, credential_store, codex_bridge=bridge)

        with patch("orbitrelay.provider_cli.ConnectionService", side_effect=factory):
            code = run_provider_cli(
                ["status", "codex"],
                self.repository,
                self.store,
                lambda _prompt: "x",
                output=self.output,
            )
        self.assertEqual(code, 0)
        text = self.output.getvalue()
        self.assertIn("authentication: unknown", text)
        self.assertIn("readiness: unknown", text)
        self.assertNotIn("local-ready", text)

if __name__ == "__main__":
    unittest.main()
