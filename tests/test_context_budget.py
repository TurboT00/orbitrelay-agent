# story: e04s05

from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from orbitrelay.agent import run_agent
from orbitrelay.context_budget import (
    ContextBudgetError,
    apply_context_budget,
    assert_no_orphan_tool_results,
    message_size,
)


def _assistant_with_tools(call_id: str, name: str = "write_file") -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": '{"file_path":"a.txt","content":"x"}',
                },
            }
        ],
    }


def _tool_result(call_id: str, content: str = "ok") -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def _history_with_pairs(pair_count: int, filler: str = "x" * 50) -> list[dict]:
    messages: list[dict] = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "start"},
    ]
    for index in range(pair_count):
        call_id = f"call-{index}"
        messages.append(_assistant_with_tools(call_id))
        messages.append(_tool_result(call_id, content=f"{filler}-{index}"))
        messages.append({"role": "assistant", "content": f"note-{index}"})
        messages.append({"role": "user", "content": f"next-{index}"})
    return messages


class ContextBudgetTests(unittest.TestCase):
    def test_drops_oldest_pairs_first_without_orphans(self) -> None:
        history = _history_with_pairs(5, filler="y" * 80)
        total = sum(message_size(message) for message in history)
        budget = total // 2
        budgeted = apply_context_budget(history, max_chars=budget)

        self.assertLessEqual(sum(message_size(m) for m in budgeted), budget)
        self.assertEqual(budgeted[0]["role"], "system")
        assert_no_orphan_tool_results(budgeted)
        # newest user turn retained
        self.assertEqual(budgeted[-1]["content"], "next-4")
        # oldest pair content should be gone
        serialized = str(budgeted)
        self.assertNotIn("call-0", serialized)

    def test_oversized_newest_segment_fails_closed(self) -> None:
        huge = "z" * 5000
        history = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u"},
            _assistant_with_tools("call-big"),
            _tool_result("call-big", content=huge),
        ]
        pair_size = message_size(history[2]) + message_size(history[3])
        prefix = message_size(history[0])
        # Budget fits prefix + tiny amount, not the pair.
        with self.assertRaises(ContextBudgetError):
            apply_context_budget(history, max_chars=prefix + pair_size - 10)

    def test_system_prefix_over_budget_fails_closed(self) -> None:
        history = [{"role": "system", "content": "s" * 1000}]
        with self.assertRaises(ContextBudgetError):
            apply_context_budget(history, max_chars=10)

    def test_empty_and_small_histories_pass_through(self) -> None:
        self.assertEqual(apply_context_budget([], max_chars=100), [])
        history = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        self.assertEqual(apply_context_budget(history, max_chars=10_000), history)

    def test_agent_applies_budget_before_model_call(self) -> None:
        history = _history_with_pairs(4, filler="q" * 100)
        # Keep only a tight budget so older pairs must drop.
        total = sum(message_size(message) for message in history)
        budget = max(total // 3, message_size(history[0]) + 200)

        def model_dump(exclude_none=True):
            return {"role": "assistant", "content": "done"}

        message = SimpleNamespace(role="assistant", content="done", tool_calls=[])
        message.model_dump = model_dump
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=None,
        )

        with tempfile.TemporaryDirectory() as workspace:
            result = run_agent(
                client,
                "continue",
                "model",
                working_directory=workspace,
                initial_messages=history,
                max_context_chars=budget,
            )
        self.assertEqual(result, "done")
        sent = client.chat.completions.create.call_args.kwargs["messages"]
        self.assertLessEqual(sum(message_size(m) for m in sent), budget)
        assert_no_orphan_tool_results(sent)
        # new user prompt is present
        self.assertEqual(sent[-1]["role"], "user")
        self.assertEqual(sent[-1]["content"], "continue")


if __name__ == "__main__":
    unittest.main()
