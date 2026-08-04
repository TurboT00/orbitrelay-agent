# story: e04s04
# story: e08s03

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from typing import TextIO

from .sessions import (
    SessionError,
    SessionHealth,
    SessionNotFoundError,
    SessionStore,
    SessionSummary,
)


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
            for summary in sessions:
                print(_format_list_line(summary, active), file=stream)
            return 0
        if args.session_action == "show":
            summary = active.inspect_session(args.id)
            payload = summary.to_dict()
            payload["active"] = active.is_session_active(args.id)
            if summary.health is SessionHealth.OK:
                # Count only; never dump message content.
                payload["message_count"] = len(active.load_messages(args.id))
            print(json.dumps(payload, indent=2, sort_keys=True), file=stream)
            return 0 if summary.health is SessionHealth.OK else 1
        if args.session_action == "delete":
            active.delete(args.id)
            print(f'Deleted session "{args.id}".', file=stream)
            return 0
        if args.session_action == "delete-all":
            if not args.confirm:
                raise SessionError("delete-all requires --confirm")
            result = active.delete_all()
            for session_id in result.deleted:
                print(f'Deleted session "{session_id}".', file=stream)
            for session_id, reason in result.failed:
                print(f'Failed session "{session_id}": {reason}', file=error_stream)
            print(
                f"Deleted {result.deleted_count} session(s)"
                + (
                    f"; {len(result.failed)} failed."
                    if result.failed
                    else "."
                ),
                file=stream if result.complete else error_stream,
            )
            return 0 if result.complete else 1
    except SessionNotFoundError as exc:
        print(str(exc), file=error_stream)
        return 1
    except SessionError as exc:
        print(str(exc), file=error_stream)
        return 1
    raise AssertionError(f"Unknown session action: {args.session_action}")


def _format_list_line(summary: SessionSummary, store: SessionStore) -> str:
    busy = "yes" if store.is_session_active(summary.id) else "no"
    sensitive = "yes" if summary.sensitive else "no"
    updated = "-" if summary.updated_at is None else str(summary.updated_at)
    model = summary.model or "-"
    workspace = summary.workspace or "-"
    line = (
        f"{summary.id} state={summary.health.value}"
        f" updated={updated}"
        f" model={model}"
        f" workspace={workspace}"
        f" active={busy}"
        f" sensitive={sensitive}"
    )
    if summary.diagnostic:
        line += f" diagnostic={summary.diagnostic}"
    return line
