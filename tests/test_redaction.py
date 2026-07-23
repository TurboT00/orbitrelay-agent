# story: e01s01
# story: e02s06

import unittest

from orbitrelay.approval_format import format_approval_record
from orbitrelay.approvals import (
    ApprovalRecord,
    RecordDisposition,
    ToolCategory,
)
from orbitrelay.redaction import REDACTED, redact_secrets


class RedactionTests(unittest.TestCase):
    def test_recursively_redacts_credential_like_fields(self):
        value = {
            "api_key": "api-secret",
            "profile": {
                "name": "work",
                "credentials": [
                    {"authorization": "Bearer token-secret"},
                    {"refresh_token": "refresh-secret"},
                ],
            },
            "password": {"nested": "must-all-disappear"},
            "model": "test-model",
        }

        redacted = redact_secrets(value)

        self.assertEqual(redacted["api_key"], REDACTED)
        self.assertEqual(redacted["profile"]["credentials"], REDACTED)
        self.assertEqual(redacted["password"], REDACTED)
        self.assertEqual(redacted["model"], "test-model")
        self.assertNotIn("token-secret", repr(redacted))
        self.assertNotIn("must-all-disappear", repr(redacted))

    def test_preserves_non_secret_nested_shapes(self):
        value = {
            "profiles": [{"name": "one"}, {"name": "two"}],
            "capabilities": ("tool_calling",),
        }

        self.assertEqual(redact_secrets(value), value)

    def test_format_approval_record_escapes_and_bounds_metadata(self):
        hostile_target = "\x1b[31msecret-path\n" + ("x" * 300)
        record = ApprovalRecord(
            sequence=7,
            call_id="call-7",
            tool_name="write_file",
            category=ToolCategory.WRITE,
            disposition=RecordDisposition.DENIED,
            reason="user_denied",
            safe_target=hostile_target,
            argument_count=None,
        )

        rendered = format_approval_record(record)

        self.assertIn("seq=7", rendered)
        self.assertIn("call_id=call-7", rendered)
        self.assertIn("disposition=denied", rendered)
        self.assertIn("reason=user_denied", rendered)
        self.assertNotIn("\x1b", rendered)
        self.assertNotIn("\n", rendered.split("target=", 1)[-1].split(" ", 1)[0])
        self.assertIn("...<truncated>", rendered)
        self.assertNotIn("x" * 300, rendered)


if __name__ == "__main__":
    unittest.main()
