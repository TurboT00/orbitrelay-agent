import unittest

from orbitrelay.approvals import ApprovalRequest, ToolCategory


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


if __name__ == "__main__":
    unittest.main()
