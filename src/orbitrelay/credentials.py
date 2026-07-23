from __future__ import annotations

from typing import Any, Protocol

from .profiles import ProfileRepository, ProviderProfile


KEYRING_SERVICE = "orbitrelay-agent"


class CredentialStoreError(RuntimeError):
    pass


class CredentialNotFoundError(CredentialStoreError):
    def __init__(self, profile_name: str):
        super().__init__(f'Credential for profile "{profile_name}" was not found')


class CredentialStore(Protocol):
    def set_secret(self, profile_name: str, secret: str) -> None: ...

    def get_secret(self, profile_name: str) -> str: ...

    def delete_secret(self, profile_name: str) -> None: ...


class KeyringCredentialStore:
    """Small fail-closed adapter around the active native keyring backend."""

    def __init__(self, *, keyring_module: Any | None = None):
        if keyring_module is None:
            import keyring as keyring_module

        self._keyring = keyring_module
        self._assert_secure_backend()

    def _assert_secure_backend(self) -> None:
        try:
            backend = self._keyring.get_keyring()
            priority = backend.priority
        except Exception as exc:
            raise CredentialStoreError(
                "Native credential store is unavailable: backend initialization failed"
            ) from exc
        backend_module = type(backend).__module__
        if priority <= 0 or backend_module.startswith("keyring.backends.fail"):
            raise CredentialStoreError(
                "Native credential store is unavailable on this system"
            )
        if backend_module.startswith("keyrings.alt"):
            raise CredentialStoreError(
                "Configured credential backend is not an approved native store"
            )

    def set_secret(self, profile_name: str, secret: str) -> None:
        if not isinstance(secret, str) or not secret:
            raise CredentialStoreError(
                f'Credential for profile "{profile_name}" cannot be empty'
            )
        try:
            self._keyring.set_password(KEYRING_SERVICE, profile_name, secret)
        except self._keyring.errors.KeyringError as exc:
            raise CredentialStoreError(
                f'Could not store credential for profile "{profile_name}"'
            ) from exc

    def get_secret(self, profile_name: str) -> str:
        try:
            secret = self._keyring.get_password(KEYRING_SERVICE, profile_name)
        except self._keyring.errors.KeyringError as exc:
            raise CredentialStoreError(
                f'Could not read credential for profile "{profile_name}"'
            ) from exc
        if secret is None:
            raise CredentialNotFoundError(profile_name)
        return secret

    def delete_secret(self, profile_name: str) -> None:
        try:
            self._keyring.delete_password(KEYRING_SERVICE, profile_name)
        except self._keyring.errors.PasswordDeleteError:
            return
        except self._keyring.errors.KeyringError as exc:
            raise CredentialStoreError(
                f'Could not delete credential for profile "{profile_name}"'
            ) from exc


class ProfileService:
    """Coordinates profile metadata and credentials without mixing their stores."""

    def __init__(
        self,
        repository: ProfileRepository,
        credential_store: CredentialStore,
    ):
        self.repository = repository
        self.credential_store = credential_store

    def create(self, profile: ProviderProfile, *, secret: str | None = None) -> None:
        if profile.requires_secret:
            if not secret:
                raise CredentialStoreError(
                    f'Profile "{profile.name}" requires a credential'
                )
            self.credential_store.set_secret(profile.name, secret)
            try:
                self.repository.save(profile)
            except Exception:
                self.credential_store.delete_secret(profile.name)
                raise
            return
        if secret is not None:
            raise CredentialStoreError(
                f'Auth kind "{profile.auth_kind.value}" does not accept a credential'
            )
        self.repository.save(profile)

    def delete(self, profile_name: str) -> None:
        profile = self.repository.get(profile_name)
        if profile.requires_secret:
            self.credential_store.delete_secret(profile_name)
        self.repository.delete(profile_name)

    def get_secret(self, profile: ProviderProfile) -> str:
        if not profile.requires_secret:
            raise CredentialStoreError(
                f'Auth kind "{profile.auth_kind.value}" does not use a credential'
            )
        return self.credential_store.get_secret(profile.name)
