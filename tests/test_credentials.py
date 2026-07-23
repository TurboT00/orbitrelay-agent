import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from orbitrelay.credentials import (
    CredentialNotFoundError,
    CredentialRollbackError,
    CredentialStoreError,
    KeyringCredentialStore,
    ProfileService,
    credential_store_or_default,
)
from orbitrelay.profile_store import (
    ProfileExistsError,
    ProfileRepository,
    ProfileStorageError,
)
from orbitrelay.profiles import (
    AuthKind,
    ProviderCapability,
    ProviderProfile,
)


CAPABILITIES = {
    ProviderCapability.TOOL_CALLING,
    ProviderCapability.ASSISTANT_MESSAGE_PASSTHROUGH,
}


def profile(name="work", auth_kind=AuthKind.API_KEY):
    return ProviderProfile.create(
        name=name,
        base_url=(
            "http://127.0.0.1:11434/v1"
            if auth_kind is AuthKind.LOCAL_NONE
            else "https://example.test/v1"
        ),
        model="test-model",
        auth_kind=auth_kind,
        capabilities=CAPABILITIES,
    )


class FakeCredentialStore:
    def __init__(self):
        self.values = {}
        self.deleted = []

    def set_secret(self, profile_name, secret):
        self.values[profile_name] = secret

    def get_secret(self, profile_name):
        try:
            return self.values[profile_name]
        except KeyError as exc:
            raise CredentialNotFoundError(profile_name) from exc

    def delete_secret(self, profile_name):
        self.deleted.append(profile_name)
        self.values.pop(profile_name, None)


class FakeKeyringError(Exception):
    pass


class FakePasswordDeleteError(FakeKeyringError):
    pass


class FakeKeyringModule:
    class errors:
        KeyringError = FakeKeyringError
        PasswordDeleteError = FakePasswordDeleteError

    def __init__(self):
        self.values = {}
        self.backend: object = type(
            "Backend",
            (),
            {"priority": 1, "__module__": "keyring.backends.macOS"},
        )()
        self.failure = None
        self.delete_failure = None

    def get_keyring(self):
        return self.backend

    def set_password(self, service, username, password):
        if self.failure:
            raise self.failure
        self.values[(service, username)] = password

    def get_password(self, service, username):
        if self.failure:
            raise self.failure
        return self.values.get((service, username))

    def delete_password(self, service, username):
        if self.failure:
            raise self.failure
        if self.delete_failure:
            raise self.delete_failure
        try:
            del self.values[(service, username)]
        except KeyError as exc:
            raise FakePasswordDeleteError() from exc


class KeyringCredentialStoreTests(unittest.TestCase):
    def test_preserves_an_injected_credential_store(self):
        store = FakeCredentialStore()

        self.assertIs(credential_store_or_default(store), store)

    def test_round_trips_and_deletes_a_profile_secret(self):
        keyring = FakeKeyringModule()
        store = KeyringCredentialStore(keyring_module=keyring)

        store.set_secret("work", "top-secret")

        self.assertEqual(store.get_secret("work"), "top-secret")
        store.delete_secret("work")
        with self.assertRaises(CredentialNotFoundError):
            store.get_secret("work")

    def test_delete_is_idempotent_for_an_absent_secret(self):
        store = KeyringCredentialStore(keyring_module=FakeKeyringModule())

        store.delete_secret("missing")

    def test_delete_failure_is_not_treated_as_absent_when_secret_remains(self):
        keyring = FakeKeyringModule()
        keyring.values[("orbitrelay-agent", "work")] = "top-secret"
        keyring.delete_failure = FakePasswordDeleteError("delete failed")
        store = KeyringCredentialStore(keyring_module=keyring)

        with self.assertRaisesRegex(CredentialStoreError, "delete"):
            store.delete_secret("work")

    def test_rejects_chained_backend(self):
        keyring = FakeKeyringModule()
        keyring.backend = type(
            "ChainerBackend",
            (),
            {"priority": 10, "__module__": "keyring.backends.chainer"},
        )()

        with self.assertRaisesRegex(CredentialStoreError, "approved native"):
            KeyringCredentialStore(keyring_module=keyring)

    def test_wraps_backend_failures_without_leaking_the_secret(self):
        keyring = FakeKeyringModule()
        keyring.failure = FakeKeyringError("backend failed")
        store = KeyringCredentialStore(keyring_module=keyring)

        with self.assertRaises(CredentialStoreError) as raised:
            store.set_secret("work", "top-secret")

        self.assertNotIn("top-secret", str(raised.exception))
        self.assertIn("work", str(raised.exception))

    def test_rejects_an_unavailable_backend(self):
        keyring = FakeKeyringModule()
        keyring.backend = type(
            "Keyring", (), {"priority": 0, "__module__": "keyring.backends.fail"}
        )()

        with self.assertRaisesRegex(CredentialStoreError, "unavailable"):
            KeyringCredentialStore(keyring_module=keyring)


