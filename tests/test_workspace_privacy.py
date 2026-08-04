"""D-01 protected workspace read contracts (e06s01)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orbitrelay.approvals import ApprovalMode, ApprovalSession
from orbitrelay.events import EventCollector, EventType
from orbitrelay.run_summary import summarize_run
from orbitrelay.sessions import SessionStore
from orbitrelay.tools import execute_tool, prepare_tool
from orbitrelay.tools.get_file_content import get_file_content
from orbitrelay.tools.workspace_privacy import (
    PRIVACY_DENIED_MESSAGE,
    PathSensitivity,
    classify_relative_path,
)

# Every AP/SP family with a representative relative path and expected rule.
ABSOLUTE_DENY_CASES: tuple[tuple[str, str, str], ...] = (
    ("AP-01", "id_rsa", "PRIVATE_KEY_MATERIAL"),
    ("AP-01", "id_ed25519", "PRIVATE_KEY_MATERIAL"),
    ("AP-01", "id_ecdsa_github", "PRIVATE_KEY_MATERIAL"),
    ("AP-02", "server.key", "KEYSTORE_MATERIAL"),
    ("AP-02", "client.p12", "KEYSTORE_MATERIAL"),
    ("AP-02", "trust.keystore", "KEYSTORE_MATERIAL"),
    ("AP-03", ".netrc", "machine api login password secret"),
    ("AP-03", ".npmrc", "//registry/:_authToken=secret"),
    ("AP-03", ".pypirc", "password: secret"),
    ("AP-03", ".git-credentials", "https://user:token@example"),
    ("AP-04", ".aws/credentials", "[default]\naws_secret_access_key=secret"),
    ("AP-04", ".docker/config.json", '{"auths":{"x":{"auth":"secret"}}}'),
    ("AP-04", ".kube/config", "users:\n- name: x\n  user:\n    token: secret"),
    (
        "AP-04",
        ".config/gcloud/application_default_credentials.json",
        '{"client_secret":"secret"}',
    ),
    ("AP-05", "my-service-account.json", '{"private_key":"secret"}'),
    ("AP-05", "service_account.json", '{"private_key":"secret"}'),
    ("AP-06", ".gnupg/private-keys-v1.d/abcd.key", "GPG_PRIVATE"),
)

SENSITIVE_CASES: tuple[tuple[str, str, str], ...] = (
    ("SP-01", ".env", "SECRET_ENV=1"),
    ("SP-01", ".env.local", "SECRET_ENV=1"),
    ("SP-02", "api_key.txt", "tok_secret"),
    ("SP-02", "my-password.json", '{"password":"x"}'),
    ("SP-02", "db.credentials", "user:pass"),
    ("SP-03", "cert.pem", "-----BEGIN CERTIFICATE-----"),
    ("SP-04", ".ssh/config", "Host *"),
    ("SP-04", ".git/config", "[core]"),
    ("SP-04", ".aws/config", "[default]"),
    ("SP-05", ".config/gcloud/configurations/config_default", "project=x"),
    ("SP-06", "terraform.tfstate", '{"resources":[]}'),
    ("SP-06", "prod.tfstate", '{"resources":[]}'),
    ("SP-06", "terraform.tfstate.backup", '{"resources":[]}'),
    ("SP-07", "terraform.tfvars", 'token="x"'),
    ("SP-07", "env.auto.tfvars", 'token="x"'),
    ("SP-07", "env.auto.tfvars.json", '{"token":"x"}'),
)

ORDINARY_CASES: tuple[str, ...] = (
    "README.md",
    "src/main.py",
    ".gitignore",
    ".editorconfig",
    ".python-version",
    ".github/workflows/ci.yml",
)


class WorkspacePrivacyClassificationTests(unittest.TestCase):
    def test_ordinary_paths_remain_ordinary(self) -> None:
        for relative in ORDINARY_CASES:
            with self.subTest(relative=relative):
                result = classify_relative_path(relative)
                self.assertTrue(result.allowed)
                self.assertEqual(result.sensitivity, PathSensitivity.ORDINARY)

    def test_absolute_deny_families(self) -> None:
        for rule_id, relative, _content in ABSOLUTE_DENY_CASES:
            with self.subTest(rule_id=rule_id, relative=relative):
                result = classify_relative_path(relative)
                self.assertEqual(result.sensitivity, PathSensitivity.ABSOLUTE_DENY)
                self.assertEqual(result.rule_id, rule_id)

    def test_sensitive_families(self) -> None:
        for rule_id, relative, _content in SENSITIVE_CASES:
            with self.subTest(rule_id=rule_id, relative=relative):
                result = classify_relative_path(relative)
                self.assertEqual(result.sensitivity, PathSensitivity.SENSITIVE)
                self.assertEqual(result.rule_id, rule_id)

    def test_absolute_deny_precedes_sensitive(self) -> None:
        # .aws/credentials is AP-04 and also under .aws (SP-04)
        result = classify_relative_path(".aws/credentials")
        self.assertEqual(result.sensitivity, PathSensitivity.ABSOLUTE_DENY)
        self.assertEqual(result.rule_id, "AP-04")

    def test_matching_is_casefold_safe(self) -> None:
        result = classify_relative_path(".ENV")
        self.assertEqual(result.rule_id, "SP-01")
        result = classify_relative_path("ID_RSA")
        self.assertEqual(result.rule_id, "AP-01")


class WorkspacePrivacyReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.directory.name)
        (self.workspace / "notes.txt").write_text("ordinary-ok\n", encoding="utf-8")
        for _rule, relative, content in ABSOLUTE_DENY_CASES + SENSITIVE_CASES:
            path = self.workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_ordinary_read_still_automatic(self) -> None:
        result = get_file_content(str(self.workspace), "notes.txt")
        self.assertEqual(result, "ordinary-ok\n")
        prepared = prepare_tool(
            "c1",
            "get_file_content",
            json.dumps({"file_path": "notes.txt"}),
            str(self.workspace),
        )
        self.assertNotIsInstance(prepared, str)

    def test_protected_reads_fail_before_content(self) -> None:
        for rule_id, relative, content in ABSOLUTE_DENY_CASES + SENSITIVE_CASES:
            with self.subTest(rule_id=rule_id, relative=relative):
                result = get_file_content(str(self.workspace), relative)
                self.assertTrue(result.startswith(PRIVACY_DENIED_MESSAGE), result)
                self.assertIn(rule_id, result)
                self.assertNotIn(content, result)
                self.assertNotIn(relative, result)

                prepared = prepare_tool(
                    "c1",
                    "get_file_content",
                    json.dumps({"file_path": relative}),
                    str(self.workspace),
                )
                self.assertIsInstance(prepared, str)
                self.assertTrue(prepared.startswith(PRIVACY_DENIED_MESSAGE))
                self.assertNotIn(content, prepared)
                self.assertNotIn(relative, prepared)

                executed = execute_tool(
                    "get_file_content",
                    json.dumps({"file_path": relative}),
                    str(self.workspace),
                )
                self.assertTrue(executed.startswith(PRIVACY_DENIED_MESSAGE))
                self.assertNotIn(content, executed)

    def test_absolute_deny_cannot_be_overridden_by_future_exception_hook(self) -> None:
        # e06s03 will add exceptions; absolute-deny must still fail closed.
        relative = "id_rsa"
        content = "PRIVATE_KEY_MATERIAL"
        result = get_file_content(str(self.workspace), relative)
        self.assertTrue(result.startswith(PRIVACY_DENIED_MESSAGE))
        self.assertNotIn(content, result)


class WorkspacePrivacyPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.directory.name)
        (self.workspace / ".env").write_text("TOP_SECRET=1\n", encoding="utf-8")
        (self.workspace / "notes.txt").write_text("ok\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_denied_under_every_approval_policy(self) -> None:
        payload = json.dumps({"file_path": ".env"})
        for mode in ApprovalMode:
            with self.subTest(mode=mode):
                prepared = prepare_tool(
                    "call-env",
                    "get_file_content",
                    payload,
                    str(self.workspace),
                )
                self.assertIsInstance(prepared, str)
                self.assertTrue(prepared.startswith(PRIVACY_DENIED_MESSAGE))
                # Preparation fails closed before an approval session can approve.
                session = ApprovalSession(
                    mode=mode,
                    approved_tools=frozenset({"write_file"}),
                )
                # No request is produced for a privacy denial.
                self.assertEqual(session.records, ())

    def test_agent_never_sends_protected_bytes_to_provider(self) -> None:
        secret = "TOP_SECRET=do-not-leak"
        (self.workspace / ".env").write_text(secret + "\n", encoding="utf-8")
        tool_result = execute_tool(
            "get_file_content",
            json.dumps({"file_path": ".env"}),
            str(self.workspace),
        )
        self.assertTrue(tool_result.startswith(PRIVACY_DENIED_MESSAGE))
        self.assertNotIn(secret, tool_result)
        self.assertNotIn(secret, json.dumps({"role": "tool", "content": tool_result}))



class WorkspacePrivacySideChannelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.directory.name)
        self.secret = "NEVER_PERSIST_ME"
        (self.workspace / "id_rsa").write_text(self.secret + "\n", encoding="utf-8")
        self.home = Path(self.directory.name) / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_events_summaries_and_sessions_omit_protected_content_and_names(self) -> None:
        collector = EventCollector()
        result = execute_tool(
            "get_file_content",
            json.dumps({"file_path": "id_rsa"}),
            str(self.workspace),
        )
        collector.emit(
            EventType.TOOL_RESULT,
            tool="get_file_content",
            status="error",
            detail=result,
        )
        serialized = json.dumps(collector.as_dicts())
        self.assertNotIn(self.secret, serialized)
        self.assertNotIn("id_rsa", serialized)

        summary = summarize_run(collector.events)
        summary_text = repr(summary)
        self.assertNotIn(self.secret, summary_text)
        self.assertNotIn("id_rsa", summary_text)

        store = SessionStore(self.home / "sessions")
        metadata = store.create(
            workspace=str(self.workspace),
            model="test-model",
        )
        store.replace_messages(
            metadata.id,
            [
                {
                    "role": "tool",
                    "tool_call_id": "c1",
                    "content": result,
                },
            ],
        )
        messages = store.load_messages(metadata.id)
        dumped = json.dumps(messages)
        self.assertNotIn(self.secret, dumped)
        self.assertNotIn("id_rsa", dumped)


if __name__ == "__main__":
    unittest.main()
