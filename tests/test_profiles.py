import unittest
import json
import tempfile
from pathlib import Path

from orbitrelay.profile_store import (
    ProfileExistsError,
    ProfileNotFoundError,
    ProfileRepository,
    ProfileStorageError,
)
from orbitrelay.profiles import (
    AuthKind,
    ProviderCapability,
    ProviderProfile,
    ProfileValidationError,
)


CAPABILITIES = frozenset(
    {
        ProviderCapability.TOOL_CALLING,
        ProviderCapability.ASSISTANT_MESSAGE_PASSTHROUGH,
    }
)


class ProviderProfileTests(unittest.TestCase):
    def test_accepts_each_declared_auth_kind_without_a_secret_value(self):
        for auth_kind in AuthKind:
            with self.subTest(auth_kind=auth_kind):
                profile = ProviderProfile.create(
                    name=f"profile-{auth_kind.value.replace('_', '-')}",
                    base_url=(
                        "http://127.0.0.1:11434/v1"
                        if auth_kind is AuthKind.LOCAL_NONE
                        else "https://example.test/v1"
                    ),
                    model="test-model",
                    auth_kind=auth_kind,
                    capabilities=CAPABILITIES,
                )

                self.assertEqual(profile.auth_kind, auth_kind)
                self.assertNotIn("secret", profile.to_dict())
                self.assertNotIn("api_key", profile.to_dict())

    def test_rejects_unsafe_profile_names(self):
        for name in ("", "../escape", "has spaces", "a/b", ".hidden"):
            with self.subTest(name=name):
                with self.assertRaises(ProfileValidationError):
                    ProviderProfile.create(
                        name=name,
                        base_url="https://example.test/v1",
                        model="test-model",
                        auth_kind=AuthKind.API_KEY,
                        capabilities=CAPABILITIES,
                    )

    def test_rejects_unauthenticated_non_loopback_endpoint(self):
        with self.assertRaisesRegex(ProfileValidationError, "loopback"):
            ProviderProfile.create(
                name="unsafe-local",
                base_url="http://192.168.1.20:11434/v1",
                model="test-model",
                auth_kind=AuthKind.LOCAL_NONE,
                capabilities=CAPABILITIES,
            )

    def test_rejects_plaintext_remote_endpoint_for_secret_backed_auth(self):
        for auth_kind in (AuthKind.API_KEY, AuthKind.LOCAL_SERVICE_BEARER):
            with self.subTest(auth_kind=auth_kind):
                with self.assertRaisesRegex(ProfileValidationError, "HTTPS or loopback"):
                    ProviderProfile.create(
                        name=f"unsafe-{auth_kind.value.replace('_', '-')}",
                        base_url="http://example.test/v1",
                        model="test-model",
                        auth_kind=auth_kind,
                        capabilities=CAPABILITIES,
                    )

    def test_rejects_plaintext_remote_endpoint_for_external_cli_auth(self):
        with self.assertRaisesRegex(ProfileValidationError, "HTTPS or loopback"):
            ProviderProfile.create(
                name="codex",
                base_url="http://example.test/v1",
                model="test-model",
                auth_kind=AuthKind.EXTERNAL_FIRST_PARTY_CLI,
                capabilities=CAPABILITIES,
            )

    def test_rejects_query_and_fragment_in_base_url(self):
        for base_url in (
            "https://example.test/v1?api_key=must-not-persist",
            "https://example.test/v1#token=must-not-persist",
        ):
            with self.subTest(base_url=base_url):
                with self.assertRaisesRegex(ProfileValidationError, "query or fragment"):
                    ProviderProfile.create(
                        name="unsafe-url",
                        base_url=base_url,
                        model="test-model",
                        auth_kind=AuthKind.API_KEY,
                        capabilities=CAPABILITIES,
                    )

    def test_rejects_malformed_port_as_profile_validation_error(self):
        with self.assertRaisesRegex(ProfileValidationError, "port"):
            ProviderProfile.create(
                name="bad-port",
                base_url="https://example.test:not-a-port/v1",
                model="test-model",
                auth_kind=AuthKind.API_KEY,
                capabilities=CAPABILITIES,
            )

    def test_allows_plaintext_loopback_for_secret_backed_auth(self):
        profile = ProviderProfile.create(
            name="local-bearer",
            base_url="http://127.0.0.1:8000/v1",
            model="test-model",
            auth_kind=AuthKind.LOCAL_SERVICE_BEARER,
            capabilities=CAPABILITIES,
        )

        self.assertEqual(profile.base_url, "http://127.0.0.1:8000/v1")

    def test_rejects_missing_required_capability(self):
        with self.assertRaisesRegex(ProfileValidationError, "tool_calling"):
            ProviderProfile.create(
                name="missing-tools",
                base_url="https://example.test/v1",
                model="test-model",
                auth_kind=AuthKind.API_KEY,
                capabilities={ProviderCapability.ASSISTANT_MESSAGE_PASSTHROUGH},
            )

    def test_rejects_invalid_contract_for_each_auth_kind(self):
        for auth_kind in AuthKind:
            with self.subTest(auth_kind=auth_kind):
                with self.assertRaisesRegex(ProfileValidationError, "model"):
                    ProviderProfile.create(
                        name=f"invalid-{auth_kind.value.replace('_', '-')}",
                        base_url=(
                            "http://127.0.0.1:11434/v1"
                            if auth_kind is AuthKind.LOCAL_NONE
                            else "https://example.test/v1"
                        ),
                        model=" ",
                        auth_kind=auth_kind,
                        capabilities=CAPABILITIES,
                    )

    def test_round_trips_secret_free_metadata(self):
        profile = ProviderProfile.create(
            name="deepseek-work",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            auth_kind=AuthKind.API_KEY,
            capabilities=CAPABILITIES,
        )

        self.assertEqual(ProviderProfile.from_dict(profile.to_dict()), profile)

    def test_rejects_unknown_serialized_fields(self):
        with self.assertRaisesRegex(ProfileValidationError, "unknown fields"):
            ProviderProfile.from_dict(
                {
                    "name": "unsafe",
                    "base_url": "https://example.test/v1",
                    "model": "test-model",
                    "auth_kind": "api_key",
                    "capabilities": ["tool_calling"],
                    "api_key": "must-not-load",
                }
            )


