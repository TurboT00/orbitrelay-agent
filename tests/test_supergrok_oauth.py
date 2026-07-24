# story: e03s02

from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from orbitrelay import cli
from orbitrelay.auth_cli import run_auth_cli
from orbitrelay.credentials import CredentialNotFoundError
from orbitrelay.profile_store import ProfileRepository
from orbitrelay.profiles import AuthKind
from orbitrelay.supergrok_oauth import (
    SUPERGROK_PROFILE_NAME,
    SuperGrokAuthService,
    SuperGrokOAuthClient,
    SuperGrokOAuthError,
    SuperGrokReauthRequired,
    SuperGrokTokenBundle,
    XAI_OAUTH_CLIENT_ID,
    XAI_OAUTH_DEVICE_URL,
    XAI_OAUTH_TOKEN_URL,
)


class FakeCredentialStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set_secret(self, profile_name: str, secret: str) -> None:
        self.values[profile_name] = secret

    def get_secret(self, profile_name: str) -> str:
        try:
            return self.values[profile_name]
        except KeyError as exc:
            raise CredentialNotFoundError(profile_name) from exc

    def delete_secret(self, profile_name: str) -> None:
        self.values.pop(profile_name, None)


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str]]] = []
        self.device_status = 200
        self.device_payload = {
            "device_code": "device-1",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://accounts.x.ai/device",
            "expires_in": 600,
            "interval": 0,
        }
        self.token_queue: list[tuple[int, dict[str, Any]]] = []
        self.refresh_status = 200
        self.refresh_payload: dict[str, Any] = {
            "access_token": "access-refreshed",
            "refresh_token": "refresh-2",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

    def request(
        self,
        method: str,
        url: str,
        *,
        headers=None,
        form=None,
        timeout: float = 15.0,
    ) -> tuple[int, dict[str, Any]]:
        del headers, timeout
        self.calls.append((method, url, dict(form or {})))
        if url == XAI_OAUTH_DEVICE_URL:
            return self.device_status, dict(self.device_payload)
        if url == XAI_OAUTH_TOKEN_URL:
            grant = (form or {}).get("grant_type", "")
            if grant == "refresh_token":
                return self.refresh_status, dict(self.refresh_payload)
            if self.token_queue:
                return self.token_queue.pop(0)
            return 400, {"error": "authorization_pending"}
        raise AssertionError(f"unexpected url {url}")


class SuperGrokOAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "profiles.json"
        self.repository = ProfileRepository(self.path)
        self.credentials = FakeCredentialStore()
        self.transport = FakeTransport()
        self.client = SuperGrokOAuthClient(self.transport)
        self.output = StringIO()
        self.now = 1_700_000_000.0
        self.sleeps: list[float] = []
        self.service = SuperGrokAuthService(
            self.repository,
            self.credentials,
            self.client,
            clock=lambda: self.now,
            sleeper=self.sleeps.append,
            output=self.output,
        )

    def _queue_success_token(self, pending: int = 1) -> None:
        for _ in range(pending):
            self.transport.token_queue.append((400, {"error": "authorization_pending"}))
        self.transport.token_queue.append(
            (
                200,
                {
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                    "scope": "openid",
                },
            )
        )

    def test_device_login_stores_tokens_only_in_credential_store(self) -> None:
        self._queue_success_token(pending=1)

        status = self.service.login()

        self.assertTrue(status.authenticated)
        profile = self.repository.get(SUPERGROK_PROFILE_NAME)
        self.assertEqual(profile.auth_kind, AuthKind.SUBSCRIPTION_OAUTH)
        self.assertEqual(profile.base_url, "https://api.x.ai/v1")
        self.assertEqual(profile.model, "grok-4.5")
        key = self.repository.credential_key(SUPERGROK_PROFILE_NAME)
        bundle = SuperGrokTokenBundle.from_json(self.credentials.values[key])
        self.assertEqual(bundle.access_token, "access-1")
        self.assertEqual(bundle.refresh_token, "refresh-1")
        metadata = self.path.read_text()
        self.assertNotIn("access-1", metadata)
        self.assertNotIn("refresh-1", metadata)
        self.assertNotIn("access-1", self.output.getvalue())
        self.assertNotIn("refresh-1", self.output.getvalue())
        self.assertIn("https://accounts.x.ai/device", self.output.getvalue())
        self.assertIn("ABCD-EFGH", self.output.getvalue())
        self.assertEqual(self.transport.calls[0][2]["client_id"], XAI_OAUTH_CLIENT_ID)

    def test_status_and_logout(self) -> None:
        self._queue_success_token(pending=0)
        self.service.login()

        status = self.service.status()
        self.assertTrue(status.authenticated)
        self.assertIn("authenticated", status.message())

        logged_out = self.service.logout()
        self.assertFalse(logged_out.authenticated)
        self.assertFalse(self.service.status().authenticated)
        with self.assertRaises(CredentialNotFoundError):
            self.credentials.get_secret(
                self.repository.credential_key(SUPERGROK_PROFILE_NAME)
            )

    def test_refresh_invalid_grant_quarantines_and_requires_reauth(self) -> None:
        self._queue_success_token(pending=0)
        self.service.login()
        self.now += 4000
        self.transport.refresh_status = 400
        self.transport.refresh_payload = {"error": "invalid_grant"}

        with self.assertRaises(SuperGrokReauthRequired):
            self.service.get_valid_access_token()

        status = self.service.status()
        self.assertTrue(status.authenticated)
        self.assertTrue(status.quarantined)
        with self.assertRaises(SuperGrokReauthRequired):
            self.service.get_valid_access_token()

    def test_login_timeout(self) -> None:
        self.transport.token_queue = [
            (400, {"error": "authorization_pending"}) for _ in range(5)
        ]
        with self.assertRaisesRegex(SuperGrokOAuthError, "timed out"):
            self.service.login(max_wait_seconds=0)

    def test_auth_cli_login_status_logout_secret_free(self) -> None:
        self._queue_success_token(pending=0)
        instructions = StringIO()
        stdout = StringIO()

        with redirect_stdout(stdout):
            code = run_auth_cli(
                ["supergrok", "login"],
                self.repository,
                self.credentials,
                client=self.client,
                output=instructions,
            )
            self.assertEqual(code, 0)
            code = run_auth_cli(
                ["supergrok", "status"],
                self.repository,
                self.credentials,
                client=self.client,
                output=instructions,
            )
            self.assertEqual(code, 0)
            code = run_auth_cli(
                ["supergrok", "logout"],
                self.repository,
                self.credentials,
                client=self.client,
                output=instructions,
            )
            self.assertEqual(code, 0)

        text = stdout.getvalue() + instructions.getvalue()
        self.assertIn("authenticated", text)
        self.assertIn("logged out", text)
        self.assertNotIn("access-1", text)
        self.assertNotIn("refresh-1", text)

    def test_main_dispatches_auth_subcommand(self) -> None:
        self._queue_success_token(pending=0)
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli.main(
                ["auth", "supergrok", "status"],
                profile_repository=self.repository,
                credential_store=self.credentials,
            )
        self.assertEqual(code, 1)
        self.assertIn("logged out", stdout.getvalue())

    def test_never_reads_foreign_auth_json_paths(self) -> None:
        source = Path("src/orbitrelay/supergrok_oauth.py").read_text()
        self.assertNotIn("~/.grok", source)
        self.assertNotIn("auth.json", source)
        self.assertNotIn("CODEX_HOME", source)


if __name__ == "__main__":
    unittest.main()
