# story: e03s04
# story: e03s05
# story: e03s06

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from .codex_bridge import CodexBridge, CodexBridgeError
from .connection_service import ConnectionService, LifecyclePart
from .credentials import CredentialStore
from .profile_store import ProfileRepository, default_profile_path


def parse_codex_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="orbitrelay codex")
    actions = parser.add_subparsers(dest="codex_action", required=True)

    actions.add_parser("status", help="Detect Codex CLI availability and version")

    login = actions.add_parser("login", help="Delegate login to official codex login")
    login.add_argument(
        "--device-auth",
        action="store_true",
        help="Use codex login --device-auth",
    )

    logout = actions.add_parser(
        "logout", help="Delegate logout to official codex logout"
    )
    logout.add_argument(
        "--disconnect",
        action="store_true",
        help=(
            "After successful official logout, also remove OrbitRelay codex "
            "metadata (logout-first; no automatic provider fallback)"
        ),
    )

    execute = actions.add_parser(
        "exec", help="Run a noninteractive codex exec alternate path"
    )
    execute.add_argument("prompt", help="Task prompt for codex exec")
    execute.add_argument(
        "--workspace",
        default=None,
        help="Workspace directory passed to codex exec --cd (default: cwd)",
    )
    return parser.parse_args(argv)


def run_codex_cli(
    argv: Sequence[str],
    *,
    bridge: CodexBridge | None = None,
    output: TextIO | None = None,
    profile_repository: ProfileRepository | None = None,
    credential_store: CredentialStore | None = None,
) -> int:
    args = parse_codex_args(argv)
    active = bridge or CodexBridge()
    stream = sys.stdout if output is None else output
    error_stream = sys.stderr if output is None else output
    try:
        if args.codex_action == "status":
            installation = active.detect()
            for line in installation.status_lines():
                print(line, file=stream)
            return 0 if installation.available else 1
        if args.codex_action == "login":
            code = active.login(device_auth=bool(args.device_auth))
            if code == 0:
                print("Codex login completed.", file=stream)
            return code
        if args.codex_action == "logout":
            if bool(getattr(args, "disconnect", False)):
                service = ConnectionService(
                    profile_repository or ProfileRepository(default_profile_path()),
                    credential_store,
                    codex_bridge=active,
                )
                lifecycle = service.logout_and_disconnect_codex()
                for line in lifecycle.lines():
                    print(line, file=stream)
                if lifecycle.logout is LifecyclePart.COMPLETED:
                    print("Codex logout completed.", file=stream)
                if lifecycle.complete:
                    return 0
                return 1
            code = active.logout()
            if code == 0:
                print("Codex logout completed.", file=stream)
            return code
        if args.codex_action == "exec":
            workspace = (
                str(Path.cwd())
                if args.workspace is None
                else str(Path(args.workspace).expanduser())
            )
            execution = active.exec(args.prompt, workspace)
            if execution.version_warning:
                print(f"Warning: {execution.version_warning}", file=error_stream)
            if execution.final_message:
                print(execution.final_message, file=stream)
            return execution.exit_code
    except CodexBridgeError as exc:
        print(str(exc), file=error_stream)
        return 1
    raise AssertionError(f"Unknown codex action: {args.codex_action}")
