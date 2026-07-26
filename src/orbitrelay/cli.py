# story: e01s01
# story: e02s04
# story: e02s05
# story: e03s01
# story: e03s02
# story: e03s03
# story: e03s04
# story: e03s05
# story: e03s06
# story: e04s02
# story: e04s03
# story: e04s06

import argparse
import getpass
import math
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TextIO

from dotenv import dotenv_values
from openai import APIStatusError, OpenAI

from .agent import run_agent
from .approvals import ApprovalMode, ApprovalSession
from .auth_cli import run_auth_cli
from .codex_cli import run_codex_cli
from .config import ApiConfig, load_api_config
from .credentials import CredentialStore, ProfileService, credential_store_or_default
from .events import EventCollector, EventType, RunEvent
from .profile_cli import run_profile_cli
from .profile_store import ProfileRepository, default_profile_path
from .profiles import AuthKind, ProviderProfile
from .run_summary import format_run_summary, summarize_run
from .session_cli import run_session_cli
from .sessions import (
    SessionCorruptionError,
    SessionError,
    SessionNotFoundError,
    SessionStore,
)
from .supergrok_oauth import (
    SuperGrokAuthService,
    SuperGrokOAuthClient,
    SuperGrokReauthRequired,
    UrlLibTransport,
)
from .terminal_authorizer import TerminalAuthorizer

DEEPSEEK_ENV_KEYS = ("DEEPSEEK_API_KEY", "DEEPSEEK_URL", "DEEPSEEK_MODEL")
GEMINI_ENV_KEYS = ("GEMINI_API_KEY", "GEMINI_URL", "GEMINI_MODEL")
XAI_ENV_KEYS = ("XAI_API_KEY", "XAI_URL", "XAI_MODEL")
TRANSPORT_ENV_KEYS = DEEPSEEK_ENV_KEYS + GEMINI_ENV_KEYS + XAI_ENV_KEYS
DEFAULT_APPROVAL_TIMEOUT = 60.0
MAX_APPROVAL_TIMEOUT = 300.0
CONSEQUENTIAL_TOOL_NAMES = frozenset({"write_file", "run_python_file"})


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OrbitRelay personal assistant")
    parser.add_argument("user_prompt", help="User prompt")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream model token deltas and tool progress to stderr",
    )
    parser.add_argument("--profile", help="Named provider profile for this run")
    parser.add_argument(
        "--workspace",
        help="Workspace directory (default: current directory)",
    )
    parser.add_argument(
        "--session",
        metavar="ID",
        help="Create or resume a local session under ORBITRELAY_HOME/sessions",
    )
    parser.add_argument(
        "--new-session",
        action="store_true",
        help="Create a new session id (prints id on stderr); optional with --session",
    )
    _add_approval_options(parser)
    return parser.parse_args(argv)


def _add_approval_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--approval-policy",
        choices=[mode.value for mode in ApprovalMode],
        default=ApprovalMode.CONFIRM.value,
        help="Approval policy: confirm, read-only, or pre-approved",
    )
    parser.add_argument(
        "--approval-timeout",
        default=str(int(DEFAULT_APPROVAL_TIMEOUT)),
        metavar="SECONDS",
        help="Confirmation timeout in seconds (default: 60; maximum: 300)",
    )
    parser.add_argument(
        "--approve-tool",
        action="append",
        default=[],
        metavar="TOOL",
        help="Pre-approve one exact consequential tool (repeatable)",
    )


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
    if profile.auth_kind is AuthKind.API_KEY:
        secret = ProfileService(
            repository, credential_store_or_default(credential_store)
        ).get_secret(profile)
        return ApiConfig(profile.base_url, secret, profile.model)
    if profile.auth_kind is AuthKind.SUBSCRIPTION_OAUTH:
        service = SuperGrokAuthService(
            repository,
            credential_store,
            SuperGrokOAuthClient(UrlLibTransport()),
        )
        try:
            token = service.get_valid_access_token(profile.name)
        except SuperGrokReauthRequired as exc:
            raise ValueError(str(exc)) from exc
        return ApiConfig(profile.base_url, token, profile.model)
    raise ValueError(f'Auth kind "{profile.auth_kind.value}" is not executable')


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


def _provider_http_error_message(exc: APIStatusError) -> str:
    status = getattr(exc, "status_code", None)
    if status == 401:
        return (
            "Provider authentication failed (HTTP 401). "
            "Check credentials or run: orbitrelay auth supergrok login"
        )
    if status == 403:
        return (
            "Provider entitlement/permission denied (HTTP 403). "
            "For SuperGrok OAuth, try XAI_API_KEY BYOK fallback or verify "
            "subscription tier."
        )
    return f"Provider request failed (HTTP {status})"


def _stream_live_sink(event: RunEvent) -> None:
    if event.type is EventType.MODEL_DELTA:
        text = event.data.get("text")
        if isinstance(text, str) and text:
            print(text, end="", file=sys.stderr, flush=True)
        return
    if event.type is EventType.TOOL_PROGRESS:
        tool = event.data.get("tool", "tool")
        phase = event.data.get("phase", "progress")
        print(f"\n[{phase}] {tool}", file=sys.stderr, flush=True)


def _prepare_session(
    args: argparse.Namespace,
    *,
    workspace: str,
    model: str,
    environment: Mapping[str, str],
) -> tuple[str | None, list | None, object | None]:
    session_id = getattr(args, "session", None)
    new_session = bool(getattr(args, "new_session", False))
    if session_id is None and not new_session:
        return None, None, None
    store = SessionStore(environ=environment)
    if new_session and session_id is None:
        metadata = store.create(workspace=workspace, model=model)
        session_id = metadata.id
        print(f"session {session_id}", file=sys.stderr)
        return session_id, None, store
    assert session_id is not None
    try:
        store.get_metadata(session_id)
        if new_session:
            raise ValueError(f'Session "{session_id}" already exists')
        messages = store.load_messages(session_id)
        return session_id, (messages or None), store
    except SessionNotFoundError:
        store.create(session_id=session_id, workspace=workspace, model=model)
        return session_id, None, store
    except SessionCorruptionError as exc:
        raise ValueError(str(exc)) from exc
    except SessionError as exc:
        raise ValueError(str(exc)) from exc


