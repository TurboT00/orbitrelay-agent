"""Single resolution boundary for stored provider connections.

This service deliberately uses the existing secure profile repository and
keyring storage while the on-disk metadata migrates from "profiles" to
"connections".  No caller outside this module needs provider-specific
credential logic.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from .codex_bridge import CodexAuthentication, CodexBridge
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
from .provider_verification import (
    ProviderProbe,
    VerificationEvidence,
    VerificationOutcome,
    classify_probe_error,
    default_openai_compatible_probe,
)
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
    installation: str | None = None
    authentication: str | None = None
    last_verification: VerificationEvidence | None = None

    def lines(self) -> tuple[str, ...]:
        rows = [
            f"provider: {self.provider}",
            f"configured: {'yes' if self.configured else 'no'}",
            f"selected: {'yes' if self.selected else 'no'}",
            f"catalog: {self.catalog}",
            f"model: {self.model or '-'}",
            f"auth: {self.auth_kind or '-'}",
            f"credential: {self.credential.value}",
        ]
        if self.installation is not None:
            rows.append(f"installation: {self.installation}")
        if self.authentication is not None:
            rows.append(f"authentication: {self.authentication}")
        rows.append(f"readiness: {self.readiness.value}")
        if self.detail:
            rows.append(f"detail: {self.detail}")
        if self.last_verification is not None:
            rows.extend(self.last_verification.lines())
        return tuple(rows)


@dataclass(frozen=True, slots=True)
class ProviderVerificationResult:
    """Outcome of an explicit verification command."""

    provider: str
    outcome: VerificationOutcome
    route: str
    model: str
    detail: str | None
    evidence: VerificationEvidence | None

    def lines(self) -> tuple[str, ...]:
        rows = [
            f"provider: {self.provider}",
            f"verification: {self.outcome.value}",
            f"route: {self.route}",
            f"model: {self.model}",
        ]
        if self.detail:
            rows.append(f"detail: {self.detail}")
        if self.evidence is not None:
            rows.append("persisted: historical")
            rows.extend(self.evidence.lines(prefix="historical_verification"))
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
        *,
        codex_bridge: CodexBridge | None = None,
        probe: ProviderProbe | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._repository = repository
        self._store = credential_store
        self._codex_bridge = codex_bridge
        self._probe = probe or default_openai_compatible_probe
        self._clock = clock or time.time
        self._repository.migrate()

    def _codex(self) -> CodexBridge:
        if self._codex_bridge is None:
            self._codex_bridge = CodexBridge()
        return self._codex_bridge

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



    def _with_last_verification(
        self,
        readiness: ProviderReadiness,
        profile_name: str | None,
    ) -> ProviderReadiness:
        if profile_name is None:
            return readiness
        evidence = self._repository.get_verification(profile_name)
        if evidence is None:
            return readiness
        return ProviderReadiness(
            provider=readiness.provider,
            configured=readiness.configured,
            selected=readiness.selected,
            catalog=readiness.catalog,
            model=readiness.model,
            auth_kind=readiness.auth_kind,
            credential=readiness.credential,
            readiness=readiness.readiness,
            detail=readiness.detail,
            installation=readiness.installation,
            authentication=readiness.authentication,
            last_verification=evidence,
        )

    def verify_provider(
        self,
        identifier: ProviderId | str,
        *,
        probe: ProviderProbe | None = None,
    ) -> ProviderVerificationResult:
        """Run a minimal live probe only for an explicit verification command."""
        definition = provider_definition(identifier)
        if definition.route is not ExecutionRoute.OPENAI_COMPATIBLE:
            raise ConnectionError(
                f'Provider verify is only available for OpenAI-compatible API '
                f'connections; "{definition.identifier.value}" is not supported'
            )
        try:
            profile = self.profile_for_provider(definition.identifier)
        except ConnectionError:
            return ProviderVerificationResult(
                provider=definition.identifier.value,
                outcome=VerificationOutcome.UNAVAILABLE,
                route=definition.route.value,
                model=definition.default_model or "-",
                detail="no stored connection",
                evidence=None,
            )
        route = definition.route.value
        model = profile.model or definition.default_model or "-"
        credential = self._credential_state(profile)
        if credential is CredentialState.ABSENT:
            return self._finish_verification(
                profile_name=profile.name,
                provider=definition.identifier.value,
                outcome=VerificationOutcome.UNAVAILABLE,
                route=route,
                model=model,
                detail="API key is absent",
                persist=False,
            )
        if credential is CredentialState.UNAVAILABLE:
            return self._finish_verification(
                profile_name=profile.name,
                provider=definition.identifier.value,
                outcome=VerificationOutcome.UNAVAILABLE,
                route=route,
                model=model,
                detail="credential backend unavailable",
                persist=False,
            )
        try:
            secret = ProfileService(
                self._repository, self._credential_store()
            ).get_secret(profile)
        except (CredentialNotFoundError, CredentialStoreError):
            return self._finish_verification(
                profile_name=profile.name,
                provider=definition.identifier.value,
                outcome=VerificationOutcome.UNAVAILABLE,
                route=route,
                model=model,
                detail="API key is unavailable",
                persist=False,
            )
        active_probe = probe or self._probe
        try:
            active_probe(
                base_url=profile.base_url,
                api_key=secret,
                model=model,
            )
        except BaseException as exc:
            outcome, detail = classify_probe_error(exc)
            return self._finish_verification(
                profile_name=profile.name,
                provider=definition.identifier.value,
                outcome=outcome,
                route=route,
                model=model,
                detail=detail,
                persist=True,
            )
        return self._finish_verification(
            profile_name=profile.name,
            provider=definition.identifier.value,
            outcome=VerificationOutcome.OK,
            route=route,
            model=model,
            detail=None,
            persist=True,
        )

    def _finish_verification(
        self,
        *,
        profile_name: str,
        provider: str,
        outcome: VerificationOutcome,
        route: str,
        model: str,
        detail: str | None,
        persist: bool,
    ) -> ProviderVerificationResult:
        evidence: VerificationEvidence | None = None
        if persist:
            evidence = VerificationEvidence(
                checked_at=float(self._clock()),
                outcome=outcome,
                route=route,
                model=model,
            )
            self._repository.set_verification(profile_name, evidence)
        return ProviderVerificationResult(
            provider=provider,
            outcome=outcome,
            route=route,
            model=model,
            detail=detail,
            evidence=evidence,
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
        return self._with_last_verification(
            self._readiness_for_profile(profile, definition, is_selected=is_selected),
            profile.name,
        )

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
        return self._with_last_verification(
            self._readiness_for_profile(profile, definition, is_selected=True),
            profile.name,
        )

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
            return self._codex_readiness(
                profile,
                definition,
                is_selected=is_selected,
                catalog_ok=catalog_ok,
                model_ok=model_ok,
                model=model,
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


    def _codex_readiness(
        self,
        profile: ProviderProfile,
        definition: ProviderDefinition,
        *,
        is_selected: bool,
        catalog_ok: bool,
        model_ok: bool,
        model: str | None,
    ) -> ProviderReadiness:
        delegated = self._codex().inspect_readiness()
        installation = "available" if delegated.installed else "unavailable"
        authentication = delegated.authentication.value
        if not catalog_ok or not model_ok:
            readiness = LocalReadiness.NOT_READY
            detail = "catalog or model metadata incomplete"
        elif delegated.authentication is CodexAuthentication.MISSING_CLI:
            readiness = LocalReadiness.NOT_READY
            detail = delegated.detail or "official Codex CLI is not available"
        elif delegated.authentication is CodexAuthentication.AUTHENTICATED:
            readiness = LocalReadiness.LOCAL_READY
            detail = None
        elif delegated.authentication is CodexAuthentication.NOT_AUTHENTICATED:
            readiness = LocalReadiness.NOT_READY
            detail = delegated.detail or "run: orbitrelay codex login"
        else:
            readiness = LocalReadiness.UNKNOWN
            detail = delegated.detail or "login status was inconclusive"
        return ProviderReadiness(
            provider=definition.identifier.value,
            configured=True,
            selected=is_selected,
            catalog=definition.identifier.value,
            model=model,
            auth_kind=profile.auth_kind.value,
            credential=CredentialState.NOT_APPLICABLE,
            readiness=readiness,
            detail=detail,
            installation=installation,
            authentication=authentication,
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
