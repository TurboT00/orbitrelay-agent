"""Expected CLI failure stream contracts (e06s05)."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from openai import APIStatusError

from orbitrelay import cli
from orbitrelay.connection_service import ConnectionService
from orbitrelay.credentials import CredentialNotFoundError
from orbitrelay.profile_store import ProfileRepository
from orbitrelay.providers import ProviderId
from orbitrelay.sessions import SessionStore


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


class CliErrorStreamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.home = Path(self.directory.name) / "home"
        self.home.mkdir()
        self.workspace = Path(self.directory.name) / "workspace"
        self.workspace.mkdir()
        self.repository = ProfileRepository(self.home / "profiles.json")
        self.store = FakeCredentialStore()
        self.connections = ConnectionService(self.repository, self.store)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _run(self, argv: list[str], **kwargs) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with (
            patch.dict(os.environ, {"ORBITRELAY_HOME": str(self.home)}, clear=False),
            patch("sys.stdout", out),
            patch("sys.stderr", err),
        ):
            code = cli.main(
                argv,
                profile_repository=kwargs.get("profile_repository", self.repository),
                credential_store=kwargs.get("credential_store", self.store),
                input_stream=kwargs.get("input_stream"),
            )
        return code, out.getvalue(), err.getvalue()

    def test_missing_connection_is_concise_stderr(self) -> None:
        code, out, err = self._run(
            ["hello", "--workspace", str(self.workspace)]
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("error:", err.lower())
        self.assertNotIn("Traceback", err)
        self.assertNotIn("Traceback", out)

    def test_unavailable_credentials_are_concise_stderr(self) -> None:
        self.connections.connect_api_key(ProviderId.OPENAI, "temporary")
        # Delete credential while leaving profile metadata selected.
        selected = self.repository.selected_name()
        assert selected is not None
        self.store.delete_secret(self.repository.credential_key(selected))
        code, out, err = self._run(["hello", "--workspace", str(self.workspace)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("error:", err.lower())
        self.assertNotIn("Traceback", err)
        self.assertNotIn("temporary", err)

    def test_provider_http_error_is_concise_stderr(self) -> None:
        self.connections.connect_api_key(ProviderId.OPENAI, "openai-secret")
        response = Mock()
        response.status_code = 401
        response.headers = {}
        response.text = "nope"
        error = APIStatusError("auth failed", response=response, body=None)
        client = Mock()
        client.chat.completions.create.side_effect = error
        with patch("orbitrelay.cli.OpenAI", return_value=client):
            code, out, err = self._run(["hello", "--workspace", str(self.workspace)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("401", err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("openai-secret", err)

    def test_invalid_session_input_is_concise_stderr(self) -> None:
        self.connections.connect_api_key(ProviderId.OPENAI, "openai-secret")
        store = SessionStore(root=self.home / "sessions")
        store.create(session_id="bad")
        (self.home / "sessions" / "bad" / "messages" / "000001.jsonl").write_text(
            "{bad\n", encoding="utf-8"
        )
        with patch("orbitrelay.cli.OpenAI") as openai:
            code, out, err = self._run(
                ["resume", "--session", "bad", "--workspace", str(self.workspace)]
            )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("error:", err.lower())
        self.assertNotIn("Traceback", err)
        openai.assert_not_called()

    def test_format_cli_error_scrubs_secret_exception_detail(self) -> None:
        secret = "sk-super-secret-sentinel-value-123456"
        message = cli.format_cli_error(ValueError(f"token={secret}"))
        self.assertNotIn(secret, message)
        self.assertIn("error:", message.lower())
        bare = cli.format_cli_error(ValueError(secret))
        self.assertNotIn(secret, bare)

    def test_tool_privacy_denial_keeps_final_answer_on_stdout_only(self) -> None:
        from types import SimpleNamespace

        self.connections.connect_api_key(ProviderId.OPENAI, "openai-secret")
        (self.workspace / ".env").write_text("SECRET=1\n", encoding="utf-8")

        def assistant(content=None, tool_calls=None):
            message = SimpleNamespace(
                role="assistant", content=content, tool_calls=tool_calls or []
            )

            def model_dump(exclude_none=True):
                payload = {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls,
                }
                if exclude_none:
                    return {
                        key: value
                        for key, value in payload.items()
                        if value is not None
                    }
                return payload

            message.model_dump = model_dump  # type: ignore[attr-defined]
            return message

        tool_call = SimpleNamespace(
            id="call-1",
            type="function",
            function=SimpleNamespace(
                name="get_file_content",
                arguments=json.dumps({"file_path": ".env"}),
            ),
        )
        first = assistant(tool_calls=[tool_call])
        final = assistant(content="done")
        client = Mock()
        client.chat.completions.create = Mock(
            side_effect=[
                SimpleNamespace(choices=[SimpleNamespace(message=first)], usage=None),
                SimpleNamespace(choices=[SimpleNamespace(message=final)], usage=None),
            ]
        )
        with patch("orbitrelay.cli.OpenAI", return_value=client):
            code, out, err = self._run(
                ["inspect", "--workspace", str(self.workspace)]
            )
        self.assertEqual(code, 0)
        self.assertEqual(out, "done\n")
        self.assertNotIn("SECRET=1", out)
        self.assertNotIn("SECRET=1", err)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
