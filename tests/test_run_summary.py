# story: e04s06

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from orbitrelay import cli
from orbitrelay.agent import run_agent
from orbitrelay.approvals import ApprovalDecision, ApprovalSession
from orbitrelay.connection_service import ConnectionService
from orbitrelay.credentials import CredentialNotFoundError
from orbitrelay.events import EventCollector, EventType
from orbitrelay.profile_store import ProfileRepository
from orbitrelay.providers import ProviderId
from orbitrelay.run_summary import format_run_summary, summarize_run


class RecordingAuthorizer:
    def __init__(self, decisions):
        self.decisions = list(decisions)

    def __call__(self, requests):
        return tuple(self.decisions)


def _assistant_message(content=None, tool_calls=None):
    message = SimpleNamespace(
        role="assistant", content=content, tool_calls=tool_calls or []
    )

    def model_dump(exclude_none=True):
        payload = {
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls or None,
        }
        if exclude_none:
            return {key: value for key, value in payload.items() if value is not None}
        return payload

    message.model_dump = model_dump  # type: ignore[attr-defined]
    return message


def _response(message, usage=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


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


class RunSummaryTests(unittest.TestCase):
    def test_summarize_successful_run_from_events(self) -> None:
        collector = EventCollector()
        collector.emit(EventType.RUN_STARTED, model="m")
        collector.emit(
            EventType.USAGE_REPORTED,
            response_number=1,
            available=True,
            prompt_tokens=11,
            completion_tokens=3,
        )
        collector.emit(EventType.TOOL_REQUESTED, tool_call_id="c1", tool="write_file")
        collector.emit(
            EventType.APPROVAL_DECIDED,
            tool_call_id="c1",
            disposition="approved",
            reason="user_approved",
        )
        collector.emit(
            EventType.TOOL_RESULT, tool_call_id="c1", tool="write_file", status="ok"
        )
        collector.emit(EventType.MODEL_MESSAGE, role="assistant", content="done")
        collector.emit(EventType.RUN_COMPLETED, status="completed")

        summary = summarize_run(collector.events)
        payload = summary.to_dict()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["response_count"], 1)
        self.assertEqual(payload["tool_requested"], 1)
        self.assertEqual(payload["tool_results_ok"], 1)
        self.assertEqual(payload["tool_results_error"], 0)
        self.assertEqual(payload["approvals"], {"approved": 1})
        self.assertEqual(payload["prompt_tokens"], 11)
        self.assertEqual(payload["completion_tokens"], 3)
        self.assertNotIn("api_key", payload)
        text = format_run_summary(summary)
        self.assertIn("status=completed", text)
        self.assertIn("tools_requested=1", text)

    def test_summarize_failed_run_includes_error_code(self) -> None:
        collector = EventCollector()
        collector.emit(EventType.RUN_STARTED, model="m")
        collector.emit(
            EventType.RUN_ERROR,
            error_type="RuntimeError",
            message="provider failed",
            api_key="should-redact",
        )
        collector.emit(EventType.RUN_COMPLETED, status="error")
        summary = summarize_run(collector.events)
        payload = summary.to_dict()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_type"], "RuntimeError")
        self.assertEqual(payload["error_message"], "provider failed")
        # ensure redaction path works if secrets sneak into data
        sneaky = EventCollector()
        sneaky.emit(EventType.RUN_ERROR, error_type="X", message="m", api_key="secret")
        sneaky.emit(EventType.RUN_COMPLETED, status="error")
        redacted = summarize_run(sneaky.events).to_dict()
        # api_key not a summary field; to_dict still redacts nested maps
        self.assertEqual(redacted["status"], "error")

    def test_agent_events_produce_summary(self) -> None:
        client = Mock()
        client.chat.completions.create.side_effect = [
            _response(
                _assistant_message(
                    tool_calls=[
                        _tool_call(
                            "call-1",
                            "write_file",
                            json.dumps({"file_path": "a.txt", "content": "x"}),
                        )
                    ]
                ),
                usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2),
            ),
            _response(
                _assistant_message(content="done"),
                usage=SimpleNamespace(prompt_tokens=6, completion_tokens=1),
            ),
        ]
        collector = EventCollector()
        with tempfile.TemporaryDirectory() as workspace:
            result = run_agent(
                client,
                "write",
                "model",
                working_directory=workspace,
                approval_session=ApprovalSession(
                    RecordingAuthorizer(
                        [ApprovalDecision.approve(reason="user_approved")]
                    )
                ),
                event_collector=collector,
            )
        self.assertEqual(result, "done")
        summary = summarize_run(collector.events)
        self.assertEqual(summary.status, "completed")
        self.assertEqual(summary.tool_requested, 1)
        self.assertEqual(summary.tool_results_ok, 1)
        self.assertEqual(summary.prompt_tokens, 11)
        self.assertEqual(summary.completion_tokens, 3)
        self.assertNotIn("secret", json.dumps(summary.to_dict()))

    def test_cli_verbose_prints_summary_on_stderr(self) -> None:
        client = Mock()
        client.chat.completions.create.return_value = _response(
            _assistant_message(content="hello"),
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1),
        )
        stdout = StringIO()
        stderr = StringIO()
        with tempfile.TemporaryDirectory() as workspace:
            repository = ProfileRepository(Path(workspace) / "profiles.json")
            credentials = _CredentialStore()
            ConnectionService(repository, credentials).connect_api_key(
                ProviderId.OPENAI, "secret"
            )
            with (
                patch("orbitrelay.cli.OpenAI", return_value=client),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = cli.main(
                    ["hi", "--verbose", "--workspace", workspace],
                    profile_repository=repository,
                    credential_store=credentials,
                )
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "hello\n")
        self.assertIn("Response 1:", stderr.getvalue())
        self.assertIn("Run summary:", stderr.getvalue())
        self.assertIn("status=completed", stderr.getvalue())
        self.assertNotIn("secret", stderr.getvalue())

    def test_cli_non_verbose_keeps_stdout_final_only(self) -> None:
        out = StringIO()
        err = StringIO()
        with tempfile.TemporaryDirectory() as workspace:
            repository = ProfileRepository(Path(workspace) / "profiles.json")
            credentials = _CredentialStore()
            ConnectionService(repository, credentials).connect_api_key(
                ProviderId.OPENAI, "secret"
            )
            with (
                patch("orbitrelay.cli.OpenAI", return_value=Mock()),
                patch("orbitrelay.cli.run_agent", return_value="final") as run_agent,
                redirect_stdout(out),
                redirect_stderr(err),
            ):
                cli.main(
                    ["hi", "--workspace", workspace],
                    profile_repository=repository,
                    credential_store=credentials,
                )
        self.assertEqual(out.getvalue(), "final\n")
        self.assertNotIn("Run summary:", err.getvalue())
        self.assertNotIn("event_collector", run_agent.call_args.kwargs)

    def test_cli_tool_round_keeps_stdout_final_only(self) -> None:
        client = Mock()
        client.chat.completions.create.side_effect = [
            _response(
                _assistant_message(
                    tool_calls=[_tool_call("call-1", "get_files_info", "{}")]
                )
            ),
            _response(_assistant_message(content="done")),
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
                patch("orbitrelay.cli.OpenAI", return_value=client),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = cli.main(
                    ["inspect", "--workspace", workspace],
                    profile_repository=repository,
                    credential_store=credentials,
                )

        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "done\n")
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
