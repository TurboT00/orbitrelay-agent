import argparse
import getpass
import json
import os
import sys
from collections.abc import Callable, Mapping
from io import TextIOBase
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .agent import run_agent
from .config import load_api_config
from .credentials import CredentialStore, KeyringCredentialStore, ProfileService
from .profiles import (
    AuthKind,
    ProfileRepository,
    ProviderCapability,
    ProviderProfile,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Chatbot")
    parser.add_argument("user_prompt", type=str, help="User prompt")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument(
        "--workspace",
        type=str,
        help="Workspace directory (default: current directory)",
    )
    return parser.parse_args(argv)


def parse_profile_args(argv=None):
    parser = argparse.ArgumentParser(prog="orbitrelay profile")
    actions = parser.add_subparsers(dest="profile_action", required=True)

    create = actions.add_parser("create", help="Create a named provider profile")
    create.add_argument("name")
    create.add_argument("--base-url", required=True)
    create.add_argument("--model", required=True)
    create.add_argument(
        "--auth-kind",
        required=True,
        choices=[kind.value for kind in AuthKind],
    )
    create.add_argument(
        "--capability",
        action="append",
        required=True,
        choices=[capability.value for capability in ProviderCapability],
    )
    create.add_argument(
        "--secret-stdin",
        action="store_true",
        help="Read the credential from standard input instead of prompting",
    )

    actions.add_parser("list", help="List named provider profiles")
    show = actions.add_parser("show", help="Inspect secret-free profile metadata")
    show.add_argument("name")
    select = actions.add_parser("select", help="Select the default profile")
    select.add_argument("name")
    delete = actions.add_parser("delete", help="Delete a named profile")
    delete.add_argument("name")
    return parser.parse_args(argv)


def resolve_workspace(value: str | None) -> str:
    workspace = Path.cwd() if value is None else Path(value).expanduser()
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise ValueError(f'Workspace is not a directory: "{workspace}"')
    return str(workspace)


def default_profile_path(environ: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    configured_home = values.get("ORBITRELAY_HOME", "").strip()
    application_home = (
        Path(configured_home).expanduser()
        if configured_home
        else Path.home() / ".orbitrelay"
    )
    return application_home / "profiles.json"


def _read_secret(
    *,
    from_stdin: bool,
    input_stream: TextIOBase,
    secret_prompt: Callable[[str], str],
) -> str:
    if from_stdin:
        return input_stream.readline().rstrip("\r\n")
    return secret_prompt("Provider credential: ")


def _credential_store(value: CredentialStore | None) -> CredentialStore:
    return KeyringCredentialStore() if value is None else value


def run_profile_command(
    args: Any,
    *,
    repository: ProfileRepository,
    credential_store: CredentialStore | None,
    secret_prompt: Callable[[str], str],
    input_stream: TextIOBase,
) -> int:
    if args.profile_action == "create":
        profile = ProviderProfile.create(
            name=args.name,
            base_url=args.base_url,
            model=args.model,
            auth_kind=args.auth_kind,
            capabilities=args.capability,
        )
        if profile.requires_secret:
            secret = _read_secret(
                from_stdin=args.secret_stdin,
                input_stream=input_stream,
                secret_prompt=secret_prompt,
            )
            ProfileService(repository, _credential_store(credential_store)).create(
                profile, secret=secret
            )
        else:
            repository.save(profile)
        print(f'Created profile "{profile.name}".')
        return 0

    if args.profile_action == "list":
        selected = repository.selected_name()
        profiles = repository.list_profiles()
        if not profiles:
            print("No profiles configured.")
            return 0
        for profile in profiles:
            marker = "*" if profile.name == selected else " "
            print(
                f"{marker} {profile.name} {profile.auth_kind.value} "
                f"{profile.base_url} {profile.model}"
            )
        return 0

    if args.profile_action == "show":
        profile = repository.get(args.name)
        visible = profile.to_dict()
        visible["selected"] = repository.selected_name() == profile.name
        print(json.dumps(visible, indent=2, sort_keys=True))
        return 0

    if args.profile_action == "select":
        repository.select(args.name)
        print(f'Selected profile "{args.name}".')
        return 0

    if args.profile_action == "delete":
        profile = repository.get(args.name)
        if profile.requires_secret:
            ProfileService(repository, _credential_store(credential_store)).delete(
                profile.name
            )
        else:
            repository.delete(profile.name)
        print(f'Deleted profile "{profile.name}".')
        return 0


    raise AssertionError(f"Unknown profile action: {args.profile_action}")


def main(
    argv=None,
    *,
    profile_repository: ProfileRepository | None = None,
    credential_store: CredentialStore | None = None,
    secret_prompt: Callable[[str], str] = getpass.getpass,
    input_stream: TextIOBase | None = None,
) -> int:
    load_dotenv()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] == "profile":
        args = parse_profile_args(raw_argv[1:])
        repository = profile_repository or ProfileRepository(default_profile_path())
        return run_profile_command(
            args,
            repository=repository,
            credential_store=credential_store,
            secret_prompt=secret_prompt,
            input_stream=sys.stdin if input_stream is None else input_stream,
        )

    args = parse_args(raw_argv)
    api_config = load_api_config()
    working_directory = resolve_workspace(args.workspace)
    client = OpenAI(api_key=api_config.api_key, base_url=api_config.base_url)
    result = run_agent(
        client,
        args.user_prompt,
        api_config.model,
        working_directory=working_directory,
        verbose=args.verbose,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
