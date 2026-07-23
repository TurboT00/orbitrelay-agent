# story: e01s01

import argparse
import getpass
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TextIO

from dotenv import dotenv_values
from openai import OpenAI

from .agent import run_agent
from .approvals import ApprovalSession, TerminalAuthorizer
from .config import ApiConfig, load_api_config
from .credentials import CredentialStore, ProfileService, credential_store_or_default
from .profile_cli import run_profile_cli
from .profile_store import ProfileRepository, default_profile_path
from .profiles import AuthKind, ProviderProfile


OPENAI_ENV_KEYS = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OrbitRelay coding agent")
    parser.add_argument("user_prompt", help="User prompt")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--profile", help="Named provider profile for this run")
    parser.add_argument(
        "--workspace",
        help="Workspace directory (default: current directory)",
    )
    return parser.parse_args(argv)


def resolve_workspace(value: str | None) -> str:
    workspace = Path.cwd() if value is None else Path(value).expanduser()
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise ValueError(f'Workspace is not a directory: "{workspace}"')
    return str(workspace)


def _api_config_from_profile(
    profile: ProviderProfile,
    repository: ProfileRepository,
    credential_store: CredentialStore | None,
) -> ApiConfig:
    if profile.auth_kind is not AuthKind.API_KEY:
        raise ValueError(
            f'Auth kind "{profile.auth_kind.value}" is not executable in P1'
        )
    secret = ProfileService(
        repository, credential_store_or_default(credential_store)
    ).get_secret(profile)
    return ApiConfig(profile.base_url, secret, profile.model)


def resolve_api_config(
    profile_name: str | None,
    *,
    repository: ProfileRepository,
    credential_store: CredentialStore | None,
) -> ApiConfig | None:
    selected_name = (
        profile_name if profile_name is not None else repository.selected_name()
    )
    if selected_name is None:
        return None
    return _api_config_from_profile(
        repository.get(selected_name), repository, credential_store
    )


def _repository_for_run(
    requested_name: str | None, repository: ProfileRepository | None
) -> tuple[ProfileRepository, bool]:
    if repository is not None:
        return repository, True
    profile_path = default_profile_path()
    use_profiles = requested_name is not None or profile_path.exists()
    return ProfileRepository(profile_path), use_profiles


def _resolved_config(
    args: argparse.Namespace,
    repository: ProfileRepository | None,
    credential_store: CredentialStore | None,
    environment: Mapping[str, str],
) -> ApiConfig:
    profile_repository, use_profiles = _repository_for_run(args.profile, repository)
    profile_config = (
        resolve_api_config(
            args.profile,
            repository=profile_repository,
            credential_store=credential_store,
        )
        if use_profiles
        else None
    )
    return load_api_config(environment) if profile_config is None else profile_config


def _invoke_agent(
    args: argparse.Namespace,
    api_config: ApiConfig,
    input_stream: TextIO | None,
) -> str:
    workspace = resolve_workspace(args.workspace)
    client = OpenAI(api_key=api_config.api_key, base_url=api_config.base_url)
    approval_session = ApprovalSession(
        TerminalAuthorizer(
            sys.stdin if input_stream is None else input_stream,
            sys.stderr,
        )
    )
    return run_agent(
        client,
        args.user_prompt,
        api_config.model,
        working_directory=workspace,
        verbose=args.verbose,
        approval_session=approval_session,
    )


def _run_agent_cli(
    args: argparse.Namespace,
    repository: ProfileRepository | None,
    credential_store: CredentialStore | None,
    environment: Mapping[str, str],
    input_stream: TextIO | None,
) -> int:
    config = _resolved_config(args, repository, credential_store, environment)
    print(_invoke_agent(args, config, input_stream))
    return 0


def _environment_source(
    process_environment: Mapping[str, str],
    dotenv_environment: Mapping[str, str],
) -> Mapping[str, str]:
    if any(key in process_environment for key in OPENAI_ENV_KEYS):
        return process_environment
    return dotenv_environment


def _dotenv_environment() -> dict[str, str]:
    values = {
        key: value
        for key, value in dotenv_values(interpolate=False).items()
        if isinstance(value, str) and key in OPENAI_ENV_KEYS
    }
    if any("${" in value for value in values.values()):
        raise ValueError("OPENAI_* dotenv interpolation is not supported")
    return values


def _dispatch_cli(
    raw_argv: Sequence[str],
    repository: ProfileRepository,
    credential_store: CredentialStore | None,
    secret_prompt: Callable[[str], str],
    input_stream: TextIO | None,
    environment: Mapping[str, str],
) -> int:
    if raw_argv and raw_argv[0] == "profile":
        return run_profile_cli(
            raw_argv[1:], repository, credential_store, secret_prompt, input_stream
        )
    return _run_agent_cli(
        parse_args(raw_argv),
        repository,
        credential_store,
        environment,
        input_stream,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    profile_repository: ProfileRepository | None = None,
    credential_store: CredentialStore | None = None,
    secret_prompt: Callable[[str], str] = getpass.getpass,
    input_stream: TextIO | None = None,
) -> int:
    process_environment = dict(os.environ)
    repository = profile_repository or ProfileRepository(default_profile_path(process_environment))
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    environment = _environment_source(process_environment, _dotenv_environment())
    return _dispatch_cli(raw_argv, repository, credential_store, secret_prompt, input_stream, environment)


if __name__ == "__main__":
    raise SystemExit(main())
