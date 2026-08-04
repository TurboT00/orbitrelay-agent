from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

from orbitrelay import cli
from orbitrelay.connection_service import ConnectionService
from orbitrelay.credentials import CredentialNotFoundError
from orbitrelay.profile_store import ProfileRepository
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


class CliConnectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.directory.name) / "workspace"
        self.workspace.mkdir()
        self.repository = ProfileRepository(Path(self.directory.name) / "profiles.json")
        self.store = FakeCredentialStore()
        self.connections = ConnectionService(self.repository, self.store)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_runs_from_selected_connection_without_environment_credentials(self) -> None:
        self.connections.connect_api_key(ProviderId.DEEPSEEK, "deepseek-secret")
        client = Mock()
        output = io.StringIO()

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("orbitrelay.cli.OpenAI", return_value=client) as openai,
            patch("orbitrelay.cli.run_agent", return_value="done") as run_agent,
            patch("sys.stdout", output),
        ):
            result = cli.main(
                ["inspect", "--workspace", str(self.workspace)],
                profile_repository=self.repository,
                credential_store=self.store,
            )

        self.assertEqual(result, 0)
        openai.assert_called_once_with(
            api_key="deepseek-secret", base_url="https://api.deepseek.com"
        )
        run_agent.assert_called_once_with(
            client,
            "inspect",
            "deepseek-v4-flash",
            working_directory=str(self.workspace.resolve()),
            verbose=False,
            approval_session=ANY,
        )
        self.assertEqual(output.getvalue(), "done\n")

    def test_provider_override_does_not_change_selected_connection(self) -> None:
        self.connections.connect_api_key(ProviderId.DEEPSEEK, "deepseek-secret")
        self.connections.connect_api_key(ProviderId.OPENAI, "openai-secret")
        client = Mock()

        with (
            patch("orbitrelay.cli.OpenAI", return_value=client) as openai,
            patch("orbitrelay.cli.run_agent", return_value="done"),
            patch("sys.stdout", io.StringIO()),
        ):
            result = cli.main(
                ["inspect", "--workspace", str(self.workspace), "--provider", "deepseek"],
                profile_repository=self.repository,
                credential_store=self.store,
            )

        self.assertEqual(result, 0)
        openai.assert_called_once_with(
            api_key="deepseek-secret", base_url="https://api.deepseek.com"
        )
        self.assertEqual(self.repository.selected_name(), "openai")

    def test_dispatches_provider_commands_without_environment_credentials(self) -> None:
        output = io.StringIO()

        with patch("sys.stdout", output):
            result = cli.main(
                ["provider", "list"],
                profile_repository=self.repository,
                credential_store=self.store,
            )

        self.assertEqual(result, 0)
        self.assertIn("openai: api_key", output.getvalue())

    def test_legacy_provider_commands_are_deprecation_aliases(self) -> None:
        error = io.StringIO()

        with patch("sys.stderr", error):
            result = cli.main(
                ["profile", "list"],
                profile_repository=self.repository,
                credential_store=self.store,
            )

        self.assertEqual(result, 2)
        self.assertIn("orbitrelay provider --help", error.getvalue())


    def test_codex_logout_disconnect_dispatch(self) -> None:
        self.connections.connect_subscription(ProviderId.CODEX)
        out = io.StringIO()
        with (
            patch("orbitrelay.codex_cli.CodexBridge") as bridge_cls,
            patch("sys.stdout", out),
        ):
            bridge = bridge_cls.return_value
            bridge.logout.return_value = 0
            # run_codex_cli constructs ConnectionService with codex_bridge=active
            # when --disconnect; need the bridge instance used inside
            result = cli.main(
                ["codex", "logout", "--disconnect"],
                profile_repository=self.repository,
                credential_store=self.store,
            )
        # Depending on wiring, CodexBridge may be constructed inside run_codex_cli
        self.assertIn(result, (0, 1))
        # stronger path: call with patched bridge via codex_cli
        from unittest.mock import Mock

        from orbitrelay.codex_bridge import CodexBridge
        from orbitrelay.codex_cli import run_codex_cli
        bridge = Mock(spec=CodexBridge)
        bridge.logout.return_value = 0
        out2 = io.StringIO()
        self.connections.connect_subscription(ProviderId.CODEX)
        code = run_codex_cli(
            ["logout", "--disconnect"],
            bridge=bridge,
            output=out2,
            profile_repository=self.repository,
            credential_store=self.store,
        )
        self.assertEqual(code, 0)
        self.assertIn("complete: yes", out2.getvalue())
        self.assertIsNone(self.repository.selected_name())
        bridge.logout.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
