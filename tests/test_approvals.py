# story: e02s01, e02s02
# story: e02s03
# story: e02s04

import unittest
from io import StringIO

from orbitrelay.approvals import (
    ApprovalDecision,
    ApprovalDisposition,
    ApprovalMode,
    ApprovalRequest,
    ApprovalSession,
    TerminalAuthorizer,
    ToolCategory,
    format_approval_request,
)


class ApprovalRequestTests(unittest.TestCase):
    def test_write_request_contains_safe_context_without_content(self):
        secret_content = "provider-secret-value"

        request = ApprovalRequest.for_write(
            call_id="call-1",
            target="notes.txt",
            content_length=len(secret_content),
        )

        self.assertEqual(request.call_id, "call-1")
        self.assertEqual(request.tool_name, "write_file")
        self.assertEqual(request.category, ToolCategory.WRITE)
        self.assertEqual(
            request.safe_context,
            (("target", "notes.txt"), ("content_length", len(secret_content))),
        )
        self.assertNotIn(secret_content, repr(request))

    def test_execution_request_formats_bounded_control_escaped_arguments(self):
        hostile_argument = "\x1b[31mspoof\n" + ("x" * 300)

        request = ApprovalRequest.for_execution(
            call_id="call-exec",
            workspace="/trusted/workspace",
            target="scripts/task.py",
            arguments=("--label", hostile_argument),
        )
        preview = format_approval_request(request)

        self.assertEqual(request.tool_name, "run_python_file")
        self.assertEqual(request.category, ToolCategory.EXECUTE)
        self.assertIn("python='current-interpreter'", preview)
        self.assertIn("workspace='/trusted/workspace'", preview)
        self.assertIn("file='scripts/task.py'", preview)
        self.assertIn("argument_count=2", preview)
        self.assertIn("\\x1b", preview)
        self.assertIn("\\n", preview)
        self.assertIn("...<truncated>", preview)
        self.assertNotIn("\x1b", preview)


class ApprovalDecisionTests(unittest.TestCase):
    def test_approval_exposes_a_stable_reason(self):
        decision = ApprovalDecision.approve(reason="user_approved")

        self.assertEqual(decision.disposition, ApprovalDisposition.APPROVED)
        self.assertEqual(decision.reason, "user_approved")
        self.assertTrue(decision.approved)

    def test_denial_exposes_a_stable_reason(self):
        decision = ApprovalDecision.deny(reason="user_denied")

        self.assertEqual(decision.disposition, ApprovalDisposition.DENIED)
        self.assertEqual(decision.reason, "user_denied")
        self.assertFalse(decision.approved)


class ApprovalSessionTests(unittest.TestCase):
    def test_read_only_policy_allows_reads_and_denies_consequential_tools(self):
        def unexpected_authorizer(_requests):
            self.fail("read-only policy must not request interactive approval")

        session = ApprovalSession(unexpected_authorizer, mode=ApprovalMode.READ_ONLY)
        read = ApprovalRequest(
            call_id="call-read",
            tool_name="get_files_info",
            category=ToolCategory.READ,
            safe_context=(),
        )
        write = ApprovalRequest.for_write(
            call_id="call-write", target="notes.txt", content_length=1
        )

        read_decision, write_decision = session.authorize((read, write))

        self.assertTrue(read_decision.approved)
        self.assertEqual(read_decision.reason, "read_allowed")
        self.assertFalse(write_decision.approved)
        self.assertEqual(write_decision.reason, "read_only_policy")

    def test_timeout_input_denies_before_authority_is_granted(self):
        class TimeoutInput:
            def readline(self):
                raise TimeoutError("approval expired")

        authorizer = TerminalAuthorizer(TimeoutInput(), StringIO())
        request = ApprovalRequest.for_write(
            call_id="call-timeout", target="notes.txt", content_length=1
        )

        (decision,) = ApprovalSession(authorizer).authorize((request,))

        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "approval_timeout")

    def test_malformed_input_exhaustion_denies_after_bounded_retries(self):
        output = StringIO()
        authorizer = TerminalAuthorizer(StringIO("maybe\nunknown\n?\n"), output)
        request = ApprovalRequest.for_write(
            call_id="call-invalid", target="notes.txt", content_length=1
        )

        (decision,) = ApprovalSession(authorizer).authorize((request,))

        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "approval_invalid_input")
        self.assertEqual(output.getvalue().count("Approve write_file"), 3)

    def test_noninteractive_confirmation_denies_without_a_prompt(self):
        output = StringIO()
        authorizer = TerminalAuthorizer(StringIO("y\n"), output, require_tty=True)
        request = ApprovalRequest.for_write(
            call_id="call-pipe", target="notes.txt", content_length=1
        )

        (decision,) = ApprovalSession(authorizer).authorize((request,))

        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "approval_noninteractive")
        self.assertEqual(output.getvalue(), "")

    def test_disable_decision_denies_later_same_tool_without_authorizer(self):
        authorization_calls = []

        def disable(requests):
            authorization_calls.append(requests)
            return (ApprovalDecision.disable_tool(),)

        session = ApprovalSession(disable)
        first = ApprovalRequest.for_write(
            call_id="call-1", target="first.txt", content_length=1
        )
        later = ApprovalRequest.for_write(
            call_id="call-2", target="later.txt", content_length=1
        )

        (first_decision,) = session.authorize((first,))
        (later_decision,) = session.authorize((later,))

        self.assertEqual(first_decision.reason, "user_disabled_tool")
        self.assertEqual(later_decision.reason, "tool_disabled_for_run")
        self.assertEqual(len(authorization_calls), 1)
        self.assertEqual(session.disabled_tools, frozenset({"write_file"}))

    def test_deny_once_does_not_disable_later_same_tool(self):
        output = StringIO()
        session = ApprovalSession(TerminalAuthorizer(StringIO("n\ny\n"), output))
        requests = tuple(
            ApprovalRequest.for_write(
                call_id=f"call-{number}",
                target=f"file-{number}.txt",
                content_length=1,
            )
            for number in (1, 2)
        )

        decisions = session.authorize(requests)

        self.assertEqual(
            [decision.reason for decision in decisions],
            ["user_denied", "user_approved"],
        )
        self.assertEqual(output.getvalue().count("Approve write_file"), 2)
        self.assertEqual(session.disabled_tools, frozenset())

    def test_new_session_does_not_inherit_disabled_tools(self):
        request = ApprovalRequest.for_write(
            call_id="call-1", target="notes.txt", content_length=1
        )
        first = ApprovalSession(lambda _requests: (ApprovalDecision.disable_tool(),))
        fresh = ApprovalSession(
            lambda _requests: (ApprovalDecision.approve(reason="user_approved"),)
        )

        first.authorize((request,))
        (fresh_decision,) = fresh.authorize((request,))

        self.assertTrue(fresh_decision.approved)
        self.assertEqual(fresh.disabled_tools, frozenset())


if __name__ == "__main__":
    unittest.main()
