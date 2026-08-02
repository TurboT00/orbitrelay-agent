"""Public provider connection commands."""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence
from typing import TextIO

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

    return parser.parse_args(argv)


def run_provider_cli(
    argv: Sequence[str],
    repository: ProfileRepository | None,
    credential_store: CredentialStore | None,
    secret_prompt: Callable[[str], str] = getpass.getpass,
    *,
    output: TextIO | None = None,
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
    except ConnectionError as exc:
        print(str(exc), file=stream)
        return 1
    raise AssertionError(f"Unknown provider action: {args.provider_action}")
