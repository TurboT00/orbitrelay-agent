# story: e03s04
# story: e03s05
# story: e03s06

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .process_bounds import (
    DEFAULT_CODEX_CAPTURE_TIMEOUT_SECONDS,
    DEFAULT_MAX_STDERR_CHARS,
    DEFAULT_MAX_STDOUT_CHARS,
    bound_text,
    run_bounded_subprocess,
)

CODEX_BINARY_NAME = "codex"
CODEX_INSTALL_GUIDANCE = (
    "Install the official Codex CLI separately and ensure `codex` is on PATH. "
    "See https://developers.openai.com/codex/"
)
FORBIDDEN_EXEC_FLAGS = frozenset(
    {
        "--dangerously-bypass-approvals-and-sandbox",
        "--yolo",
    }
)


class CodexBridgeError(RuntimeError):
    """User-facing Codex bridge failure."""

class CodexAuthentication(StrEnum):
    AUTHENTICATED = "authenticated"
    NOT_AUTHENTICATED = "not-authenticated"
    UNKNOWN = "unknown"
    MISSING_CLI = "missing-cli"


@dataclass(frozen=True, slots=True)
class CodexDelegatedStatus:
    """Normalized Codex installation/auth facts with no raw account output."""

    installed: bool
    path: str | None
    version: str | None
    authentication: CodexAuthentication
    detail: str | None = None



@dataclass(frozen=True)
class _CapturedProcess:
    """CompletedProcess-compatible capture with bound metadata."""

    args: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False


Runner = Callable[..., subprocess.CompletedProcess[str] | _CapturedProcess]
Which = Callable[[str], str | None]


@dataclass(frozen=True)
class CodexInstallation:
    available: bool
    path: str | None
    version: str | None
    warning: str | None = None

    def status_lines(self) -> tuple[str, ...]:
        if not self.available:
            lines: tuple[str, ...] = (
                "Codex CLI: unavailable",
                CODEX_INSTALL_GUIDANCE,
            )
            if self.warning:
                lines = (*lines, f"Warning: {self.warning}")
            return lines
        lines = (
            "Codex CLI: available",
            f"Path: {self.path}",
            f"Version: {self.version or 'unknown'}",
        )
        if self.warning:
            lines = (*lines, f"Warning: {self.warning}")
        return lines


@dataclass(frozen=True)
class CodexExecResult:
    exit_code: int
    final_message: str
    version_warning: str | None = None
    argv: tuple[str, ...] = ()
    timed_out: bool = False
    output_truncated: bool = False


def _default_runner(
    argv: Sequence[str],
    *,
    capture_output: bool = False,
    text: bool = True,
    check: bool = False,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str] | _CapturedProcess:
    del check
    del text  # bounded capture always uses text mode when capturing
    if capture_output:
        bounded = run_bounded_subprocess(
            list(argv),
            cwd=cwd,
            env=env,
            timeout=(
                DEFAULT_CODEX_CAPTURE_TIMEOUT_SECONDS
                if timeout is None
                else float(timeout)
            ),
            max_stdout_chars=DEFAULT_MAX_STDOUT_CHARS,
            max_stderr_chars=DEFAULT_MAX_STDERR_CHARS,
        )
        return _CapturedProcess(
            args=list(argv),
            returncode=bounded.returncode,
            stdout=bounded.stdout,
            stderr=bounded.stderr,
            timed_out=bounded.timed_out,
            stdout_truncated=bounded.stdout_truncated,
            stderr_truncated=bounded.stderr_truncated,
        )
    return subprocess.run(
        list(argv),
        capture_output=False,
        text=True,
        cwd=cwd,
        env=None if env is None else dict(env),
        timeout=timeout,
        check=False,
    )


