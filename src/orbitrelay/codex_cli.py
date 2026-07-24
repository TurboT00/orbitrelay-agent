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

    actions.add_parser("logout", help="Delegate logout to official codex logout")

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
            result = active.exec(args.prompt, workspace)
            if result.version_warning:
                print(f"Warning: {result.version_warning}", file=error_stream)
            if result.final_message:
                print(result.final_message, file=stream)
            return result.exit_code
    except CodexBridgeError as exc:
        print(str(exc), file=error_stream)
        return 1
    raise AssertionError(f"Unknown codex action: {args.codex_action}")
