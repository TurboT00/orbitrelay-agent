# story: e04s01

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from orbitrelay.agent import run_agent
from orbitrelay.approvals import ApprovalDecision, ApprovalSession
from orbitrelay.events import EventCollector, EventType, RunEvent
from orbitrelay.redaction import REDACTED


class RecordingAuthorizer:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.requests = []

    def __call__(self, requests):
        self.requests.extend(requests)
        if len(self.decisions) != len(requests):
            raise AssertionError("decision count mismatch")
        return tuple(self.decisions)


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


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class EventModelTests(unittest.TestCase):
    def test_run_event_redacts_sensitive_data(self):
        event = RunEvent(
            type=EventType.TOOL_RESULT,
            data={"tool_call_id": "c1", "api_key": "secret", "ok": True},
        )
        payload = event.to_dict()
        self.assertEqual(payload["type"], "tool.result")
        self.assertEqual(payload["data"]["api_key"], REDACTED)
        self.assertEqual(payload["data"]["ok"], True)

    def test_collector_preserves_order(self):
        collector = EventCollector()
        collector.emit(EventType.RUN_STARTED, session_id="s1")
        collector.emit(EventType.MODEL_MESSAGE, role="assistant", content="hi")
        collector.emit(EventType.RUN_COMPLETED, status="completed")
        self.assertEqual(
            [event.type for event in collector.events],
            [
                EventType.RUN_STARTED,
                EventType.MODEL_MESSAGE,
                EventType.RUN_COMPLETED,
            ],
        )

    def test_agent_emits_correlated_tool_and_approval_events(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            _response(
                _assistant_message(
                    tool_calls=[
                        _tool_call(
                            "call-1",
                            "write_file",
                            json.dumps(
                                {
                                    "file_path": "notes.txt",
                                    "content": "hello",
                                }
                            ),
                        )
                    ]
                ),
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4),
            ),
            _response(_assistant_message(content="done")),
        ]
        collector = EventCollector()
        authorizer = RecordingAuthorizer(
            [ApprovalDecision.approve(reason="user_approved")]
        )
        with tempfile.TemporaryDirectory() as workspace:
            Path(workspace, "notes.txt")  # ensure path parent exists
            result = run_agent(
                client,
                "write a note",
                "test-model",
                working_directory=workspace,
                approval_session=ApprovalSession(authorizer),
                event_collector=collector,
            )

        self.assertEqual(result, "done")
        types = [event.type for event in collector.events]
        self.assertIn(EventType.RUN_STARTED, types)
        self.assertIn(EventType.TOOL_REQUESTED, types)
        self.assertIn(EventType.APPROVAL_DECIDED, types)
        self.assertIn(EventType.TOOL_RESULT, types)
        self.assertIn(EventType.USAGE_REPORTED, types)
        self.assertIn(EventType.MODEL_MESSAGE, types)
        self.assertIn(EventType.RUN_COMPLETED, types)
        self.assertEqual(types[-1], EventType.RUN_COMPLETED)

        requested = collector.of_type(EventType.TOOL_REQUESTED)[0]
        decided = collector.of_type(EventType.APPROVAL_DECIDED)[0]
        tool_result = collector.of_type(EventType.TOOL_RESULT)[0]
        self.assertEqual(requested.data["tool_call_id"], "call-1")
        self.assertEqual(decided.data["tool_call_id"], "call-1")
        self.assertEqual(tool_result.data["tool_call_id"], "call-1")
        self.assertEqual(requested.data["tool"], "write_file")

        serialized = json.dumps(collector.as_dicts())
        self.assertNotIn("hello", serialized)  # write content not in events
        self.assertIn("call-1", serialized)

    def test_agent_without_collector_remains_compatible(self):
        client = Mock()
        client.chat.completions.create.return_value = _response(
            _assistant_message(content="plain")
        )
        with tempfile.TemporaryDirectory() as workspace:
            result = run_agent(
                client,
                "hi",
                "test-model",
                working_directory=workspace,
            )
        self.assertEqual(result, "plain")

    def test_plain_text_tool_error_is_reported_as_an_error_event(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            _response(
                _assistant_message(
                    tool_calls=[_tool_call("call-1", "unknown_tool", "{}")]
                )
            ),
            _response(_assistant_message(content="done")),
        ]
        collector = EventCollector()

        with tempfile.TemporaryDirectory() as workspace:
            run_agent(
                client,
                "try an unknown tool",
                "test-model",
                working_directory=workspace,
                event_collector=collector,
            )

        result_event = collector.of_type(EventType.TOOL_RESULT)[0]
        self.assertEqual(result_event.data["status"], "error")



    def test_denied_tool_never_emits_executing_or_ok(self) -> None:
        from orbitrelay.approvals import ApprovalDecision, ApprovalSession
        from orbitrelay.events import EventType

        client = Mock()
        client.chat.completions.create.side_effect = [
            _response(
                _assistant_message(
                    tool_calls=[
                        _tool_call(
                            "call-1",
                            "write_file",
                            '{"file_path":"x.txt","content":"nope"}',
                        )
                    ]
                )
            ),
            _response(_assistant_message(content="done")),
        ]
        collector = EventCollector()

        def authorize(requests):
            return (ApprovalDecision.deny(reason="user_denied"),)

        with tempfile.TemporaryDirectory() as workspace:
            run_agent(
                client,
                "write something",
                "test-model",
                working_directory=workspace,
                event_collector=collector,
                approval_session=ApprovalSession(authorize),
            )
            self.assertFalse(Path(workspace, "x.txt").exists())

        progress = [
            event.data.get("phase")
            for event in collector.of_type(EventType.TOOL_PROGRESS)
        ]
        self.assertIn("preparing", progress)
        self.assertIn("authorizing", progress)
        self.assertNotIn("executing", progress)
        result = collector.of_type(EventType.TOOL_RESULT)[0]
        self.assertEqual(result.data["status"], "denied")


if __name__ == "__main__":
    unittest.main()
