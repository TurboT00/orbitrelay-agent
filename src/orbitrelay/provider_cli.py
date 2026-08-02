"""Public provider connection commands."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import TextIO

from dotenv import dotenv_values
from .codex_cli import run_codex_cli
from .connection_service import ConnectionError, ConnectionService
from .credentials import CredentialStore
from .profile_store import ProfileRepository, default_profile_path
from .providers import AuthMethod, ProviderId, supported_providers


def parse_provider_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="orbitrelay provider")
    actions = parser.add_subparsers(dest="provider_action", required=True)

    actions.add_parser("list", help="List supported providers and methods")

    connect = actions.add_parser("connect", help="Connect and select a provider")
    connect.add_argument("provider", choices=[item.value for item in ProviderId if item is not ProviderId.CUSTOM])
    connect.add_argument(
        "--method",
        choices=[method.value for method in AuthMethod],
        required=True,
        help="Authentication method to use",
    )

    status = actions.add_parser("status", help="Show a provider connection status")
    status.add_argument("provider", nargs="?", choices=[item.value for item in ProviderId if item is not ProviderId.CUSTOM])

    disconnect = actions.add_parser("disconnect", help="Disconnect a provider")
    disconnect.add_argument("provider", choices=[item.value for item in ProviderId if item is not ProviderId.CUSTOM])

    import_env = actions.add_parser(
        "import-env", help="Import one provider API key from environment or .env"
    )
    import_env.add_argument(
        "--provider",
        required=True,
        choices=[item.value for item in ProviderId if item is not ProviderId.CUSTOM],
    )
    return parser.parse_args(argv)


def run_provider_cli(
    argv: Sequence[str],
    repository: ProfileRepository | None,
    credential_store: CredentialStore | None,
    secret_prompt: Callable[[str], str] = getpass.getpass,
    *,
    output: TextIO | None = None,
    environment: Mapping[str, str] | None = None,
    dotenv_environment: Mapping[str, str] | None = None,
) -> int:
    args = parse_provider_args(argv)
    stream = sys.stdout if output is None else output
    service = ConnectionService(
        repository or ProfileRepository(default_profile_path()), credential_store
    )
    try:
        if args.provider_action == "list":
            selected = service.selected_provider()
            for provider in supported_providers():
                marker = "*" if selected is provider else " "
                methods = ", ".join(
                    availability.method.value
                    for availability in provider.authentication
                    if availability.available
                )
                print(f"{marker} {provider.identifier.value}: {methods or 'unavailable'}", file=stream)
            return 0
        if args.provider_action == "connect":
            identifier = ProviderId(args.provider)
            method = AuthMethod(args.method)
            if method is AuthMethod.API_KEY:
                secret = secret_prompt(f"{identifier.value} API key: ")
                service.connect_api_key(identifier, secret)
                print(f'Connected and selected provider "{identifier.value}".', file=stream)
                return 0
            connection = service.prepare_subscription(identifier)
            if connection.provider.identifier is ProviderId.CODEX:
                result = run_codex_cli(["login"], output=stream)
                if result:
                    return result
            service.connect_subscription(identifier)
            print(f'Connected provider "{identifier.value}".', file=stream)
            return 0
        if args.provider_action == "status":
            if args.provider is None:
                selected = service.selected_provider()
                if selected is None:
                    print("No provider is selected.", file=stream)
                else:
                    print(f"Selected provider: {selected.identifier.value}", file=stream)
                return 0
            profile = service.profile_for_provider(ProviderId(args.provider))
            print(f'Provider "{args.provider}" is connected as "{profile.name}".', file=stream)
            return 0
        if args.provider_action == "disconnect":
            service.disconnect(ProviderId(args.provider))
            print(f'Disconnected provider "{args.provider}".', file=stream)
            return 0
        if args.provider_action == "import-env":
            identifier = ProviderId(args.provider)
            definition = next(
                item for item in supported_providers() if item.identifier is identifier
            )
            if definition.legacy_api_key_env is None:
                raise ConnectionError(
                    f'Provider "{identifier.value}" cannot import an API key'
                )
            values = _import_values(
                os.environ if environment is None else environment,
                dotenv_environment,
            )
            candidates = [
                item.identifier
                for item in supported_providers()
                if item.legacy_api_key_env
                and values.get(item.legacy_api_key_env, "").strip()
            ]
            if not candidates:
                raise ConnectionError("No supported provider API key was found to import")
            if candidates != [identifier]:
                names = ", ".join(item.value for item in candidates)
                raise ConnectionError(f"Environment is ambiguous; found API keys for: {names}")
            for key in definition.legacy_base_url_envs:
                override = values.get(key, "").strip()
                if override and override.rstrip("/") != (definition.base_url or "").rstrip("/"):
                    raise ConnectionError(f"{key} is not supported by provider import")
            model = values.get(definition.legacy_model_env or "", "").strip() or None
            service.connect_api_key(
                identifier, values[definition.legacy_api_key_env].strip(), model=model
            )
            print(f'Imported and selected provider "{identifier.value}".', file=stream)
            return 0
    except ConnectionError as exc:
        print(str(exc), file=stream)
        return 1
    raise AssertionError(f"Unknown provider action: {args.provider_action}")


def _import_values(
    environment: Mapping[str, str], dotenv_environment: Mapping[str, str] | None
) -> dict[str, str]:
    dotenv = dotenv_values(interpolate=False) if dotenv_environment is None else dotenv_environment
    values = {
        key: value
        for key, value in dotenv.items()
        if isinstance(value, str)
    }
    values.update({key: value for key, value in environment.items() if isinstance(value, str)})
    if any("${" in value for value in values.values()):
        raise ConnectionError("Environment interpolation is not supported")
    return values
