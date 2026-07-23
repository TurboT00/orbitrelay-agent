# story: e02s01, e02s02

import unittest

from orbitrelay.approvals import (
    ApprovalDecision,
    ApprovalDisposition,
    ApprovalRequest,
    ApprovalSession,
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


if __name__ == "__main__":
    unittest.main()
