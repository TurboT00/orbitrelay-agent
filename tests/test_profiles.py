# story: e01s01

import unittest
import json
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import cast

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
    def test_rejects_unknown_auth_and_capability_values(self):
        with self.assertRaisesRegex(ProfileValidationError, "auth_kind"):
            ProviderProfile.create(
                name="work",
                base_url="https://example.test/v1",
                model="test-model",
                auth_kind="unknown",
                capabilities=CAPABILITIES,
            )
        with self.assertRaisesRegex(ProfileValidationError, "capability"):
            ProviderProfile.create(
                name="work",
                base_url="https://example.test/v1",
                model="test-model",
                auth_kind=AuthKind.API_KEY,
                capabilities=[*CAPABILITIES, "unknown"],
            )

    def test_rejects_malformed_or_credential_bearing_base_urls(self):
        invalid_urls = {
            "": "empty",
            "https://example.test/v1\nunsafe": "whitespace",
            "/relative/v1": "absolute",
            "https://user:password@example.test/v1": "credentials",
        }
        for base_url, message in invalid_urls.items():
            with self.subTest(base_url=base_url):
                with self.assertRaisesRegex(ProfileValidationError, message):
                    ProviderProfile.create(
                        name="work",
                        base_url=base_url,
                        model="test-model",
                        auth_kind=AuthKind.API_KEY,
                        capabilities=CAPABILITIES,
                    )

    def test_accepts_localhost_as_a_loopback_host(self):
        profile = ProviderProfile.create(
            name="local",
            base_url="http://localhost:11434/v1",
            model="test-model",
            auth_kind=AuthKind.LOCAL_NONE,
            capabilities=CAPABILITIES,
        )

        self.assertEqual(profile.base_url, "http://localhost:11434/v1")

    def test_rejects_non_iterable_capabilities(self):
        with self.assertRaisesRegex(ProfileValidationError, "capabilities must be a list"):
            ProviderProfile.create(
                name="work",
                base_url="https://example.test/v1",
                model="test-model",
                auth_kind=AuthKind.API_KEY,
                capabilities=cast(Iterable[ProviderCapability | str], None),
            )

    def test_rejects_malformed_serialized_profile_shapes(self):
        valid = api_key_profile().to_dict()
        malformed = [
            (None, "metadata must be an object"),
            ({key: value for key, value in valid.items() if key != "model"}, "missing"),
            ({**valid, "capabilities": "tool_calling"}, "capabilities must be a list"),
        ]
        for metadata, message in malformed:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ProfileValidationError, message):
                    ProviderProfile.from_dict(metadata)

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
        for auth_kind in (
            AuthKind.API_KEY,
            AuthKind.LOCAL_SERVICE_BEARER,
            AuthKind.SUBSCRIPTION_OAUTH,
        ):
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
    def test_rejects_malformed_structured_metadata(self):
        valid_profile = api_key_profile().to_dict()
        malformed = [
            ([], "root must be an object"),
            (
                {"version": 1, "selected": None, "profiles": {}, "extra": True},
                "invalid fields",
            ),
            ({"version": 1, "selected": None, "profiles": []}, "must be an object"),
            (
                {
                    "version": 1,
                    "selected": None,
                    "profiles": {"wrong-name": valid_profile},
                },
                "does not match",
            ),
            (
                {
                    "version": 1,
                    "selected": None,
                    "profiles": {"work": {"name": "work"}},
                },
                "Stored profile is invalid",
            ),
            ({"version": 1, "selected": 7, "profiles": {}}, "string or null"),
            (
                {"version": 1, "selected": "missing", "profiles": {}},
                "does not exist in metadata",
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            for metadata, message in malformed:
                with self.subTest(message=message):
                    path.write_text(json.dumps(metadata))
                    with self.assertRaisesRegex(ProfileStorageError, message):
                        ProfileRepository(path).list_profiles()

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

    def test_rejects_group_writable_profile_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_directory = Path(directory) / "unsafe"
            profile_directory.mkdir()
            profile_directory.chmod(0o770)

            with self.assertRaisesRegex(ProfileStorageError, "group/world writable"):
                ProfileRepository(profile_directory / "profiles.json").save(
                    api_key_profile()
                )

    def test_subprocess_writers_preserve_distinct_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            script = """
import sys
from orbitrelay.profile_store import ProfileRepository
from orbitrelay.profiles import AuthKind, ProviderCapability, ProviderProfile
profile = ProviderProfile.create(
    name=sys.argv[2],
    base_url='https://example.test/v1',
    model='test-model',
    auth_kind=AuthKind.API_KEY,
    capabilities={
        ProviderCapability.TOOL_CALLING,
        ProviderCapability.ASSISTANT_MESSAGE_PASSTHROUGH,
    },
)
ProfileRepository(sys.argv[1]).save(profile)
"""
            processes = [
                subprocess.Popen([sys.executable, "-c", script, str(path), name])
                for name in ("one", "two", "three", "four")
            ]
            return_codes = [process.wait(timeout=10) for process in processes]

            self.assertEqual(return_codes, [0, 0, 0, 0])
            self.assertEqual(
                [profile.name for profile in ProfileRepository(path).list_profiles()],
                ["four", "one", "three", "two"],
            )


if __name__ == "__main__":
    unittest.main()
