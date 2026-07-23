# story: e01s01

import unittest

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


if __name__ == "__main__":
    unittest.main()