def _invoke_agent(
    args: argparse.Namespace,
    api_config: ApiConfig,
    input_stream: TextIO | None,
    environment: Mapping[str, str] | None = None,
) -> str:
    workspace = resolve_workspace(args.workspace)
    timeout = _approval_timeout(args.approval_timeout)
    approved_tools = _approved_tools(args)
    stream = bool(getattr(args, "stream", False))
    env = environment or os.environ
    session_id, initial_messages, store = _prepare_session(
        args, workspace=workspace, model=api_config.model, environment=env
    )
    client = OpenAI(api_key=api_config.api_key, base_url=api_config.base_url)
    need_collector = stream or store is not None or bool(args.verbose)
    collector = (
        EventCollector(live_sink=_stream_live_sink if stream else None)
        if need_collector
        else None
    )
    if store is not None and session_id is not None and collector is not None:
        store.bind_collector(session_id, collector)

    def on_messages_update(messages: list) -> None:
        if store is not None and session_id is not None:
            store.replace_messages(session_id, messages)

    run_kwargs: dict[str, object] = {
        "working_directory": workspace,
        "verbose": args.verbose,
        "approval_session": _approval_session(
            input_stream, ApprovalMode(args.approval_policy), timeout, approved_tools
        ),
    }
    if collector is not None:
        run_kwargs["event_collector"] = collector
    if stream:
        run_kwargs["stream"] = True
    if initial_messages is not None:
        run_kwargs["initial_messages"] = initial_messages
    if store is not None:
        run_kwargs["on_messages_update"] = on_messages_update
    try:
        final_text = run_agent(
            client,
            args.user_prompt,
            api_config.model,
            **run_kwargs,  # type: ignore[arg-type]
        )
    except APIStatusError as exc:
        raise ValueError(_provider_http_error_message(exc)) from exc
    if stream:
        print(file=sys.stderr)
    if args.verbose and collector is not None:
        print(
            format_run_summary(summarize_run(collector.events)),
            file=sys.stderr,
            flush=True,
        )
    return final_text


def _approval_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as exc:
        raise ValueError(
            "approval timeout must be a positive number of seconds"
        ) from exc
    if not math.isfinite(timeout) or not 0 < timeout <= MAX_APPROVAL_TIMEOUT:
        raise ValueError(
            "approval timeout must be greater than 0 and at most 300 seconds"
        )
    return timeout


def _approved_tools(args: argparse.Namespace) -> frozenset[str]:
    tools = tuple(args.approve_tool)
    mode = ApprovalMode(args.approval_policy)
    if mode is not ApprovalMode.PRE_APPROVED:
        if tools:
            raise ValueError("--approve-tool requires --approval-policy pre-approved")
        return frozenset()
    if not tools:
        raise ValueError("pre-approved policy requires at least one --approve-tool")
    if len(set(tools)) != len(tools):
        raise ValueError("approve tool names must not be duplicated")
    invalid = set(tools) - CONSEQUENTIAL_TOOL_NAMES
    if invalid:
        raise ValueError(
            f"approve tool must be consequential and known: {sorted(invalid)!r}"
        )
    return frozenset(tools)


def _approval_session(
    input_stream: TextIO | None,
    mode: ApprovalMode = ApprovalMode.CONFIRM,
    timeout: float = DEFAULT_APPROVAL_TIMEOUT,
    approved_tools: frozenset[str] = frozenset(),
) -> ApprovalSession:
    source = sys.stdin if input_stream is None else input_stream
    return ApprovalSession(
        TerminalAuthorizer(
            source,
            sys.stderr,
            timeout_seconds=timeout,
            require_tty=input_stream is None,
        ),
        mode=mode,
        approved_tools=approved_tools,
    )


def _run_agent_cli(
    args: argparse.Namespace,
    repository: ProfileRepository | None,
    credential_store: CredentialStore | None,
    environment: Mapping[str, str],
    input_stream: TextIO | None,
) -> int:
    config = _resolved_config(args, repository, credential_store, environment)
    print(_invoke_agent(args, config, input_stream, environment))
    return 0


def _environment_source(
    process_environment: Mapping[str, str],
    dotenv_environment: Mapping[str, str],
) -> Mapping[str, str]:
    if any(key in process_environment for key in TRANSPORT_ENV_KEYS):
        return process_environment
    return dotenv_environment


def _dotenv_environment() -> dict[str, str]:
    values = {
        key: value
        for key, value in dotenv_values(interpolate=False).items()
        if isinstance(value, str) and key in TRANSPORT_ENV_KEYS
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
    if raw_argv and raw_argv[0] == "auth":
        return run_auth_cli(
            raw_argv[1:],
            repository,
            credential_store,
            input_stream=input_stream,
        )
    if raw_argv and raw_argv[0] == "codex":
        return run_codex_cli(raw_argv[1:])
    if raw_argv and raw_argv[0] == "session":
        return run_session_cli(raw_argv[1:], environment=environment)
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
    repository = profile_repository or ProfileRepository(
        default_profile_path(process_environment)
    )
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    environment = _environment_source(process_environment, _dotenv_environment())
    return _dispatch_cli(
        raw_argv, repository, credential_store, secret_prompt, input_stream, environment
    )


if __name__ == "__main__":
    raise SystemExit(main())
