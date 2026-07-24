# story: e03s02

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from .credentials import CredentialStore
from .profile_store import ProfileRepository
from .supergrok_oauth import (
    SuperGrokAuthService,
    SuperGrokOAuthClient,
    SuperGrokOAuthError,
    UrlLibTransport,
)


def parse_auth_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="orbitrelay auth")
    parser.add_argument(
        "provider",
        choices=("supergrok",),
        help="Auth provider (currently: supergrok)",
    )
    parser.add_argument(
        "action",
        choices=("login", "status", "logout"),
        help="login, status, or logout",
    )
    return parser.parse_args(argv)


def run_auth_cli(
    argv: Sequence[str],
    repository: ProfileRepository,
    credential_store: CredentialStore | None,
    *,
    client: SuperGrokOAuthClient | None = None,
    output: TextIO | None = None,
    input_stream: TextIO | None = None,
) -> int:
    del input_stream  # reserved for future browser/device prompts
    args = parse_auth_args(argv)
    if args.provider != "supergrok":
        raise AssertionError(f"Unsupported auth provider: {args.provider}")
    service = SuperGrokAuthService(
        repository,
        credential_store,
        client or SuperGrokOAuthClient(UrlLibTransport()),
        output=sys.stderr if output is None else output,
    )
    stream = sys.stderr if output is None else output
    try:
        if args.action == "login":
            status = service.login()
        elif args.action == "status":
            status = service.status()
        else:
            status = service.logout()
    except SuperGrokOAuthError as exc:
        print(str(exc), file=stream)
        return 1
    print(status.message())
    if args.action == "logout":
        return 0
    if args.action == "status":
        return 0 if status.authenticated and not status.quarantined else 1
    return 0 if status.authenticated else 1
