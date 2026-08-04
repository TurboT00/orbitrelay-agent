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
from orbitrelay.tools.get_files_info import get_files_info
from orbitrelay.tools.workspace_privacy import (
    OMITTED_ENTRIES_LINE,
    PRIVACY_DENIED_MESSAGE,
    PathSensitivity,
    authorize_exact_path,
    authorize_subtree,
    classify_relative_path,
    clear_privacy_authorization,
    clear_workspace_policy_cache,
    declare_run_exception,
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
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "get_file_content",
                                "arguments": "{}",
                            },
                        }
                    ],
                },
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



class WorkspacePrivacyDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_privacy_authorization()
        clear_workspace_policy_cache()
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.directory.name)
        (self.workspace / "README.md").write_text("hello\n", encoding="utf-8")
        (self.workspace / ".gitignore").write_text("*.log\n!keep.log\nsecret-dir/\n", encoding="utf-8")
        (self.workspace / "noise.log").write_text("log-secret\n", encoding="utf-8")
        (self.workspace / "keep.log").write_text("keep-me\n", encoding="utf-8")
        (self.workspace / "secret-dir").mkdir()
        (self.workspace / "secret-dir" / "hidden.txt").write_text("hidden\n", encoding="utf-8")
        (self.workspace / ".env").write_text("ENV=1\n", encoding="utf-8")
        (self.workspace / "id_rsa").write_text("KEY\n", encoding="utf-8")
        (self.workspace / "notes.txt").write_text("ok\n", encoding="utf-8")
        (self.workspace / ".orbitrelayignore").write_text("private.dat\n", encoding="utf-8")
        (self.workspace / "private.dat").write_text("orbit-secret\n", encoding="utf-8")

    def tearDown(self) -> None:
        clear_privacy_authorization()
        clear_workspace_policy_cache()
        self.directory.cleanup()

    def test_sp08_gitignore_and_negation(self) -> None:
        ignored = classify_relative_path("noise.log", workspace_root=str(self.workspace))
        kept = classify_relative_path("keep.log", workspace_root=str(self.workspace))
        nested = classify_relative_path(
            "secret-dir/hidden.txt", workspace_root=str(self.workspace)
        )
        self.assertEqual(ignored.rule_id, "SP-08")
        self.assertFalse(ignored.allowed)
        self.assertTrue(kept.allowed)
        self.assertEqual(nested.rule_id, "SP-08")
        self.assertFalse(nested.allowed)
        self.assertNotIn(
            "log-secret",
            get_file_content(str(self.workspace), "noise.log"),
        )
        self.assertEqual(get_file_content(str(self.workspace), "keep.log"), "keep-me\n")

    def test_orbitrelayignore_deny_only(self) -> None:
        result = classify_relative_path(
            "private.dat", workspace_root=str(self.workspace)
        )
        self.assertEqual(result.rule_id, "SP-08")
        self.assertFalse(result.allowed)
        denial = get_file_content(str(self.workspace), "private.dat")
        self.assertTrue(denial.startswith(PRIVACY_DENIED_MESSAGE))
        self.assertNotIn("orbit-secret", denial)

    def test_orbitrelayignore_rejects_negation(self) -> None:
        (self.workspace / ".orbitrelayignore").write_text("*.tmp\n!keep.tmp\n", encoding="utf-8")
        clear_workspace_policy_cache()
        (self.workspace / "x.tmp").write_text("tmp\n", encoding="utf-8")
        result = get_file_content(str(self.workspace), "x.tmp")
        self.assertIn("invalid .orbitrelayignore", result)
        self.assertIn("negation", result)
        listing = get_files_info(str(self.workspace))
        self.assertIn("invalid .orbitrelayignore", listing)

    def test_listing_omits_protected_names_and_sizes(self) -> None:
        listing = get_files_info(str(self.workspace))
        self.assertIn("README.md", listing)
        self.assertIn("notes.txt", listing)
        self.assertIn("keep.log", listing)
        self.assertIn(".gitignore", listing)
        for banned in (
            "noise.log",
            "private.dat",
            ".env",
            "id_rsa",
            "secret-dir",
            "log-secret",
            "orbit-secret",
            "ENV=1",
            "KEY",
        ):
            self.assertNotIn(banned, listing)
        self.assertIn(OMITTED_ENTRIES_LINE, listing)
        # sizes of omitted entries must not appear via those names
        self.assertNotRegex(listing, r"noise\.log: file_size=")

    def test_direct_read_and_discovery_share_classification(self) -> None:
        for relative in (
            "notes.txt",
            "noise.log",
            "keep.log",
            "private.dat",
            ".env",
            "id_rsa",
            "secret-dir/hidden.txt",
        ):
            with self.subTest(relative=relative):
                classification = classify_relative_path(
                    relative, workspace_root=str(self.workspace)
                )
                if classification.allowed:
                    content = get_file_content(str(self.workspace), relative)
                    self.assertFalse(content.startswith(PRIVACY_DENIED_MESSAGE))
                else:
                    content = get_file_content(str(self.workspace), relative)
                    self.assertTrue(
                        content.startswith(PRIVACY_DENIED_MESSAGE)
                        or content.startswith("Error: invalid .orbitrelayignore"),
                        content,
                    )
                parent = str(Path(relative).parent).replace("\\", "/")
                if parent == ".":
                    listing = get_files_info(str(self.workspace), ".")
                    name = Path(relative).name
                    if classification.discoverable:
                        self.assertIn(name, listing)
                    else:
                        self.assertNotIn(name, listing)

    def test_authorized_exact_file_is_discoverable_and_readable(self) -> None:
        authorize_exact_path(".env")
        classification = classify_relative_path(
            ".env", workspace_root=str(self.workspace)
        )
        self.assertTrue(classification.allowed)
        self.assertEqual(classification.sensitivity, PathSensitivity.SENSITIVE)
        self.assertEqual(get_file_content(str(self.workspace), ".env"), "ENV=1\n")
        listing = get_files_info(str(self.workspace))
        self.assertIn(".env", listing)
        # absolute deny still omitted even if somehow authorized
        authorize_exact_path("id_rsa")
        self.assertFalse(
            classify_relative_path("id_rsa", workspace_root=str(self.workspace)).allowed
        )
        self.assertNotIn("id_rsa", get_files_info(str(self.workspace)))
        self.assertNotIn("KEY", get_file_content(str(self.workspace), "id_rsa"))

    def test_authorized_subtree_reveals_non_absolute_deny_only(self) -> None:
        sensitive_dir = self.workspace / "vault"
        sensitive_dir.mkdir()
        (sensitive_dir / "note.txt").write_text("visible\n", encoding="utf-8")
        (sensitive_dir / "id_ed25519").write_text("ABS\n", encoding="utf-8")
        # Make the subtree sensitive via orbitrelayignore
        (self.workspace / ".orbitrelayignore").write_text("vault/\n", encoding="utf-8")
        clear_workspace_policy_cache()
        self.assertFalse(
            classify_relative_path(
                "vault/note.txt", workspace_root=str(self.workspace)
            ).allowed
        )
        authorize_subtree("vault")
        self.assertTrue(
            classify_relative_path(
                "vault/note.txt", workspace_root=str(self.workspace)
            ).allowed
        )
        self.assertFalse(
            classify_relative_path(
                "vault/id_ed25519", workspace_root=str(self.workspace)
            ).allowed
        )
        listing = get_files_info(str(self.workspace), "vault")
        self.assertIn("note.txt", listing)
        self.assertNotIn("id_ed25519", listing)
        self.assertIn(OMITTED_ENTRIES_LINE, listing)
        self.assertEqual(
            get_file_content(str(self.workspace), "vault/note.txt"), "visible\n"
        )
        self.assertNotIn(
            "ABS", get_file_content(str(self.workspace), "vault/id_ed25519")
        )

    def test_listing_protected_directory_fails_closed(self) -> None:
        listing = get_files_info(str(self.workspace), "secret-dir")
        self.assertTrue(
            listing.startswith(PRIVACY_DENIED_MESSAGE)
            or "protected path denied" in listing,
            listing,
        )
        self.assertNotIn("hidden.txt", listing)



class OneRunExceptionTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_privacy_authorization()
        clear_workspace_policy_cache()
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.directory.name)
        (self.workspace / "notes.txt").write_text("ok\n", encoding="utf-8")
        (self.workspace / ".env").write_text("SECRET=1\n", encoding="utf-8")
        (self.workspace / ".env.local").write_text("OTHER=1\n", encoding="utf-8")
        (self.workspace / "vault").mkdir()
        (self.workspace / "vault" / "note.txt").write_text("v\n", encoding="utf-8")
        (self.workspace / "vault" / "id_rsa").write_text("KEY\n", encoding="utf-8")
        (self.workspace / "id_ed25519").write_text("ABS\n", encoding="utf-8")

    def tearDown(self) -> None:
        clear_privacy_authorization()
        clear_workspace_policy_cache()
        self.directory.cleanup()

    def test_declare_exact_file_authorizes_only_that_path(self) -> None:
        declare_run_exception(str(self.workspace), ".env", scope="file")
        self.assertEqual(
            get_file_content(str(self.workspace), ".env"), "SECRET=1\n"
        )
        sibling = get_file_content(str(self.workspace), ".env.local")
        self.assertTrue(sibling.startswith(PRIVACY_DENIED_MESSAGE))
        listing = get_files_info(str(self.workspace))
        self.assertIn(".env", listing)
        self.assertNotIn(".env.local", listing)

    def test_declare_subtree_is_bounded_and_keeps_absolute_deny(self) -> None:
        declare_run_exception(str(self.workspace), "vault", scope="subtree")
        self.assertEqual(
            get_file_content(str(self.workspace), "vault/note.txt"), "v\n"
        )
        denied = get_file_content(str(self.workspace), "vault/id_rsa")
        self.assertTrue(denied.startswith(PRIVACY_DENIED_MESSAGE))
        outside = get_file_content(str(self.workspace), ".env")
        self.assertTrue(outside.startswith(PRIVACY_DENIED_MESSAGE))
        listing = get_files_info(str(self.workspace), "vault")
        self.assertIn("note.txt", listing)
        self.assertNotIn("id_rsa", listing)

    def test_declare_rejects_absolute_deny_and_escape(self) -> None:
        with self.assertRaisesRegex(ValueError, "absolute-deny"):
            declare_run_exception(str(self.workspace), "id_ed25519", scope="file")
        with self.assertRaisesRegex(ValueError, "escapes"):
            declare_run_exception(str(self.workspace), "../outside", scope="file")
        with self.assertRaisesRegex(ValueError, "existing file"):
            declare_run_exception(str(self.workspace), "missing.env", scope="file")

    def test_authority_is_process_scoped_and_cleared(self) -> None:
        declare_run_exception(str(self.workspace), ".env", scope="file")
        self.assertEqual(get_file_content(str(self.workspace), ".env"), "SECRET=1\n")
        clear_privacy_authorization()
        denied = get_file_content(str(self.workspace), ".env")
        self.assertTrue(denied.startswith(PRIVACY_DENIED_MESSAGE))


class CliSensitiveExceptionTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_privacy_authorization()
        self.directory = tempfile.TemporaryDirectory()
        self.home = Path(self.directory.name) / "home"
        self.home.mkdir()
        self.workspace = Path(self.directory.name) / "ws"
        self.workspace.mkdir()
        (self.workspace / ".env").write_text("CLI_SECRET=1\n", encoding="utf-8")
        from orbitrelay.connection_service import ConnectionService
        from orbitrelay.profile_store import ProfileRepository
        from orbitrelay.providers import ProviderId

        self.repository = ProfileRepository(self.home / "profiles.json")
        self.store = type(
            "S",
            (),
            {
                "values": {},
                "set_secret": lambda self, k, v: self.values.__setitem__(k, v),
                "get_secret": lambda self, k: self.values[k],
                "delete_secret": lambda self, k: self.values.pop(k, None),
            },
        )()
        # proper fake store
        class Fake:
            def __init__(self):
                self.values = {}
            def set_secret(self, k, v):
                self.values[k] = v
            def get_secret(self, k):
                from orbitrelay.credentials import CredentialNotFoundError
                try:
                    return self.values[k]
                except KeyError as exc:
                    raise CredentialNotFoundError(k) from exc
            def delete_secret(self, k):
                self.values.pop(k, None)
        self.store = Fake()
        ConnectionService(self.repository, self.store).connect_api_key(
            ProviderId.OPENAI, "k"
        )

    def tearDown(self) -> None:
        clear_privacy_authorization()
        self.directory.cleanup()

    def test_cli_applies_and_clears_sensitive_exception(self) -> None:
        import io
        import os
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        from orbitrelay import cli

        final = SimpleNamespace(
            role="assistant",
            content="done",
            tool_calls=None,
            model_dump=lambda exclude_none=True: {
                "role": "assistant",
                "content": "done",
            },
        )
        client = Mock()
        client.chat.completions.create = Mock(
            return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=final)], usage=None
            )
        )
        out = io.StringIO()
        err = io.StringIO()
        with (
            patch.dict(os.environ, {"ORBITRELAY_HOME": str(self.home)}, clear=False),
            patch("orbitrelay.cli.OpenAI", return_value=client),
            patch("sys.stdout", out),
            patch("sys.stderr", err),
        ):
            code = cli.main(
                [
                    "hello",
                    "--workspace",
                    str(self.workspace),
                    "--allow-sensitive-read",
                    ".env",
                ],
                profile_repository=self.repository,
                credential_store=self.store,
            )
        self.assertEqual(code, 0)
        # authority cleared after run
        denied = get_file_content(str(self.workspace), ".env")
        self.assertTrue(denied.startswith(PRIVACY_DENIED_MESSAGE))

    def test_cli_rejects_absolute_deny_declaration(self) -> None:
        import io
        import os
        from unittest.mock import patch

        from orbitrelay import cli

        (self.workspace / "id_rsa").write_text("K\n", encoding="utf-8")
        out = io.StringIO()
        err = io.StringIO()
        with (
            patch.dict(os.environ, {"ORBITRELAY_HOME": str(self.home)}, clear=False),
            patch("sys.stdout", out),
            patch("sys.stderr", err),
        ):
            code = cli.main(
                [
                    "hello",
                    "--workspace",
                    str(self.workspace),
                    "--allow-sensitive-read",
                    "id_rsa",
                ],
                profile_repository=self.repository,
                credential_store=self.store,
            )
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("absolute-deny", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())



class SensitiveSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_privacy_authorization()
        clear_workspace_policy_cache()
        self.directory = tempfile.TemporaryDirectory()
        self.home = Path(self.directory.name) / "home"
        self.home.mkdir()
        self.workspace = Path(self.directory.name) / "ws"
        self.workspace.mkdir()
        (self.workspace / ".env").write_text("TOP=1\n", encoding="utf-8")
        self.sessions = SessionStore(root=self.home / "sessions")
        self.meta = self.sessions.create(
            session_id="sens1", workspace=str(self.workspace), model="m"
        )

    def tearDown(self) -> None:
        clear_privacy_authorization()
        clear_workspace_policy_cache()
        self.directory.cleanup()

    def test_default_sensitive_run_is_ephemeral(self) -> None:
        import io
        import os
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        from orbitrelay import cli
        from orbitrelay.connection_service import ConnectionService
        from orbitrelay.profile_store import ProfileRepository
        from orbitrelay.providers import ProviderId

        repository = ProfileRepository(self.home / "profiles.json")
        class Fake:
            def __init__(self):
                self.values = {}
            def set_secret(self, k, v):
                self.values[k] = v
            def get_secret(self, k):
                from orbitrelay.credentials import CredentialNotFoundError
                try:
                    return self.values[k]
                except KeyError as exc:
                    raise CredentialNotFoundError(k) from exc
            def delete_secret(self, k):
                self.values.pop(k, None)
        store = Fake()
        ConnectionService(repository, store).connect_api_key(ProviderId.OPENAI, "k")
        final = SimpleNamespace(
            role="assistant",
            content="done",
            tool_calls=None,
            model_dump=lambda exclude_none=True: {"role": "assistant", "content": "done"},
        )
        client = Mock()
        client.chat.completions.create = Mock(
            return_value=SimpleNamespace(choices=[SimpleNamespace(message=final)], usage=None)
        )
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, {"ORBITRELAY_HOME": str(self.home)}, clear=False),
            patch("orbitrelay.cli.OpenAI", return_value=client),
            patch("sys.stdout", out),
            patch("sys.stderr", err),
        ):
            code = cli.main(
                [
                    "use secrets",
                    "--workspace",
                    str(self.workspace),
                    "--session",
                    "sens1",
                    "--allow-sensitive-read",
                    ".env",
                ],
                profile_repository=repository,
                credential_store=store,
            )
        self.assertEqual(code, 0)
        # Without persist consent, messages stay empty (ephemeral).
        self.assertEqual(self.sessions.load_messages("sens1"), [])
        self.assertFalse(self.sessions.get_metadata("sens1").sensitive)

    def test_persist_consent_marks_session_and_requires_renewed_authority(self) -> None:
        import io
        import os
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        from orbitrelay import cli
        from orbitrelay.connection_service import ConnectionService
        from orbitrelay.profile_store import ProfileRepository
        from orbitrelay.providers import ProviderId

        repository = ProfileRepository(self.home / "profiles.json")
        class Fake:
            def __init__(self):
                self.values = {}
            def set_secret(self, k, v):
                self.values[k] = v
            def get_secret(self, k):
                from orbitrelay.credentials import CredentialNotFoundError
                try:
                    return self.values[k]
                except KeyError as exc:
                    raise CredentialNotFoundError(k) from exc
            def delete_secret(self, k):
                self.values.pop(k, None)
        store = Fake()
        ConnectionService(repository, store).connect_api_key(ProviderId.OPENAI, "k")
        final = SimpleNamespace(
            role="assistant",
            content="done",
            tool_calls=None,
            model_dump=lambda exclude_none=True: {"role": "assistant", "content": "done"},
        )
        client = Mock()
        client.chat.completions.create = Mock(
            return_value=SimpleNamespace(choices=[SimpleNamespace(message=final)], usage=None)
        )
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, {"ORBITRELAY_HOME": str(self.home)}, clear=False),
            patch("orbitrelay.cli.OpenAI", return_value=client),
            patch("sys.stdout", out),
            patch("sys.stderr", err),
        ):
            code = cli.main(
                [
                    "use secrets",
                    "--workspace",
                    str(self.workspace),
                    "--session",
                    "sens1",
                    "--allow-sensitive-read",
                    ".env",
                    "--persist-sensitive-session",
                ],
                profile_repository=repository,
                credential_store=store,
            )
        self.assertEqual(code, 0)
        meta = self.sessions.get_metadata("sens1")
        self.assertTrue(meta.sensitive)
        self.assertIn(".env", meta.sensitive_authority)
        self.assertTrue(self.sessions.load_messages("sens1"))

        # Resume without renewed authority fails before provider.
        out2, err2 = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, {"ORBITRELAY_HOME": str(self.home)}, clear=False),
            patch("orbitrelay.cli.OpenAI") as openai,
            patch("sys.stdout", out2),
            patch("sys.stderr", err2),
        ):
            code2 = cli.main(
                [
                    "continue",
                    "--workspace",
                    str(self.workspace),
                    "--session",
                    "sens1",
                ],
                profile_repository=repository,
                credential_store=store,
            )
        self.assertEqual(code2, 1)
        self.assertEqual(out2.getvalue(), "")
        self.assertIn("renew", err2.getvalue().lower())
        openai.assert_not_called()

        # Resume with matching authority succeeds.
        client2 = Mock()
        client2.chat.completions.create = Mock(
            return_value=SimpleNamespace(choices=[SimpleNamespace(message=final)], usage=None)
        )
        out3, err3 = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, {"ORBITRELAY_HOME": str(self.home)}, clear=False),
            patch("orbitrelay.cli.OpenAI", return_value=client2),
            patch("sys.stdout", out3),
            patch("sys.stderr", err3),
        ):
            code3 = cli.main(
                [
                    "continue",
                    "--workspace",
                    str(self.workspace),
                    "--session",
                    "sens1",
                    "--allow-sensitive-read",
                    ".env",
                ],
                profile_repository=repository,
                credential_store=store,
            )
        self.assertEqual(code3, 0)


if __name__ == "__main__":
    unittest.main()
