from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orbitrelay.connection_service import (
    CodexCliConnection,
    ConnectionError,
    ConnectionService,
    LifecyclePart,
    OpenAICompatibleConnection,
)
from orbitrelay.credentials import CredentialNotFoundError
from orbitrelay.profile_store import ProfileNotFoundError, ProfileRepository
from orbitrelay.profiles import AuthKind, ProviderCapability, ProviderProfile
from orbitrelay.providers import ProviderId


class FakeCredentialStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set_secret(self, key: str, secret: str) -> None:
        self.values[key] = secret

    def get_secret(self, key: str) -> str:
        try:
            return self.values[key]
        except KeyError as exc:
            raise CredentialNotFoundError(key) from exc

    def delete_secret(self, key: str) -> None:
        self.values.pop(key, None)


class ConnectionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.repository = ProfileRepository(Path(self.directory.name) / "profiles.json")
        self.store = FakeCredentialStore()
        self.service = ConnectionService(self.repository, self.store)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_connects_and_resolves_an_api_key_provider(self) -> None:
        self.service.connect_api_key(ProviderId.DEEPSEEK, "deepseek-secret")

        resolved = self.service.resolve()

        self.assertIsInstance(resolved, OpenAICompatibleConnection)
        assert isinstance(resolved, OpenAICompatibleConnection)
        self.assertEqual(resolved.provider.identifier, ProviderId.DEEPSEEK)
        self.assertEqual(resolved.config.api_key, "deepseek-secret")
        self.assertEqual(self.repository.selected_name(), "deepseek")

    def test_an_override_selects_the_requested_provider(self) -> None:
        self.service.connect_api_key(ProviderId.OPENAI, "openai-secret")
        self.service.connect_api_key(ProviderId.GROK, "grok-secret")

        resolved = self.service.resolve(ProviderId.OPENAI)

        assert isinstance(resolved, OpenAICompatibleConnection)
        self.assertEqual(resolved.config.api_key, "openai-secret")
        self.assertEqual(resolved.provider.identifier, ProviderId.OPENAI)

    def test_replaces_a_key_without_changing_its_credential_key(self) -> None:
        self.service.connect_api_key(ProviderId.GEMINI, "old-secret")
        key = self.repository.credential_key("gemini")
        self.service.connect_api_key(ProviderId.GEMINI, "new-secret")

        self.assertEqual(self.store.get_secret(key), "new-secret")
        self.assertEqual(self.service.resolve().config.api_key, "new-secret")

    def test_rejects_unsupported_subscription_before_storing_a_secret(self) -> None:
        with self.assertRaisesRegex(ConnectionError, "No documented"):
            self.service.connect_subscription(ProviderId.GROK)

        self.assertEqual(self.store.values, {})

    def test_returns_codex_external_cli_connection_without_a_keyring_secret(self) -> None:
        resolved = self.service.connect_subscription(ProviderId.CODEX)

        self.assertIsInstance(resolved, CodexCliConnection)
        self.assertEqual(self.store.values, {})
        self.assertEqual(self.repository.selected_name(), "codex")
        self.assertEqual(
            self.service.resolve(),
            CodexCliConnection(resolved.provider),
        )

    def test_metadata_and_codex_operations_do_not_initialize_keyring(self) -> None:
        with patch(
            "orbitrelay.connection_service.credential_store_or_default",
            side_effect=AssertionError("keyring must stay lazy"),
        ):
            service = ConnectionService(self.repository)
            self.assertIsNone(service.selected_provider())
            service.connect_subscription(ProviderId.CODEX)
            self.assertEqual(service.resolve().provider.identifier, ProviderId.CODEX)
            service.disconnect(ProviderId.CODEX)

    def test_legacy_custom_endpoint_is_not_misidentified_as_a_provider(self) -> None:
        custom = ProviderProfile.create(
            name="custom",
            base_url="https://example.test/v1",
            model="custom-model",
            auth_kind=AuthKind.API_KEY,
            capabilities={
                ProviderCapability.TOOL_CALLING,
                ProviderCapability.ASSISTANT_MESSAGE_PASSTHROUGH,
            },
        )
        self.repository.save(custom)
        self.store.set_secret(self.repository.credential_key("custom"), "secret")
        self.repository.select("custom")

        with self.assertRaisesRegex(ConnectionError, "custom legacy endpoint"):
            self.service.resolve()

    def test_migrates_v1_metadata_without_changing_the_credential_key(self) -> None:
        profile = ProviderProfile.create(
            name="legacy-deepseek",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            auth_kind=AuthKind.API_KEY,
            capabilities={
                ProviderCapability.TOOL_CALLING,
                ProviderCapability.ASSISTANT_MESSAGE_PASSTHROUGH,
            },
        )
        path = self.repository.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "selected": "legacy-deepseek",
                    "profiles": {"legacy-deepseek": profile.to_dict()},
                }
            )
        )
        key = self.repository.credential_key("legacy-deepseek")
        self.store.set_secret(key, "legacy-secret")

        migrated = ConnectionService(self.repository, self.store)
        resolved = migrated.resolve()

        self.assertEqual(json.loads(path.read_text())["version"], 2)
        self.assertEqual(self.repository.credential_key("legacy-deepseek"), key)
        assert isinstance(resolved, OpenAICompatibleConnection)
        self.assertEqual(resolved.config.api_key, "legacy-secret")

    def test_legacy_supergrok_token_is_not_used_as_an_api_key(self) -> None:
        legacy = ProviderProfile.create(
            name="supergrok",
            base_url="https://api.x.ai/v1",
            model="grok-4.5",
            auth_kind=AuthKind.SUBSCRIPTION_OAUTH,
            capabilities={
                ProviderCapability.TOOL_CALLING,
                ProviderCapability.ASSISTANT_MESSAGE_PASSTHROUGH,
            },
        )
        self.repository.save(legacy)
        key = self.repository.credential_key("supergrok")
        self.store.set_secret(key, "legacy-refresh-token")
        self.repository.select("supergrok")

        with self.assertRaisesRegex(ConnectionError, "requires reauthentication"):
            self.service.resolve()
        self.assertEqual(self.store.get_secret(key), "legacy-refresh-token")





    def test_codex_disconnect_clears_selection_without_fallback(self) -> None:
        self.service.connect_api_key(ProviderId.OPENAI, "openai-secret")
        self.service.connect_subscription(ProviderId.CODEX)
        self.assertEqual(self.repository.selected_name(), "codex")
        result = self.service.disconnect(ProviderId.CODEX)
        self.assertEqual(result.metadata, LifecyclePart.COMPLETED)
        self.assertEqual(result.selection, LifecyclePart.COMPLETED)
        self.assertEqual(result.official_auth, LifecyclePart.UNCHANGED)
        self.assertIsNone(self.repository.selected_name())
        with self.assertRaises(ProfileNotFoundError):
            self.repository.get("codex")
        # OpenAI remains connected but is not auto-selected.
        self.assertEqual(self.repository.get("openai").name, "openai")

    def test_logout_and_disconnect_codex_is_logout_first_with_partials(self) -> None:
        from unittest.mock import Mock

        bridge = Mock()
        bridge.logout.return_value = 0
        service = ConnectionService(self.repository, self.store, codex_bridge=bridge)
        service.connect_subscription(ProviderId.CODEX)
        complete = service.logout_and_disconnect_codex()
        self.assertTrue(complete.complete)
        self.assertEqual(complete.logout, LifecyclePart.COMPLETED)
        self.assertEqual(complete.metadata, LifecyclePart.COMPLETED)
        bridge.logout.assert_called_once_with()
        with self.assertRaises(ProfileNotFoundError):
            self.repository.get("codex")

        # logout fails: metadata untouched
        service.connect_subscription(ProviderId.CODEX)
        bridge.logout.return_value = 1
        failed = service.logout_and_disconnect_codex()
        self.assertFalse(failed.complete)
        self.assertEqual(failed.logout, LifecyclePart.FAILED)
        self.assertEqual(failed.metadata, LifecyclePart.UNCHANGED)
        self.assertEqual(self.repository.get("codex").name, "codex")
        self.assertIn("retry:", failed.recovery or "")

        # logout ok, metadata already absent
        bridge.logout.return_value = 0
        service.disconnect(ProviderId.CODEX)
        absent = service.logout_and_disconnect_codex()
        self.assertTrue(absent.complete)
        self.assertEqual(absent.metadata, LifecyclePart.ABSENT)

class ProviderReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.repository = ProfileRepository(Path(self.directory.name) / "profiles.json")
        self.store = FakeCredentialStore()
        self.service = ConnectionService(self.repository, self.store)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_api_provider_local_ready_when_configured_selected_and_present(self) -> None:
        self.service.connect_api_key(ProviderId.OPENAI, "openai-secret")
        status = self.service.inspect_provider(ProviderId.OPENAI)
        self.assertTrue(status.configured)
        self.assertTrue(status.selected)
        self.assertEqual(status.credential.value, "present")
        self.assertEqual(status.readiness.value, "local-ready")
        self.assertNotIn("openai-secret", "\n".join(status.lines()))

    def test_credential_absent_is_not_ready(self) -> None:
        self.service.connect_api_key(ProviderId.DEEPSEEK, "temp")
        key = self.repository.credential_key("deepseek")
        self.store.delete_secret(key)
        status = self.service.inspect_provider(ProviderId.DEEPSEEK)
        self.assertTrue(status.configured)
        self.assertEqual(status.credential.value, "absent")
        self.assertEqual(status.readiness.value, "not-ready")

    def test_credential_backend_unavailable_is_unknown(self) -> None:
        self.service.connect_api_key(ProviderId.GEMINI, "temp")

        class UnavailableStore:
            def set_secret(self, key: str, secret: str) -> None:
                raise AssertionError("set should not run")

            def get_secret(self, key: str) -> str:
                from orbitrelay.credentials import CredentialStoreError

                raise CredentialStoreError("Native credential store is unavailable")

            def delete_secret(self, key: str) -> None:
                raise AssertionError("delete should not run")

        service = ConnectionService(self.repository, UnavailableStore())
        status = service.inspect_provider(ProviderId.GEMINI)
        self.assertTrue(status.configured)
        self.assertEqual(status.credential.value, "unavailable")
        self.assertEqual(status.readiness.value, "unknown")
        self.assertNotIn("temp", "\n".join(status.lines()))

    def test_unconfigured_provider_is_not_ready(self) -> None:
        status = self.service.inspect_provider(ProviderId.GROK)
        self.assertFalse(status.configured)
        self.assertEqual(status.readiness.value, "not-ready")


if __name__ == "__main__":
    unittest.main()
