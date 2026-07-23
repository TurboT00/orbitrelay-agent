# story: e01s01

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TextIO

from .credentials import CredentialStore, ProfileService, credential_store_or_default
from .profile_store import ProfileRepository, default_profile_path
from .profiles import AuthKind, ProviderCapability, ProviderProfile
from .redaction import redact_secrets


@dataclass(frozen=True)
class ProfileCommandContext:
    repository: ProfileRepository
    credential_store: CredentialStore | None
    secret_prompt: Callable[[str], str]
    input_stream: TextIO


def _configure_create_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--auth-kind", required=True, choices=[kind.value for kind in AuthKind]
    )
    parser.add_argument(
        "--capability",
        action="append",
        required=True,
        choices=[item.value for item in ProviderCapability],
    )
    parser.add_argument(
        "--secret-stdin",
        action="store_true",
        help="Read the credential from standard input instead of prompting",
    )


def _add_named_action(actions: Any, name: str, help_text: str) -> None:
    parser = actions.add_parser(name, help=help_text)
    parser.add_argument("name")


def parse_profile_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="orbitrelay profile")
    actions = parser.add_subparsers(dest="profile_action", required=True)
    create = actions.add_parser("create", help="Create a named provider profile")
    _configure_create_parser(create)
    actions.add_parser("list", help="List named provider profiles")
    _add_named_action(actions, "show", "Inspect secret-free profile metadata")
    _add_named_action(actions, "select", "Select the default profile")
    _add_named_action(actions, "delete", "Delete a named profile")
    return parser.parse_args(argv)


def _profile_from_args(args: argparse.Namespace) -> ProviderProfile:
    return ProviderProfile.create(
        name=args.name,
        base_url=args.base_url,
        model=args.model,
        auth_kind=args.auth_kind,
        capabilities=args.capability,
    )


def _read_secret(args: argparse.Namespace, context: ProfileCommandContext) -> str:
    if args.secret_stdin:
        return context.input_stream.readline().rstrip("\r\n")
    return context.secret_prompt("Provider credential: ")


def _create_profile(args: argparse.Namespace, context: ProfileCommandContext) -> int:
    profile = _profile_from_args(args)
    if args.secret_stdin and not profile.requires_secret:
        raise ValueError(
            f'Auth kind "{profile.auth_kind.value}" does not accept a credential'
        )
    if profile.requires_secret:
        service = ProfileService(
            context.repository, credential_store_or_default(context.credential_store)
        )
        service.create(profile, secret=_read_secret(args, context))
    else:
        context.repository.save(profile)
    print(f'Created profile "{profile.name}".')
    return 0


def _list_profiles(
    _args: argparse.Namespace, context: ProfileCommandContext
) -> int:
    profiles = context.repository.list_profiles()
    if not profiles:
        print("No profiles configured.")
        return 0
    selected = context.repository.selected_name()
    for profile in profiles:
        marker = "*" if profile.name == selected else " "
        print(
            f"{marker} {profile.name} {profile.auth_kind.value} "
            f"{profile.base_url} {profile.model}"
        )
    return 0


def _show_profile(args: argparse.Namespace, context: ProfileCommandContext) -> int:
    profile = context.repository.get(args.name)
    visible = profile.to_dict()
    visible["selected"] = context.repository.selected_name() == profile.name
    print(json.dumps(redact_secrets(visible), indent=2, sort_keys=True))
    return 0


def _select_profile(args: argparse.Namespace, context: ProfileCommandContext) -> int:
    context.repository.select(args.name)
    print(f'Selected profile "{args.name}".')
    return 0


def _delete_profile(args: argparse.Namespace, context: ProfileCommandContext) -> int:
    profile = context.repository.get(args.name)
    if profile.requires_secret:
        service = ProfileService(
            context.repository, credential_store_or_default(context.credential_store)
        )
        service.delete(profile.name)
    else:
        context.repository.delete(profile.name)
    print(f'Deleted profile "{profile.name}".')
    return 0


PROFILE_ACTIONS: dict[
    str, Callable[[argparse.Namespace, ProfileCommandContext], int]
] = {
    "create": _create_profile,
    "list": _list_profiles,
    "show": _show_profile,
    "select": _select_profile,
    "delete": _delete_profile,
}


def run_profile_command(
    args: argparse.Namespace, context: ProfileCommandContext
) -> int:
    try:
        action = PROFILE_ACTIONS[args.profile_action]
    except KeyError as exc:
        raise AssertionError(f"Unknown profile action: {args.profile_action}") from exc
    return action(args, context)


def run_profile_cli(
    argv: Sequence[str],
    repository: ProfileRepository | None,
    credential_store: CredentialStore | None,
    secret_prompt: Callable[[str], str],
    input_stream: TextIO | None,
) -> int:
    context = ProfileCommandContext(
        repository or ProfileRepository(default_profile_path()),
        credential_store,
        secret_prompt,
        sys.stdin if input_stream is None else input_stream,
    )
    return run_profile_command(parse_profile_args(argv), context)