class CodexBridge:
    def __init__(
        self,
        *,
        which: Which | None = None,
        runner: Runner | None = None,
        binary_name: str = CODEX_BINARY_NAME,
    ) -> None:
        self._which = shutil.which if which is None else which
        self._runner = _default_runner if runner is None else runner
        self._binary_name = binary_name

    def detect(self) -> CodexInstallation:
        path = self._which(self._binary_name)
        if path is None:
            return CodexInstallation(available=False, path=None, version=None)
        completed = self._runner(
            [path, "--version"],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            warning = detail or f"`{self._binary_name} --version` failed"
            warning, _ = bound_text(warning, 200)
            return CodexInstallation(
                available=False,
                path=path,
                version=None,
                warning=warning or None,
            )
        version_text = (completed.stdout or completed.stderr or "").strip()
        version = version_text.splitlines()[0].strip() if version_text else None
        return CodexInstallation(available=True, path=path, version=version)

    def require_available(self) -> CodexInstallation:
        installation = self.detect()
        if not installation.available or not installation.path:
            raise CodexBridgeError(
                "Codex CLI is not available. " + CODEX_INSTALL_GUIDANCE
            )
        return installation

    def login(self, *, device_auth: bool = False) -> int:
        installation = self.require_available()
        assert installation.path is not None
        argv = [installation.path, "login"]
        if device_auth:
            argv.append("--device-auth")
        completed = self._runner(argv, capture_output=False, text=True)
        return int(completed.returncode)


    def inspect_readiness(self, *, timeout: float = 10.0) -> CodexDelegatedStatus:
        """Return sanitized installation and login facts for provider status.

        Official CLI stdout/stderr is classified and discarded. Account-bearing
        text never leaves this method.
        """
        installation = self.detect()
        if not installation.available or not installation.path:
            return CodexDelegatedStatus(
                installed=False,
                path=installation.path,
                version=None,
                authentication=CodexAuthentication.MISSING_CLI,
                detail="official Codex CLI is not available",
            )
        try:
            completed = self._runner(
                [installation.path, "login", "status"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return CodexDelegatedStatus(
                installed=True,
                path=installation.path,
                version=installation.version,
                authentication=CodexAuthentication.UNKNOWN,
                detail="login status timed out",
            )
        except OSError:
            return CodexDelegatedStatus(
                installed=True,
                path=installation.path,
                version=installation.version,
                authentication=CodexAuthentication.UNKNOWN,
                detail="login status could not be executed",
            )
        authentication = _normalize_login_status(completed)
        detail = {
            CodexAuthentication.AUTHENTICATED: None,
            CodexAuthentication.NOT_AUTHENTICATED: "run: orbitrelay codex login",
            CodexAuthentication.UNKNOWN: "login status was inconclusive",
            CodexAuthentication.MISSING_CLI: CODEX_INSTALL_GUIDANCE,
        }[authentication]
        return CodexDelegatedStatus(
            installed=True,
            path=installation.path,
            version=installation.version,
            authentication=authentication,
            detail=detail,
        )

    def login_status(self) -> int:
        installation = self.require_available()
        assert installation.path is not None
        completed = self._runner(
            [installation.path, "login", "status"],
            capture_output=True,
            text=True,
        )
        return int(completed.returncode)

    def logout(self) -> int:
        installation = self.require_available()
        assert installation.path is not None
        completed = self._runner(
            [installation.path, "logout"],
            capture_output=False,
            text=True,
        )
        return int(completed.returncode)

    def build_exec_argv(
        self,
        *,
        path: str,
        prompt: str,
        workspace: str,
        output_last_message: str | None = None,
    ) -> list[str]:
        argv = [path, "exec", "--json", "--cd", workspace]
        if output_last_message is not None:
            argv.extend(["--output-last-message", output_last_message])
        argv.append(prompt)
        if any(flag in argv for flag in FORBIDDEN_EXEC_FLAGS):
            raise AssertionError("Codex exec argv must not bypass sandbox approvals")
        return argv

    def exec(
        self,
        prompt: str,
        workspace: str,
        *,
        require_login: bool = True,
    ) -> CodexExecResult:
        installation = self.require_available()
        assert installation.path is not None
        if require_login:
            status = self.login_status()
            if status != 0:
                raise CodexBridgeError(
                    "Codex is not logged in. Run: orbitrelay codex login"
                )
        workspace_path = Path(workspace).expanduser().resolve()
        if not workspace_path.is_dir():
            raise CodexBridgeError(f'Workspace is not a directory: "{workspace_path}"')
        with tempfile.TemporaryDirectory(prefix="orbitrelay-codex-") as temporary:
            final_path = str(Path(temporary) / "final-message.txt")
            argv = self.build_exec_argv(
                path=installation.path,
                prompt=prompt,
                workspace=str(workspace_path),
                output_last_message=final_path,
            )
            completed = self._runner(
                argv,
                capture_output=True,
                text=True,
                timeout=DEFAULT_CODEX_CAPTURE_TIMEOUT_SECONDS,
            )
            timed_out = bool(getattr(completed, "timed_out", False))
            stdout_truncated = bool(getattr(completed, "stdout_truncated", False))
            stderr_truncated = bool(getattr(completed, "stderr_truncated", False))
            stdout, stdout_cut = bound_text(
                completed.stdout or "", DEFAULT_MAX_STDOUT_CHARS
            )
            stderr, stderr_cut = bound_text(
                completed.stderr or "", DEFAULT_MAX_STDERR_CHARS
            )
            stdout_truncated = stdout_truncated or stdout_cut
            stderr_truncated = stderr_truncated or stderr_cut
            final_message = ""
            final_truncated = False
            final_file = Path(final_path)
            if final_file.is_file():
                raw_final = final_file.read_text(encoding="utf-8")
                final_message, final_truncated = bound_text(
                    raw_final, DEFAULT_MAX_STDOUT_CHARS
                )
            elif stdout:
                final_message = _final_message_from_jsonl(stdout)
            if timed_out and not final_message:
                raise CodexBridgeError(
                    f"process timed out after {DEFAULT_CODEX_CAPTURE_TIMEOUT_SECONDS:g} seconds"
                )
            if completed.returncode != 0 and not final_message:
                detail = (stderr or stdout or "").strip()
                if len(detail) > 400:
                    detail = detail[:400]
                raise CodexBridgeError(
                    detail
                    or f"codex exec failed with exit code {completed.returncode}"
                )
            return CodexExecResult(
                exit_code=int(completed.returncode),
                final_message=final_message.strip(),
                version_warning=installation.warning,
                argv=tuple(argv),
                timed_out=timed_out,
                output_truncated=stdout_truncated or stderr_truncated or final_truncated,
            )


def _normalize_login_status(
    completed: subprocess.CompletedProcess[str] | _CapturedProcess,
) -> CodexAuthentication:
    """Map official login status to a coarse auth fact without retaining output."""
    code = int(completed.returncode)
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    text = f"{stdout}\n{stderr}".casefold()
    if code == 0:
        return CodexAuthentication.AUTHENTICATED
    not_auth_markers = (
        "not logged in",
        "not authenticated",
        "please log in",
        "run codex login",
        "no account",
        "logged out",
    )
    if any(marker in text for marker in not_auth_markers):
        return CodexAuthentication.NOT_AUTHENTICATED
    stripped = text.strip()
    if code == 1 and (not stripped or "login" in stripped):
        return CodexAuthentication.NOT_AUTHENTICATED
    if code != 0:
        return CodexAuthentication.UNKNOWN
    return CodexAuthentication.UNKNOWN


def _final_message_from_jsonl(stdout: str) -> str:
    final_message = ""
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event: Any = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if (
            event.get("type") == "item.completed"
            and isinstance(item, dict)
            and item.get("type") == "agent_message"
            and isinstance(item.get("text"), str)
        ):
            final_message = item["text"]
    return final_message