def api_key_profile(name="work"):
    return ProviderProfile.create(
        name=name,
        base_url="https://example.test/v1",
        model="test-model",
        auth_kind=AuthKind.API_KEY,
        capabilities=CAPABILITIES,
    )


class ProfileRepositoryTests(unittest.TestCase):
    def test_saves_lists_selects_and_deletes_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orbitrelay" / "profiles.json"
            repository = ProfileRepository(path)
            work = api_key_profile("work")
            personal = api_key_profile("personal")

            repository.save(work)
            repository.save(personal)
            repository.select("work")

            self.assertEqual(repository.get("work"), work)
            self.assertEqual(
                [profile.name for profile in repository.list_profiles()],
                ["personal", "work"],
            )
            self.assertEqual(repository.selected_name(), "work")

            repository.delete("work")

            self.assertIsNone(repository.selected_name())
            with self.assertRaises(ProfileNotFoundError):
                repository.get("work")

    def test_metadata_never_contains_a_secret_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            ProfileRepository(path).save(api_key_profile())

            persisted = json.loads(path.read_text())

            def keys(value):
                if isinstance(value, dict):
                    return set(value).union(*(keys(item) for item in value.values()))
                if isinstance(value, list):
                    return set().union(*(keys(item) for item in value), set())
                return set()

            self.assertNotIn("api_key", keys(persisted))
            self.assertNotIn("secret", keys(persisted))

    def test_rejects_accidental_profile_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProfileRepository(Path(directory) / "profiles.json")
            repository.save(api_key_profile())

            with self.assertRaises(ProfileExistsError):
                repository.save(api_key_profile())

            replacement = ProviderProfile.create(
                name="work",
                base_url="https://replacement.test/v1",
                model="new-model",
                auth_kind=AuthKind.API_KEY,
                capabilities=CAPABILITIES,
            )
            repository.save(replacement, replace=True)
            self.assertEqual(repository.get("work"), replacement)

    def test_rejects_selecting_an_unknown_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProfileRepository(Path(directory) / "profiles.json")

            with self.assertRaises(ProfileNotFoundError):
                repository.select("missing")

    def test_rejects_corrupt_or_unknown_storage_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            path.write_text("not json")
            with self.assertRaisesRegex(ProfileStorageError, "valid JSON"):
                ProfileRepository(path).list_profiles()

            path.write_text(json.dumps({"version": 99, "selected": None, "profiles": {}}))
            with self.assertRaisesRegex(ProfileStorageError, "version"):
                ProfileRepository(path).list_profiles()

    def test_rejects_symlinked_metadata_and_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_directory = root / "real"
            real_directory.mkdir()
            metadata = real_directory / "profiles.json"
            ProfileRepository(metadata).save(api_key_profile())

            linked_file = root / "linked-profiles.json"
            linked_file.symlink_to(metadata)
            with self.assertRaisesRegex(ProfileStorageError, "symbolic link"):
                ProfileRepository(linked_file).list_profiles()

            linked_directory = root / "linked-directory"
            linked_directory.symlink_to(real_directory, target_is_directory=True)
            with self.assertRaisesRegex(ProfileStorageError, "symbolic link"):
                ProfileRepository(linked_directory / "profiles.json").list_profiles()


if __name__ == "__main__":
    unittest.main()
