from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from openai import APIConnectionError, APIStatusError, APITimeoutError

from orbitrelay.connection_service import ConnectionService
from orbitrelay.credentials import CredentialNotFoundError, CredentialStoreError
from orbitrelay.profile_store import ProfileRepository
from orbitrelay.provider_verification import VerificationOutcome
from orbitrelay.providers import ProviderId


class FakeCredentialStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.unavailable = False

    def set_secret(self, key: str, secret: str) -> None:
        self.values[key] = secret

    def get_secret(self, key: str) -> str:
        if self.unavailable:
            raise CredentialStoreError("backend down")
        try:
            return self.values[key]
        except KeyError as exc:
            raise CredentialNotFoundError(key) from exc

    def delete_secret(self, key: str) -> None:
        self.values.pop(key, None)


class ProviderVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "profiles.json"
        self.repository = ProfileRepository(self.path)
        self.store = FakeCredentialStore()
        self.probe = Mock()
        self.clock = Mock(return_value=1_700_000_000.0)
        self.service = ConnectionService(
            self.repository,
            self.store,
            probe=self.probe,
            clock=self.clock,
        )
        self.service.connect_api_key(ProviderId.OPENAI, "sk-SENTINEL-KEY")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_verify_success_persists_only_historical_metadata(self) -> None:
        result = self.service.verify_provider(ProviderId.OPENAI)
        self.assertEqual(result.outcome, VerificationOutcome.OK)
        self.assertIsNotNone(result.evidence)
        assert result.evidence is not None
        self.assertTrue(result.evidence.historical)
        self.assertEqual(result.evidence.checked_at, 1_700_000_000.0)
        self.assertEqual(result.evidence.route, "openai_compatible")
        self.probe.assert_called_once()
        kwargs = self.probe.call_args.kwargs
        self.assertEqual(kwargs["api_key"], "sk-SENTINEL-KEY")
        text = "\n".join(result.lines())
        self.assertNotIn("sk-SENTINEL-KEY", text)
        self.assertNotIn("SECRET_BODY", text)
        persisted = json.loads(self.path.read_text())
        blob = json.dumps(persisted)
        self.assertNotIn("sk-SENTINEL-KEY", blob)
        evidence = persisted["verifications"]["openai"]
        self.assertEqual(
            set(evidence),
            {"checked_at", "outcome", "route", "model", "historical"},
        )
        self.assertEqual(evidence["outcome"], "ok")
        self.assertTrue(evidence["historical"])

    def test_verify_failure_and_timeout_are_sanitized(self) -> None:
        self.probe.side_effect = APIStatusError(
            message="SECRET_ERROR body",
            response=Mock(status_code=401, headers={}),
            body={"error": "SECRET_BODY"},
        )
        failed = self.service.verify_provider(ProviderId.OPENAI)
        self.assertEqual(failed.outcome, VerificationOutcome.FAILED)
        failed_text = "\n".join(failed.lines())
        self.assertIn("HTTP 401", failed_text)
        self.assertNotIn("SECRET", failed_text)

        self.probe.side_effect = APITimeoutError(request=Mock())
        timed_out = self.service.verify_provider(ProviderId.OPENAI)
        self.assertEqual(timed_out.outcome, VerificationOutcome.TIMEOUT)
        timeout_text = "\n".join(timed_out.lines())
        self.assertIn("timed out", timeout_text)
        self.assertNotIn("SECRET", timeout_text)

        self.probe.side_effect = APIConnectionError(request=Mock())
        connected = self.service.verify_provider(ProviderId.OPENAI)
        self.assertEqual(connected.outcome, VerificationOutcome.FAILED)
        self.assertIn("could not connect", "\n".join(connected.lines()))

    def test_unavailable_credentials_do_not_probe(self) -> None:
        key = self.repository.credential_key("openai")
        self.store.delete_secret(key)
        result = self.service.verify_provider(ProviderId.OPENAI)
        self.assertEqual(result.outcome, VerificationOutcome.UNAVAILABLE)
        self.probe.assert_not_called()
        self.assertIsNone(self.repository.get_verification("openai"))

        self.store.unavailable = True
        self.store.set_secret(key, "sk-SENTINEL-KEY")
        unavailable = self.service.verify_provider(ProviderId.OPENAI)
        self.assertEqual(unavailable.outcome, VerificationOutcome.UNAVAILABLE)
        self.probe.assert_not_called()

    def test_status_remains_offline_and_shows_historical_only(self) -> None:
        self.service.verify_provider(ProviderId.OPENAI)
        self.probe.reset_mock()
        status = self.service.inspect_provider(ProviderId.OPENAI)
        self.probe.assert_not_called()
        text = "\n".join(status.lines())
        self.assertIn("last_verification: historical", text)
        self.assertIn("last_verification_outcome: ok", text)
        self.assertNotIn("sk-SENTINEL-KEY", text)

    def test_codex_verify_is_rejected(self) -> None:
        from orbitrelay.connection_service import ConnectionError

        with self.assertRaisesRegex(ConnectionError, "OpenAI-compatible"):
            self.service.verify_provider(ProviderId.CODEX)
        self.probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
