"""Single resolution boundary for stored provider connections.

This service deliberately uses the existing secure profile repository and
keyring storage while the on-disk metadata migrates from "profiles" to
"connections".  No caller outside this module needs provider-specific
credential logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .config import ApiConfig
from .credentials import (
    CredentialNotFoundError,
    CredentialStore,
    CredentialStoreError,
    ProfileService,
    credential_store_or_default,
)
from .profile_store import ProfileNotFoundError, ProfileRepository
from .profiles import AuthKind, ProviderProfile
from .providers import (
    AuthMethod,
    ExecutionRoute,
    ProviderDefinition,
    ProviderId,
    provider_definition,
    provider_for_legacy_endpoint,
)


class ConnectionError(ValueError):
    """A stored provider connection cannot be created or used."""


@dataclass(frozen=True)
class OpenAICompatibleConnection:
    config: ApiConfig
    provider: ProviderDefinition


@dataclass(frozen=True)
class CodexCliConnection:
    provider: ProviderDefinition


ResolvedConnection = OpenAICompatibleConnection | CodexCliConnection

class CredentialState(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not-applicable"


class LocalReadiness(StrEnum):
    LOCAL_READY = "local-ready"
    NOT_READY = "not-ready"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProviderReadiness:
    """Offline local facts for one provider connection."""

    provider: str
    configured: bool
    selected: bool
    catalog: str
    model: str | None
    auth_kind: str | None
    credential: CredentialState
    readiness: LocalReadiness
    detail: str | None = None

    def lines(self) -> tuple[str, ...]:
        rows = [
            f"provider: {self.provider}",
            f"configured: {'yes' if self.configured else 'no'}",
            f"selected: {'yes' if self.selected else 'no'}",
            f"catalog: {self.catalog}",
            f"model: {self.model or '-'}",
            f"auth: {self.auth_kind or '-'}",
            f"credential: {self.credential.value}",
            f"readiness: {self.readiness.value}",
        ]
        if self.detail:
            rows.append(f"detail: {self.detail}")
        return tuple(rows)




def _provider_for_profile(profile: ProviderProfile) -> ProviderDefinition | None:
    if profile.auth_kind is AuthKind.EXTERNAL_FIRST_PARTY_CLI:
        return provider_definition(ProviderId.CODEX)
    if profile.auth_kind is AuthKind.SUBSCRIPTION_OAUTH:
        return provider_definition(ProviderId.GROK)
    return provider_for_legacy_endpoint(profile.base_url)


class ConnectionService:
    """Creates, selects, and resolves one stored provider connection."""

    def __init__(
        self,
        repository: ProfileRepository,
        credential_store: CredentialStore | None = None,
    ) -> None:
        self._repository = repository
        self._store = credential_store
        self._repository.migrate()

    def _credential_store(self) -> CredentialStore:
        if self._store is None:
            self._store = credential_store_or_default(None)
        return self._store

    def selected_provider(self) -> ProviderDefinition | None:
        name = self._repository.selected_name()
        if name is None:
            return None
        return _provider_for_profile(self._repository.get(name))

    def profile_for_provider(self, identifier: ProviderId | str) -> ProviderProfile:
        definition = provider_definition(identifier)
        matches = [
            profile
            for profile in self._repository.list_profiles()
            if _provider_for_profile(profile) is definition
        ]
        if not matches:
            raise ConnectionError(f'Provider "{definition.identifier.value}" is not connected')
        if len(matches) > 1:
            raise ConnectionError(
                f'Provider "{definition.identifier.value}" has multiple legacy profiles; '
                "select one with the profile command before migration"
            )
        return matches[0]

    def connect_api_key(
        self,
        identifier: ProviderId | str,
        secret: str,
        *,
        model: str | None = None,
    ) -> ProviderProfile:
        definition = provider_definition(identifier)
        availability = definition.auth(AuthMethod.API_KEY)
        if not availability.available:
            raise ConnectionError(availability.reason or "API-key authentication is unavailable")
        if not secret.strip():
            raise ConnectionError("API key cannot be empty")
        assert definition.base_url is not None
        assert definition.default_model is not None
        selected_model = definition.default_model if model is None else model.strip()
        if not selected_model:
            raise ConnectionError("Model cannot be empty")
        profile = ProviderProfile.create(
            name=definition.identifier.value,
            base_url=definition.base_url,
            model=selected_model,
            auth_kind=AuthKind.API_KEY,
            capabilities=definition.capabilities,
        )
        self._save_api_key_profile(profile, secret)
        self._repository.select(profile.name)
        return profile

    def prepare_subscription(self, identifier: ProviderId | str) -> CodexCliConnection:
        definition = provider_definition(identifier)
        availability = definition.auth(AuthMethod.SUBSCRIPTION)
        if not availability.available:
            raise ConnectionError(availability.reason or "Subscription authentication is unavailable")
        if definition.route is not ExecutionRoute.CODEX_CLI:
            raise ConnectionError(
                f'Subscription authentication for "{definition.identifier.value}" '
                "is not implemented yet"
            )
        return CodexCliConnection(definition)

    def connect_subscription(self, identifier: ProviderId | str) -> CodexCliConnection:
        connection = self.prepare_subscription(identifier)
        definition = connection.provider
        assert definition.base_url is not None
        assert definition.default_model is not None
        profile = ProviderProfile.create(
            name=definition.identifier.value,
            base_url=definition.base_url,
            model=definition.default_model,
            auth_kind=AuthKind.EXTERNAL_FIRST_PARTY_CLI,
            capabilities=definition.capabilities,
        )
        with self._repository.transaction():
            try:
                existing = self._repository.get(profile.name)
            except ProfileNotFoundError:
                self._repository.save(profile)
            else:
                if existing.requires_secret:
                    raise ConnectionError(
                        'Connection name "codex" is already used by a credential-backed connection'
                    )
                self._repository.save(profile, replace=True)
            self._repository.select(profile.name)
        return connection

    def resolve(self, identifier: ProviderId | str | None = None) -> ResolvedConnection:
        profile = (
            self.profile_for_provider(identifier)
            if identifier is not None
            else self._selected_profile()
        )
        definition = _provider_for_profile(profile)
        if definition is None:
            raise ConnectionError(
                f'Profile "{profile.name}" is a custom legacy endpoint and cannot '
                "be selected with --provider"
            )
        if definition.route is ExecutionRoute.CODEX_CLI:
            return CodexCliConnection(definition)
        if profile.auth_kind is not AuthKind.API_KEY:
            raise ConnectionError(
                f'Provider "{definition.identifier.value}" requires reauthentication'
            )
        try:
            secret = ProfileService(
                self._repository, self._credential_store()
            ).get_secret(profile)
        except CredentialNotFoundError as exc:
            raise ConnectionError(
                f'Provider "{definition.identifier.value}" has no stored API key'
            ) from exc
        return OpenAICompatibleConnection(
            ApiConfig(profile.base_url, secret, profile.model), definition
        )


    def inspect_provider(self, identifier: ProviderId | str) -> ProviderReadiness:
        """Return offline readiness facts without contacting a provider network."""
        definition = provider_definition(identifier)
        selected = self.selected_provider()
        is_selected = selected is definition
        try:
            profile = self.profile_for_provider(definition.identifier)
        except ConnectionError:
            return ProviderReadiness(
                provider=definition.identifier.value,
                configured=False,
                selected=is_selected,
                catalog=definition.identifier.value,
                model=definition.default_model,
                auth_kind=None,
                credential=CredentialState.ABSENT
                if definition.route is ExecutionRoute.OPENAI_COMPATIBLE
                else CredentialState.NOT_APPLICABLE,
                readiness=LocalReadiness.NOT_READY,
                detail="no stored connection",
            )
        return self._readiness_for_profile(profile, definition, is_selected=is_selected)

    def inspect_selected(self) -> ProviderReadiness | None:
        name = self._repository.selected_name()
        if name is None:
            return None
        try:
            profile = self._repository.get(name)
        except ProfileNotFoundError:
            return ProviderReadiness(
                provider="-",
                configured=False,
                selected=True,
                catalog="-",
                model=None,
                auth_kind=None,
                credential=CredentialState.UNAVAILABLE,
                readiness=LocalReadiness.UNKNOWN,
                detail="selected connection metadata is missing",
            )
        definition = _provider_for_profile(profile)
        if definition is None:
            return ProviderReadiness(
                provider=profile.name,
                configured=True,
                selected=True,
                catalog="custom",
                model=profile.model,
                auth_kind=profile.auth_kind.value,
                credential=self._credential_state(profile),
                readiness=LocalReadiness.NOT_READY,
                detail="custom legacy endpoint is not a catalog provider",
            )
        return self._readiness_for_profile(profile, definition, is_selected=True)

    def _readiness_for_profile(
        self,
        profile: ProviderProfile,
        definition: ProviderDefinition,
        *,
        is_selected: bool,
    ) -> ProviderReadiness:
        credential = self._credential_state(profile)
        catalog_ok = definition.identifier is not ProviderId.CUSTOM
        model = profile.model or definition.default_model
        model_ok = bool(model and str(model).strip())
        if credential is CredentialState.UNAVAILABLE:
            readiness = LocalReadiness.UNKNOWN
            detail = "credential backend unavailable"
        elif definition.route is ExecutionRoute.CODEX_CLI:
            # Codex local CLI/login facts belong to e07s03; metadata alone is not ready.
            readiness = LocalReadiness.NOT_READY
            detail = (
                "catalog or model metadata incomplete"
                if not catalog_ok or not model_ok
                else "delegated Codex readiness requires e07s03 inspection"
            )
        elif (
            catalog_ok
            and model_ok
            and profile.auth_kind is AuthKind.API_KEY
            and credential is CredentialState.PRESENT
        ):
            readiness = LocalReadiness.LOCAL_READY
            detail = None
        elif credential is CredentialState.ABSENT:
            readiness = LocalReadiness.NOT_READY
            detail = "API key is absent"
        else:
            readiness = LocalReadiness.NOT_READY
            detail = "connection is not locally executable"
        return ProviderReadiness(
            provider=definition.identifier.value,
            configured=True,
            selected=is_selected,
            catalog=definition.identifier.value,
            model=model,
            auth_kind=profile.auth_kind.value,
            credential=credential,
            readiness=readiness,
            detail=detail,
        )

    def _credential_state(self, profile: ProviderProfile) -> CredentialState:
        if not profile.requires_secret:
            return CredentialState.NOT_APPLICABLE
        try:
            store = self._credential_store()
        except CredentialStoreError:
            return CredentialState.UNAVAILABLE
        key = self._repository.credential_key(profile.name)
        try:
            secret = store.get_secret(key)
        except CredentialNotFoundError:
            return CredentialState.ABSENT
        except CredentialStoreError:
            return CredentialState.UNAVAILABLE
        if not isinstance(secret, str) or not secret:
            return CredentialState.ABSENT
        return CredentialState.PRESENT

    def disconnect(self, identifier: ProviderId | str) -> None:
        profile = self.profile_for_provider(identifier)
        if profile.requires_secret:
            ProfileService(
                self._repository, self._credential_store()
            ).delete(profile.name)
        else:
            self._repository.delete(profile.name)

    def _selected_profile(self) -> ProviderProfile:
        name = self._repository.selected_name()
        if name is None:
            raise ConnectionError("No provider is connected; run: orbitrelay provider connect")
        try:
            return self._repository.get(name)
        except ProfileNotFoundError as exc:
            raise ConnectionError("The selected provider connection no longer exists") from exc

    def _save_api_key_profile(self, profile: ProviderProfile, secret: str) -> None:
        """Replace metadata and secret without leaving metadata half-written."""

        store = self._credential_store()
        service = ProfileService(self._repository, store)
        with self._repository.transaction():
            try:
                existing = self._repository.get(profile.name)
            except ProfileNotFoundError:
                service.create(profile, secret=secret)
                return
            if not existing.requires_secret:
                raise ConnectionError(
                    f'Connection name "{profile.name}" uses incompatible authentication'
                )
            key = self._repository.credential_key(profile.name)
            old_secret = service.get_secret(existing)
            store.set_secret(key, secret)
            try:
                self._repository.save(profile, replace=True)
            except Exception:
                store.set_secret(key, old_secret)
                raise