class FailingRepository(ProfileRepository):
    def __init__(self, path):
        super().__init__(path)
        self.fail_writes = False

    def _write(self, state):
        if self.fail_writes:
            raise ProfileStorageError("metadata write failed")
        super()._write(state)


class FailingDeleteCredentialStore(FakeCredentialStore):
    def delete_secret(self, profile_name):
        raise CredentialStoreError("cleanup failed")


class ProfileServiceTests(unittest.TestCase):
    def test_creates_secret_backed_profile_without_persisting_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            repository = ProfileRepository(path)
            credentials = FakeCredentialStore()
            service = ProfileService(repository, credentials)

            service.create(profile(), secret="top-secret")

            self.assertEqual(credentials.values, {"work": "top-secret"})
            self.assertEqual(repository.get("work"), profile())
            self.assertNotIn("top-secret", path.read_text())

    def test_cleans_up_secret_when_metadata_creation_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = FailingRepository(Path(directory) / "profiles.json")
            repository.fail_writes = True
            credentials = FakeCredentialStore()
            service = ProfileService(repository, credentials)

            with self.assertRaises(ProfileStorageError):
                service.create(profile(), secret="top-secret")

            self.assertEqual(credentials.values, {})

    def test_reports_metadata_and_cleanup_failure_without_masking_either(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = FailingRepository(Path(directory) / "profiles.json")
            repository.fail_writes = True
            service = ProfileService(repository, FailingDeleteCredentialStore())

            with self.assertRaises(CredentialRollbackError) as raised:
                service.create(profile(), secret="top-secret")

            self.assertIsInstance(raised.exception.metadata_error, ProfileStorageError)
            self.assertIsInstance(raised.exception.cleanup_error, CredentialStoreError)

    def test_duplicate_creation_preserves_the_existing_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProfileRepository(Path(directory) / "profiles.json")
            credentials = FakeCredentialStore()
            service = ProfileService(repository, credentials)
            service.create(profile(), secret="original-secret")

            with self.assertRaises(ProfileExistsError):
                service.create(profile(), secret="replacement-secret")

            self.assertEqual(credentials.values, {"work": "original-secret"})

    def test_deletion_is_retry_safe_after_metadata_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = FailingRepository(Path(directory) / "profiles.json")
            credentials = FakeCredentialStore()
            service = ProfileService(repository, credentials)
            service.create(profile(), secret="top-secret")
            repository.fail_writes = True

            with self.assertRaises(ProfileStorageError):
                service.delete("work")

            self.assertEqual(credentials.values, {})
            repository.fail_writes = False
            service.delete("work")
            self.assertEqual(repository.list_profiles(), ())

    def test_rejects_secret_for_a_non_secret_auth_kind(self):
        with tempfile.TemporaryDirectory() as directory:
            service = ProfileService(
                ProfileRepository(Path(directory) / "profiles.json"),
                FakeCredentialStore(),
            )

            with self.assertRaisesRegex(CredentialStoreError, "does not accept"):
                service.create(
                    profile("local", auth_kind=AuthKind.LOCAL_NONE),
                    secret="not-needed",
                )

    def test_alternate_profile_homes_use_distinct_credential_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            credentials = FakeCredentialStore()
            first = ProfileRepository(Path(directory) / "first" / "profiles.json")
            second = ProfileRepository(Path(directory) / "second" / "profiles.json")
            ProfileService(first, credentials).create(profile(), secret="first-secret")
            ProfileService(second, credentials).create(profile(), secret="second-secret")

            self.assertEqual(len(credentials.values), 2)
            self.assertEqual(
                ProfileService(first, credentials).get_secret(first.get("work")),
                "first-secret",
            )
            self.assertEqual(
                ProfileService(second, credentials).get_secret(second.get("work")),
                "second-secret",
            )

    def test_concurrent_same_name_creation_preserves_winning_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            credentials = FakeCredentialStore()
            start = threading.Barrier(2)

            def create(secret):
                start.wait()
                service = ProfileService(ProfileRepository(path), credentials)
                try:
                    service.create(profile(), secret=secret)
                    return "created"
                except ProfileExistsError:
                    return "exists"

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(create, ("first-secret", "second-secret")))

            repository = ProfileRepository(path)
            stored = ProfileService(repository, credentials).get_secret(
                repository.get("work")
            )
            self.assertCountEqual(results, ["created", "exists"])
            self.assertIn(stored, {"first-secret", "second-secret"})


if __name__ == "__main__":
    unittest.main()
