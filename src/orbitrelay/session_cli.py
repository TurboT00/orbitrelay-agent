# story: e04s04

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from typing import TextIO

from .sessions import SessionError, SessionNotFoundError, SessionStore


def parse_session_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="orbitrelay session")
    actions = parser.add_subparsers(dest="session_action", required=True)
    actions.add_parser("list", help="List local sessions")
    show = actions.add_parser("show", help="Show secret-free session metadata")
    show.add_argument("id")
    delete = actions.add_parser("delete", help="Delete one session")
    delete.add_argument("id")
    delete_all = actions.add_parser(
        "delete-all", help="Delete all sessions (requires --confirm)"
    )
    delete_all.add_argument(
        "--confirm",
        action="store_true",
        help="Required confirmation flag for delete-all",
    )
    return parser.parse_args(argv)


def run_session_cli(
    argv: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
    store: SessionStore | None = None,
    output: TextIO | None = None,
) -> int:
    args = parse_session_args(argv)
    active = store or SessionStore(environ=environment)
    stream = sys.stdout if output is None else output
    error_stream = sys.stderr if output is None else output
    try:
        if args.session_action == "list":
            sessions = active.list_sessions()
            if not sessions:
                print("No sessions stored.", file=stream)
                return 0
            for metadata in sessions:
                busy = "yes" if active.is_session_active(metadata.id) else "no"
                sensitive = "yes" if metadata.sensitive else "no"
                print(
                    f"{metadata.id} updated={metadata.updated_at}"
                    f" model={metadata.model or '-'}"
                    f" workspace={metadata.workspace or '-'}"
                    f" active={busy}"
                    f" sensitive={sensitive}",
                    file=stream,
                )
            return 0
        if args.session_action == "show":
            metadata = active.get_metadata(args.id)
            payload = metadata.to_dict()
            payload["active"] = active.is_session_active(args.id)
            # include message count only, not contents dump with secrets risk
            messages = active.load_messages(args.id)
            payload["message_count"] = len(messages)
            print(json.dumps(payload, indent=2, sort_keys=True), file=stream)
            return 0
        if args.session_action == "delete":
            active.delete(args.id)
            print(f'Deleted session "{args.id}".', file=stream)
            return 0
        if args.session_action == "delete-all":
            if not args.confirm:
                raise SessionError("delete-all requires --confirm")
            count = active.delete_all()
            print(f"Deleted {count} session(s).", file=stream)
            return 0
    except SessionNotFoundError as exc:
        print(str(exc), file=error_stream)
        return 1
    except SessionError as exc:
        print(str(exc), file=error_stream)
        return 1
    raise AssertionError(f"Unknown session action: {args.session_action}")
