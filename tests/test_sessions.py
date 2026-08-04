# story: e04s03
# story: e04s04

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from orbitrelay import cli
from orbitrelay.agent import run_agent
from orbitrelay.connection_service import ConnectionService
from orbitrelay.credentials import CredentialNotFoundError
from orbitrelay.events import EventCollector, EventType
from orbitrelay.profile_store import ProfileRepository
from orbitrelay.providers import ProviderId
from orbitrelay.sessions import (
    SessionCorruptionError,
    SessionError,
    SessionNotFoundError,
    SessionStore,
)


def _assistant_message(content=None, tool_calls=None):
    message = SimpleNamespace(
        role="assistant", content=content, tool_calls=tool_calls or []
    )

    def model_dump(exclude_none=True):
        payload = {
            "role": message.role,
            "content": message.content,
            "tool_calls": message.tool_calls,
        }
        if exclude_none:
            return {key: value for key, value in payload.items() if value is not None}
        return payload

    message.model_dump = model_dump  # type: ignore[attr-defined]
    return message


def _response(message, usage=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class _CredentialStore:
    def __init__(self):
        self.values = {}

    def set_secret(self, key, secret):
        self.values[key] = secret

    def get_secret(self, key):
        try:
            return self.values[key]
        except KeyError as exc:
            raise CredentialNotFoundError(key) from exc

    def delete_secret(self, key):
        self.values.pop(key, None)


class SessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.home = Path(self.temporary_directory.name)
        self.store = SessionStore(root=self.home / "sessions", clock=lambda: 1000.0)

    def test_create_uses_secure_permissions_and_redacts_secrets(self) -> None:
        metadata = self.store.create(session_id="demo1", workspace="/tmp/ws", model="m")
        self.assertEqual(metadata.id, "demo1")
        root_mode = stat.S_IMODE((self.home / "sessions").stat().st_mode)
        session_mode = stat.S_IMODE((self.home / "sessions" / "demo1").stat().st_mode)
        self.assertEqual(root_mode, 0o700)
        self.assertEqual(session_mode, 0o700)

        self.store.replace_messages(
            "demo1",
            [
                {"role": "user", "content": "hi", "api_key": "secret-key"},
                {"role": "assistant", "content": "hello"},
            ],
        )
        messages_path = self.home / "sessions" / "demo1" / "messages.jsonl"
        events_path = self.home / "sessions" / "demo1" / "events.jsonl"
        self.assertEqual(stat.S_IMODE(messages_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(events_path.stat().st_mode), 0o600)
        body = messages_path.read_text(encoding="utf-8")
        self.assertNotIn("secret-key", body)
        self.assertIn("<redacted>", body)

        collector = EventCollector()
        collector.emit(EventType.RUN_STARTED, model="m", api_key="token-value")
        self.store.append_events("demo1", collector.events)
        events_body = events_path.read_text(encoding="utf-8")
        self.assertNotIn("token-value", events_body)
        self.assertIn("<redacted>", events_body)

    def test_rejects_unsafe_session_ids(self) -> None:
        with self.assertRaises(SessionError):
            self.store.create(session_id="../escape")

    def test_corrupt_messages_fail_closed(self) -> None:
        self.store.create(session_id="broken")
        path = self.home / "sessions" / "broken" / "messages.jsonl"
        path.write_text("{not-json\n", encoding="utf-8")
        with self.assertRaises(SessionCorruptionError):
            self.store.load_messages("broken")

    def test_missing_session_raises(self) -> None:
        with self.assertRaises(SessionNotFoundError):
            self.store.load_messages("nope")

    def test_agent_resume_includes_prior_history(self) -> None:
        self.store.create(session_id="chat1")
        self.store.replace_messages(
            "chat1",
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "answer-one"},
            ],
        )
        client = Mock()
        client.chat.completions.create.return_value = _response(
            _assistant_message(content="answer-two")
        )
        history = self.store.load_messages("chat1")
        with tempfile.TemporaryDirectory() as workspace:
            result = run_agent(
                client,
                "second",
                "model",
                working_directory=workspace,
                initial_messages=history,
            )
        self.assertEqual(result, "answer-two")
        sent_messages = client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(sent_messages[0]["role"], "system")
        self.assertEqual(sent_messages[-2]["content"], "answer-one")
        self.assertEqual(sent_messages[-1], {"role": "user", "content": "second"})

    def test_cli_persists_and_resumes_session(self) -> None:
        home = self.home
        client = Mock()
        client.chat.completions.create.side_effect = [
            _response(_assistant_message(content="first-answer")),
            _response(_assistant_message(content="second-answer")),
        ]
        stdout = StringIO()
        stderr = StringIO()
        with tempfile.TemporaryDirectory() as workspace:
            repository = ProfileRepository(Path(workspace) / "profiles.json")
            credentials = _CredentialStore()
            ConnectionService(repository, credentials).connect_api_key(
                ProviderId.OPENAI, "secret"
            )
            with (
                patch.dict(os.environ, {"ORBITRELAY_HOME": str(home)}, clear=True),
                patch("orbitrelay.cli.OpenAI", return_value=client),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = cli.main(
                    [
                        "first prompt",
                        "--session",
                        "demo",
                        "--workspace",
                        workspace,
                    ],
                    profile_repository=repository,
                    credential_store=credentials,
                )
                self.assertEqual(code, 0)
                code = cli.main(
                    [
                        "second prompt",
                        "--session",
                        "demo",
                        "--workspace",
                        workspace,
                    ],
                    profile_repository=repository,
                    credential_store=credentials,
                )
                self.assertEqual(code, 0)

        self.assertEqual(stdout.getvalue(), "first-answer\nsecond-answer\n")
        store = SessionStore(root=home / "sessions")
        messages = store.load_messages("demo")
        roles = [message["role"] for message in messages]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)
        # second model call should include prior assistant answer
        second_messages = client.chat.completions.create.call_args_list[1].kwargs[
            "messages"
        ]
        self.assertTrue(
            any(
                message.get("content") == "first-answer"
                for message in second_messages
                if isinstance(message, dict)
            )
        )
        # no api key material in session files
        session_text = (home / "sessions" / "demo" / "messages.jsonl").read_text()
        events_text = (home / "sessions" / "demo" / "events.jsonl").read_text()
        self.assertNotIn("secret", session_text)
        self.assertNotIn("secret", events_text)

    def test_cli_corrupt_session_fails_before_tools(self) -> None:
        home = self.home
        store = SessionStore(root=home / "sessions")
        store.create(session_id="bad")
        (home / "sessions" / "bad" / "messages.jsonl").write_text("{bad\n", encoding="utf-8")
        with tempfile.TemporaryDirectory() as workspace:
            repository = ProfileRepository(Path(workspace) / "profiles.json")
            credentials = _CredentialStore()
            ConnectionService(repository, credentials).connect_api_key(
                ProviderId.OPENAI, "secret"
            )
            stderr = StringIO()
            stdout = StringIO()
            with (
                patch.dict(
                    os.environ,
                    {"ORBITRELAY_HOME": str(home)},
                    clear=True,
                ),
                patch("orbitrelay.cli.OpenAI") as openai,
                patch("sys.stderr", stderr),
                patch("sys.stdout", stdout),
            ):
                code = cli.main(
                    ["resume", "--session", "bad", "--workspace", workspace],
                    profile_repository=repository,
                    credential_store=credentials,
                )
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertRegex(stderr.getvalue(), r"not valid JSON|corrupt|invalid|error:")
        self.assertNotIn("Traceback", stderr.getvalue())
        openai.assert_not_called()

    def test_session_cli_list_show_delete(self) -> None:
        from orbitrelay.session_cli import run_session_cli

        self.store.create(session_id="one", model="m1")
        self.store.create(session_id="two", model="m2")
        self.store.replace_messages("one", [{"role": "user", "content": "hi"}])
        out = StringIO()
        code = run_session_cli(["list"], store=self.store, output=out)
        self.assertEqual(code, 0)
        self.assertIn("one", out.getvalue())
        self.assertIn("two", out.getvalue())

        show = StringIO()
        code = run_session_cli(["show", "one"], store=self.store, output=show)
        self.assertEqual(code, 0)
        payload = json.loads(show.getvalue())
        self.assertEqual(payload["id"], "one")
        self.assertEqual(payload["message_count"], 1)
        self.assertNotIn("hi", show.getvalue())  # show is metadata-only

        deleted = StringIO()
        code = run_session_cli(["delete", "one"], store=self.store, output=deleted)
        self.assertEqual(code, 0)
        ids = {item.id for item in self.store.list_sessions()}
        self.assertEqual(ids, {"two"})

        err = StringIO()
        code = run_session_cli(["delete-all"], store=self.store, output=err)
        self.assertEqual(code, 1)
        code = run_session_cli(
            ["delete-all", "--confirm"], store=self.store, output=err
        )
        self.assertEqual(code, 0)
        self.assertEqual(self.store.list_sessions(), ())


if __name__ == "__main__":
    unittest.main()
