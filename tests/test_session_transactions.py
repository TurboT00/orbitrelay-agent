"""Replay-safe session checkpoint contracts (e08s02)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orbitrelay.context_budget import is_replay_safe, replay_safe_prefix
from orbitrelay.events import EventCollector, EventType
from orbitrelay.sessions import SessionError, SessionStore


def _assistant_tools(*call_ids: str) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": "get_files_info", "arguments": "{}"},
            }
            for call_id in call_ids
        ],
    }


def _tool(call_id: str, content: str = "ok") -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


class ReplaySafeHelperTests(unittest.TestCase):
    def test_complete_group_is_safe(self) -> None:
        messages = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
            _assistant_tools("c1", "c2"),
            _tool("c1"),
            _tool("c2"),
            {"role": "assistant", "content": "done"},
        ]
        self.assertTrue(is_replay_safe(messages))

    def test_partial_tool_batch_is_unsafe(self) -> None:
        messages = [
            {"role": "user", "content": "u"},
            _assistant_tools("c1", "c2"),
            _tool("c1"),
        ]
        self.assertFalse(is_replay_safe(messages))
        safe = replay_safe_prefix(messages)
        self.assertEqual(safe, [{"role": "user", "content": "u"}])


class SessionTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.store = SessionStore(root=Path(self.directory.name) / "sessions")
        self.meta = self.store.create(session_id="tx1", model="m")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_commit_complete_group(self) -> None:
        prior = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "hello"},
        ]
        self.store.commit_checkpoint("tx1", prior)
        complete = [
            *prior,
            _assistant_tools("c1"),
            _tool("c1", "result-1"),
            {"role": "assistant", "content": "final"},
        ]
        collector = EventCollector()
        collector.emit(EventType.TOOL_RESULT, tool_call_id="c1", status="ok")
        self.store.commit_checkpoint("tx1", complete, events=collector.events)
        loaded = self.store.load_messages("tx1")
        self.assertEqual(loaded, complete)
        # events rewritten fully
        events_path = self.store._session_dir("tx1") / "events.jsonl"
        text = events_path.read_text(encoding="utf-8")
        self.assertIn("tool.result", text)
        self.assertEqual(text.count("\n"), 1)

    def test_refuse_partial_tool_batch_checkpoint(self) -> None:
        prior = [{"role": "user", "content": "u"}]
        self.store.commit_checkpoint("tx1", prior)
        partial = [*prior, _assistant_tools("c1", "c2"), _tool("c1")]
        with self.assertRaises(SessionError):
            self.store.commit_checkpoint("tx1", partial)
        self.assertEqual(self.store.load_messages("tx1"), prior)

    def test_load_trims_incomplete_trailing_group(self) -> None:
        prior = [
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
        ]
        self.store.commit_checkpoint("tx1", prior)
        # Simulate crash by writing incomplete messages directly.
        path = self.store._session_dir("tx1") / "messages.jsonl"
        incomplete = [
            *prior,
            _assistant_tools("c1"),
        ]
        path.write_text(
            "".join(json.dumps(message) + "\n" for message in incomplete),
            encoding="utf-8",
        )
        loaded = self.store.load_messages("tx1")
        self.assertEqual(loaded, prior)
        self.assertTrue(is_replay_safe(loaded))

    def test_interruption_boundaries_keep_prior_generation(self) -> None:
        base = [{"role": "system", "content": "s"}]
        self.store.commit_checkpoint("tx1", base)

        # user boundary
        user = [*base, {"role": "user", "content": "q1"}]
        self.store.commit_checkpoint("tx1", user)

        # final answer boundary
        final = [*user, {"role": "assistant", "content": "ans"}]
        self.store.commit_checkpoint("tx1", final)

        # complete tool batch boundary
        batch = [
            *final,
            {"role": "user", "content": "q2"},
            _assistant_tools("t1"),
            _tool("t1", "tool-ok"),
        ]
        self.store.commit_checkpoint("tx1", batch)
        self.assertEqual(self.store.load_messages("tx1"), batch)

        # partial batch must not replace
        partial = [*batch, _assistant_tools("t2")]
        with self.assertRaises(SessionError):
            self.store.commit_checkpoint("tx1", partial)
        self.assertEqual(self.store.load_messages("tx1"), batch)

    def test_unique_temp_atomic_replace_leaves_no_tmp(self) -> None:
        messages = [{"role": "user", "content": "only"}]
        self.store.commit_checkpoint("tx1", messages)
        directory = self.store._session_dir("tx1")
        temps = [path for path in directory.iterdir() if ".tmp" in path.name]
        self.assertEqual(temps, [])


if __name__ == "__main__":
    unittest.main()
