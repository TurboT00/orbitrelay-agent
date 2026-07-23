# story: e02s01, e02s02

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openai.types.chat.chat_completion import ChatCompletion

from orbitrelay.agent import MAX_MODEL_RESPONSES, TurnLimitError, run_agent
from orbitrelay.approvals import ApprovalDecision, ApprovalSession

WORKING_DIRECTORY = "/workspace"


def make_completion(*, content=None, tool_calls=None, reasoning_content=None):
    message = {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls,
    }
    if reasoning_content is not None:
        message["reasoning_content"] = reasoning_content

    return ChatCompletion.model_validate(
        {
            "id": "completion-id",
            "choices": [
                {
                    "finish_reason": "tool_calls" if tool_calls else "stop",
                    "index": 0,
                    "logprobs": None,
                    "message": message,
                }
            ],
            "created": 0,
            "model": "deepseek-v4-flash",
            "object": "chat.completion",
        }
    )


def tool_call(call_id, name="get_files_info", arguments="{}"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


class ScriptedCompletions:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def create(self, **arguments):
        self.calls.append(copy.deepcopy(arguments))
        return next(self.responses)


def scripted_client(*responses):
    completions = ScriptedCompletions(responses)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


class AgentLoopTests(unittest.TestCase):
    def test_returns_immediate_final_text(self):
        client, completions = scripted_client(make_completion(content="done"))

        result = run_agent(
            client,
            "solve it",
            "deepseek-v4-flash",
            working_directory=WORKING_DIRECTORY,
        )

        self.assertEqual(result, "done")
        self.assertEqual(len(completions.calls), 1)
        self.assertEqual(completions.calls[0]["messages"][0]["role"], "system")
        self.assertEqual(completions.calls[0]["messages"][1]["content"], "solve it")

    def test_executes_multiple_calls_and_correlates_results(self):
        first = make_completion(
            tool_calls=[
                tool_call("call-1"),
                tool_call("call-2", "get_file_content", '{"file_path":"main.py"}'),
            ]
        )
        client, completions = scripted_client(first, make_completion(content="done"))

        with patch(
            "orbitrelay.agent.execute_prepared_tool",
            side_effect=["files", "contents"],
        ) as execute:
            result = run_agent(
                client,
                "inspect",
                "deepseek-v4-flash",
                working_directory=WORKING_DIRECTORY,
            )

        self.assertEqual(result, "done")
        self.assertEqual(
            [call.args[0].name for call in execute.call_args_list],
            ["get_files_info", "get_file_content"],
        )
        second_messages = completions.calls[1]["messages"]
        self.assertEqual(second_messages[-2]["tool_call_id"], "call-1")
        self.assertEqual(second_messages[-2]["content"], "files")
        self.assertEqual(second_messages[-1]["tool_call_id"], "call-2")
        self.assertEqual(second_messages[-1]["content"], "contents")

    def test_authorizes_complete_write_batch_before_any_execution(self):
        first = make_completion(
            tool_calls=[
                tool_call(
                    "call-1",
                    "write_file",
                    '{"file_path":"approved.txt","content":"approved"}',
                ),
                tool_call(
                    "call-2",
                    "write_file",
                    '{"file_path":"denied.txt","content":"denied"}',
                ),
            ]
        )
        client, completions = scripted_client(first, make_completion(content="done"))

        with tempfile.TemporaryDirectory() as workspace:
            approved_target = Path(workspace, "approved.txt")
            denied_target = Path(workspace, "denied.txt")

            def authorize(requests):
                self.assertEqual(
                    [request.call_id for request in requests],
                    ["call-1", "call-2"],
                )
                self.assertFalse(approved_target.exists())
                self.assertFalse(denied_target.exists())
                return (
                    ApprovalDecision.approve(reason="user_approved"),
                    ApprovalDecision.deny(reason="user_denied"),
                )

            result = run_agent(
                client,
                "write files",
                "deepseek-v4-flash",
                working_directory=workspace,
                approval_session=ApprovalSession(authorize),
            )

            self.assertEqual(result, "done")
            self.assertEqual(approved_target.read_text(encoding="utf-8"), "approved")
            self.assertFalse(denied_target.exists())

        tool_messages = completions.calls[1]["messages"][-2:]
        self.assertEqual(
            [message["tool_call_id"] for message in tool_messages],
            ["call-1", "call-2"],
        )
        denial = json.loads(tool_messages[1]["content"])
        self.assertEqual(denial["error"]["code"], "approval_denied")
        self.assertEqual(denial["error"]["tool_call_id"], "call-2")

    def test_authorizes_complete_execution_batch_and_correlates_denial(self):
        first = make_completion(
            tool_calls=[
                tool_call(
                    "call-exec-1",
                    "run_python_file",
                    '{"file_path":"task.py","args":["approved"]}',
                ),
                tool_call(
                    "call-exec-2",
                    "run_python_file",
                    '{"file_path":"task.py","args":["denied"]}',
                ),
            ]
        )
        client, completions = scripted_client(first, make_completion(content="done"))

        with tempfile.TemporaryDirectory() as workspace:
            Path(workspace, "task.py").write_text("print('safe')", encoding="utf-8")
            with patch("orbitrelay.tools.run_python_file.subprocess.run") as run:
                run.return_value = SimpleNamespace(returncode=0, stdout="ran\n", stderr="")

                def authorize(requests):
                    self.assertEqual(
                        [request.call_id for request in requests],
                        ["call-exec-1", "call-exec-2"],
                    )
                    run.assert_not_called()
                    return (
                        ApprovalDecision.approve(reason="user_approved"),
                        ApprovalDecision.deny(reason="user_denied"),
                    )

                result = run_agent(
                    client,
                    "run Python",
                    "deepseek-v4-flash",
                    working_directory=workspace,
                    approval_session=ApprovalSession(authorize),
                )

            self.assertEqual(result, "done")
            run.assert_called_once()

        tool_messages = completions.calls[1]["messages"][-2:]
        self.assertEqual(tool_messages[0]["tool_call_id"], "call-exec-1")
        self.assertEqual(tool_messages[0]["content"], "STDOUT:\nran\n")
        denial = json.loads(tool_messages[1]["content"])
        self.assertEqual(denial["error"]["code"], "approval_denied")
        self.assertEqual(denial["error"]["tool_call_id"], "call-exec-2")

    def test_invalid_write_content_is_rejected_without_approval(self):
        first = make_completion(
            tool_calls=[
                tool_call(
                    "call-1",
                    "write_file",
                    '{"file_path":"invalid.txt","content":123}',
                )
            ]
        )
        client, completions = scripted_client(first, make_completion(content="done"))

        def unexpected_approval(_requests):
            self.fail("invalid write must not request approval")

        with tempfile.TemporaryDirectory() as workspace:
            result = run_agent(
                client,
                "write invalid content",
                "deepseek-v4-flash",
                working_directory=workspace,
                approval_session=ApprovalSession(unexpected_approval),
            )

            self.assertEqual(result, "done")
            self.assertFalse(Path(workspace, "invalid.txt").exists())

        tool_message = completions.calls[1]["messages"][-1]
        self.assertEqual(tool_message["tool_call_id"], "call-1")
        self.assertIn("invalid arguments", tool_message["content"])
        self.assertIn("content", tool_message["content"])

    def test_preserves_reasoning_content_across_multiple_tool_rounds(self):
        client, completions = scripted_client(
            make_completion(
                tool_calls=[tool_call("call-1")], reasoning_content="reasoning-one"
            ),
            make_completion(
                tool_calls=[tool_call("call-2")], reasoning_content="reasoning-two"
            ),
            make_completion(content="done"),
        )

        with patch("orbitrelay.agent.execute_prepared_tool", return_value="ok"):
            run_agent(
                client,
                "inspect",
                "deepseek-v4-flash",
                working_directory=WORKING_DIRECTORY,
            )

        second_messages = completions.calls[1]["messages"]
        third_messages = completions.calls[2]["messages"]
        self.assertEqual(second_messages[2]["reasoning_content"], "reasoning-one")
        self.assertEqual(third_messages[2]["reasoning_content"], "reasoning-one")
        self.assertEqual(third_messages[4]["reasoning_content"], "reasoning-two")

    def test_final_text_on_response_eight_succeeds(self):
        responses = [
            make_completion(tool_calls=[tool_call(f"call-{number}")])
            for number in range(1, MAX_MODEL_RESPONSES)
        ]
        responses.append(make_completion(content="finished at the limit"))
        client, completions = scripted_client(*responses)

        with patch(
            "orbitrelay.agent.execute_prepared_tool", return_value="ok"
        ) as execute:
            result = run_agent(
                client,
                "long task",
                "deepseek-v4-flash",
                working_directory=WORKING_DIRECTORY,
            )

        self.assertEqual(result, "finished at the limit")
        self.assertEqual(len(completions.calls), MAX_MODEL_RESPONSES)
        self.assertEqual(execute.call_count, MAX_MODEL_RESPONSES - 1)

    def test_tool_request_on_response_eight_raises_without_executing_it(self):
        responses = [
            make_completion(tool_calls=[tool_call(f"call-{number}")])
            for number in range(1, MAX_MODEL_RESPONSES + 1)
        ]
        client, completions = scripted_client(*responses)

        with patch(
            "orbitrelay.agent.execute_prepared_tool", return_value="ok"
        ) as execute:
            with self.assertRaisesRegex(TurnLimitError, "8-response limit"):
                run_agent(
                    client,
                    "long task",
                    "deepseek-v4-flash",
                    working_directory=WORKING_DIRECTORY,
                )

        self.assertEqual(len(completions.calls), MAX_MODEL_RESPONSES)
        self.assertEqual(execute.call_count, MAX_MODEL_RESPONSES - 1)

    def test_prevalidates_all_calls_before_executing_any(self):
        valid = SimpleNamespace(
            id="call-1",
            type="function",
            function=SimpleNamespace(name="get_files_info", arguments="{}"),
        )
        malformed = SimpleNamespace(
            id=None,
            type="function",
            function=SimpleNamespace(name="get_files_info", arguments="{}"),
        )
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        role="assistant", content=None, tool_calls=[valid, malformed]
                    )
                )
            ]
        )
        client, _completions = scripted_client(response)

        with patch("orbitrelay.agent.execute_prepared_tool") as execute:
            with self.assertRaisesRegex(RuntimeError, "nonempty id"):
                run_agent(
                    client,
                    "inspect",
                    "deepseek-v4-flash",
                    working_directory=WORKING_DIRECTORY,
                )

        execute.assert_not_called()

    def test_rejects_duplicate_call_ids_before_execution(self):
        response = make_completion(
            tool_calls=[tool_call("duplicate"), tool_call("duplicate")]
        )
        client, _completions = scripted_client(response)

        with patch("orbitrelay.agent.execute_prepared_tool") as execute:
            with self.assertRaisesRegex(RuntimeError, "duplicated"):
                run_agent(
                    client,
                    "inspect",
                    "deepseek-v4-flash",
                    working_directory=WORKING_DIRECTORY,
                )

        execute.assert_not_called()

    def test_rejects_completion_without_choices(self):
        client, _completions = scripted_client(SimpleNamespace(choices=[]))

        with self.assertRaisesRegex(RuntimeError, "any choices"):
            run_agent(
                client,
                "inspect",
                "deepseek-v4-flash",
                working_directory=WORKING_DIRECTORY,
            )

    def test_verbose_mode_allows_missing_usage(self):
        client, _completions = scripted_client(make_completion(content="done"))

        result = run_agent(
            client,
            "inspect",
            "deepseek-v4-flash",
            working_directory=WORKING_DIRECTORY,
            verbose=True,
        )

        self.assertEqual(result, "done")


if __name__ == "__main__":
    unittest.main()
