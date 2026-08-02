"""The supported provider catalog.

Provider-specific defaults and authentication availability live here so command
handlers and connection storage do not grow their own lists of providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class ProviderId(StrEnum):
    OPENAI = "openai"
    CODEX = "codex"
    GEMINI = "gemini"
    GROK = "grok"
    DEEPSEEK = "deepseek"
    CUSTOM = "custom"


class AuthMethod(StrEnum):
    API_KEY = "api_key"
    SUBSCRIPTION = "subscription"


class ExecutionRoute(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    CODEX_CLI = "codex_cli"


@dataclass(frozen=True)
class AuthAvailability:
    method: AuthMethod
    available: bool
    reason: str | None = None


@dataclass(frozen=True)
class ProviderDefinition:
    identifier: ProviderId
    display_name: str
    route: ExecutionRoute
    base_url: str | None
    default_model: str | None
    capabilities: frozenset[str]
    authentication: tuple[AuthAvailability, ...]
    documentation_url: str
    legacy_api_key_env: str | None = None
    legacy_model_env: str | None = None
    legacy_base_url_envs: tuple[str, ...] = ()

    def auth(self, method: AuthMethod | str) -> AuthAvailability:
        requested = AuthMethod(method)
        for availability in self.authentication:
            if availability.method is requested:
                return availability
        raise ValueError(
            f'{self.display_name} does not define authentication method '
            f'"{requested.value}"'
        )

    def requires_api_key(self) -> bool:
        return self.auth(AuthMethod.API_KEY).available


REQUIRED_CAPABILITIES: Final = frozenset(
    {"tool_calling", "assistant_message_passthrough"}
)


def _api_key_only(
    identifier: ProviderId,
    display_name: str,
    base_url: str,
    default_model: str,
    documentation_url: str,
    api_key_env: str,
    model_env: str,
    *base_url_envs: str,
) -> ProviderDefinition:
    return ProviderDefinition(
        identifier=identifier,
        display_name=display_name,
        route=ExecutionRoute.OPENAI_COMPATIBLE,
        base_url=base_url,
        default_model=default_model,
        capabilities=REQUIRED_CAPABILITIES,
        authentication=(
            AuthAvailability(AuthMethod.API_KEY, True),
            AuthAvailability(
                AuthMethod.SUBSCRIPTION,
                False,
                "No documented OrbitRelay subscription authorization is available.",
            ),
        ),
        documentation_url=documentation_url,
        legacy_api_key_env=api_key_env,
        legacy_model_env=model_env,
        legacy_base_url_envs=base_url_envs,
    )


_PROVIDERS: Final[tuple[ProviderDefinition, ...]] = (
    ProviderDefinition(
        identifier=ProviderId.OPENAI,
        display_name="OpenAI",
        route=ExecutionRoute.OPENAI_COMPATIBLE,
        base_url="https://api.openai.com/v1/",
        default_model="gpt-5.6-luna",
        capabilities=REQUIRED_CAPABILITIES,
        authentication=(
            AuthAvailability(AuthMethod.API_KEY, True),
            AuthAvailability(
                AuthMethod.SUBSCRIPTION,
                False,
                "Use the Codex provider for the official subscription CLI path.",
            ),
        ),
        documentation_url="https://platform.openai.com/docs/api-reference/authentication",
        legacy_api_key_env="OPENAI_API_KEY",
        legacy_model_env="OPENAI_MODEL",
        legacy_base_url_envs=("OPENAI_URL", "OPENAI_BASE_URL"),
    ),
    ProviderDefinition(
        identifier=ProviderId.CODEX,
        display_name="OpenAI Codex",
        route=ExecutionRoute.CODEX_CLI,
        base_url="https://chatgpt.com",
        default_model="codex",
        capabilities=REQUIRED_CAPABILITIES,
        authentication=(
            AuthAvailability(
                AuthMethod.API_KEY,
                False,
                "Codex credentials are managed by the official Codex CLI.",
            ),
            AuthAvailability(AuthMethod.SUBSCRIPTION, True),
        ),
        documentation_url="https://developers.openai.com/codex/auth",
    ),
    ProviderDefinition(
        identifier=ProviderId.GEMINI,
        display_name="Google Gemini",
        route=ExecutionRoute.OPENAI_COMPATIBLE,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_model="gemini-3.6-flash",
        capabilities=REQUIRED_CAPABILITIES,
        authentication=(
            AuthAvailability(AuthMethod.API_KEY, True),
            AuthAvailability(
                AuthMethod.SUBSCRIPTION,
                False,
                "Gemini OAuth remains unavailable until the documented integration probe passes.",
            ),
        ),
        documentation_url="https://ai.google.dev/gemini-api/docs/api-key",
        legacy_api_key_env="GEMINI_API_KEY",
        legacy_model_env="GEMINI_MODEL",
        legacy_base_url_envs=("GEMINI_URL", "GEMINI_BASE_URL"),
    ),
    _api_key_only(
        ProviderId.GROK,
        "xAI Grok",
        "https://api.x.ai/v1",
        "grok-4.5",
        "https://docs.x.ai/developers/quickstart",
        "XAI_API_KEY",
        "XAI_MODEL",
        "XAI_URL",
        "XAI_BASE_URL",
    ),
    _api_key_only(
        ProviderId.DEEPSEEK,
        "DeepSeek",
        "https://api.deepseek.com",
        "deepseek-v4-flash",
        "https://api-docs.deepseek.com/",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_URL",
        "DEEPSEEK_BASE_URL",
    ),
)

_BY_IDENTIFIER: Final = {provider.identifier: provider for provider in _PROVIDERS}


def supported_providers() -> tuple[ProviderDefinition, ...]:
    return _PROVIDERS


def provider_definition(identifier: ProviderId | str) -> ProviderDefinition:
    try:
        return _BY_IDENTIFIER[ProviderId(identifier)]
    except (KeyError, ValueError) as exc:
        names = ", ".join(provider.identifier.value for provider in _PROVIDERS)
        raise ValueError(f"Unknown provider {identifier!r}; choose one of: {names}") from exc


def provider_for_legacy_endpoint(base_url: str) -> ProviderDefinition | None:
    normalized = base_url.rstrip("/")
    for provider in _PROVIDERS:
        if provider.base_url is not None and provider.base_url.rstrip("/") == normalized:
            return provider
    return None
