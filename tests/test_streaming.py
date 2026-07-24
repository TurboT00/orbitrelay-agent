# story: e04s02

from __future__ import annotations

import json
import os
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
from orbitrelay.events import EventCollector, EventType
from orbitrelay.profile_store import ProfileRepository
from orbitrelay.streaming import assemble_chat_completion


class RecordingAuthorizer:
    def __init__(self, decisions):
        self.decisions = list(decisions)

    def __call__(self, requests):
        if len(self.decisions) != len(requests):
            raise AssertionError("decision count mismatch")
        return tuple(self.decisions)


def _chunk(content=None, tool_calls=None, usage=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = SimpleNamespace(delta=delta)
    return SimpleNamespace(choices=[choice], usage=usage)


def _tool_delta(index, call_id=None, name=None, arguments=None):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(
        index=index,
        id=call_id,
        type="function",
        function=function,
    )


class StreamingTests(unittest.TestCase):
    def test_assemble_emits_model_deltas_and_final_text(self):
        collector = EventCollector()
        stream = [
            _chunk(content="Hel"),
            _chunk(content="lo"),
            _chunk(content="!", usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2)),
        ]
        response = assemble_chat_completion(
            stream, collector=collector, response_number=1
        )
        message = response.choices[0].message
        self.assertEqual(message.content, "Hello!")
        deltas = collector.of_type(EventType.MODEL_DELTA)
        self.assertEqual([event.data["text"] for event in deltas], ["Hel", "lo", "!"])
        self.assertEqual(
            [event.type for event in collector.events],
            [EventType.MODEL_DELTA, EventType.MODEL_DELTA, EventType.MODEL_DELTA],
        )

    def test_assemble_tool_call_deltas(self):
        stream = [
            _chunk(
                tool_calls=[
                    _tool_delta(0, call_id="call-1", name="write_file", arguments="")
                ]
            ),
            _chunk(
                tool_calls=[
                    _tool_delta(0, arguments='{"file_path":"a.txt","content":"x"}')
                ]
            ),
        ]
        response = assemble_chat_completion(stream)
        tool_calls = response.choices[0].message.tool_calls
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].id, "call-1")
        self.assertEqual(tool_calls[0].function.name, "write_file")
        self.assertEqual(
            tool_calls[0].function.arguments,
            '{"file_path":"a.txt","content":"x"}',
        )

    def test_run_agent_stream_emits_deltas_before_completion(self):
        client = Mock()
        client.chat.completions.create.return_value = [
            _chunk(content="A"),
            _chunk(content="B"),
        ]
        collector = EventCollector()
        with tempfile.TemporaryDirectory() as workspace:
            result = run_agent(
                client,
                "hi",
                "model",
                working_directory=workspace,
                stream=True,
                event_collector=collector,
            )
        self.assertEqual(result, "AB")
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertTrue(kwargs.get("stream"))
        self.assertEqual(kwargs.get("model"), "model")
        types = [event.type for event in collector.events]
        self.assertLess(
            types.index(EventType.MODEL_DELTA),
            types.index(EventType.RUN_COMPLETED),
        )
        self.assertEqual(types[-1], EventType.RUN_COMPLETED)
        self.assertEqual(
            "".join(event.data["text"] for event in collector.of_type(EventType.MODEL_DELTA)),
            "AB",
        )

    def test_run_agent_stream_tool_progress_without_secrets(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            [
                _chunk(
                    tool_calls=[
                        _tool_delta(
                            0,
                            call_id="call-1",
                            name="write_file",
                            arguments=json.dumps(
                                {"file_path": "notes.txt", "content": "secret-body"}
                            ),
                        )
                    ]
                )
            ],
            [_chunk(content="done")],
        ]
        collector = EventCollector()
        with tempfile.TemporaryDirectory() as workspace:
            result = run_agent(
                client,
                "write",
                "model",
                working_directory=workspace,
                stream=True,
                approval_session=ApprovalSession(
                    RecordingAuthorizer(
                        [ApprovalDecision.approve(reason="user_approved")]
                    )
                ),
                event_collector=collector,
            )
        self.assertEqual(result, "done")
        progress = collector.of_type(EventType.TOOL_PROGRESS)
        phases = [event.data["phase"] for event in progress]
        self.assertEqual(phases, ["preparing", "authorizing", "executing"])
        serialized = json.dumps(collector.as_dicts())
        self.assertNotIn("secret-body", serialized)
        self.assertNotIn("api_key", serialized)

    def test_cli_stream_writes_deltas_to_stderr_final_to_stdout(self):
        fake_client = Mock()
        fake_client.chat.completions.create.return_value = [
            _chunk(content="Hi"),
            _chunk(content="!"),
        ]
        stdout = StringIO()
        stderr = StringIO()
        with tempfile.TemporaryDirectory() as workspace:
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=True),
                patch("orbitrelay.cli.dotenv_values", return_value={}),
                patch("orbitrelay.cli.OpenAI", return_value=fake_client),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = cli.main(
                    ["hello", "--stream", "--workspace", workspace],
                    profile_repository=ProfileRepository(
                        Path(workspace) / "profiles.json"
                    ),
                )
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "Hi!\n")
        self.assertIn("Hi!", stderr.getvalue().replace("\n", ""))

    def test_cli_default_is_non_stream(self):
        with tempfile.TemporaryDirectory() as workspace:
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=True),
                patch("orbitrelay.cli.dotenv_values", return_value={}),
                patch("orbitrelay.cli.OpenAI", return_value=Mock()),
                patch("orbitrelay.cli.run_agent", return_value="final") as run_agent,
                redirect_stdout(StringIO()),
            ):
                cli.main(
                    ["hello", "--workspace", workspace],
                    profile_repository=ProfileRepository(
                        Path(workspace) / "profiles.json"
                    ),
                )
        self.assertNotIn("stream", run_agent.call_args.kwargs)
        self.assertNotIn("event_collector", run_agent.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
