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
from pathlib import Path
from typing import Any


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


Runner = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


@dataclass(frozen=True)
class CodexInstallation:
    available: bool
    path: str | None
    version: str | None
    warning: str | None = None

    def status_lines(self) -> tuple[str, ...]:
        if not self.available:
            lines = [
                "Codex CLI: unavailable",
                CODEX_INSTALL_GUIDANCE,
            ]
            if self.warning:
                lines = (*lines, f"Warning: {self.warning}")
            return lines
        lines = [
            "Codex CLI: available",
            f"Path: {self.path}",
            f"Version: {self.version or 'unknown'}",
        ]
        if self.warning:
            lines = (*lines, f"Warning: {self.warning}")
        return lines


@dataclass(frozen=True)
class CodexExecResult:
    exit_code: int
    final_message: str
    version_warning: str | None = None
    argv: tuple[str, ...] = ()


def _default_runner(
    argv: Sequence[str],
    *,
    capture_output: bool = False,
    text: bool = True,
    check: bool = False,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    del check
    return subprocess.run(
        list(argv),
        capture_output=capture_output,
        text=text,
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
            return CodexInstallation(
                available=False,
                path=path,
                version=None,
                warning=warning[:200],
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
            completed = self._runner(argv, capture_output=True, text=True)
            final_message = ""
            final_file = Path(final_path)
            if final_file.is_file():
                final_message = final_file.read_text(encoding="utf-8")
            elif completed.stdout:
                final_message = _final_message_from_jsonl(completed.stdout)
            if completed.returncode != 0 and not final_message:
                detail = (completed.stderr or completed.stdout or "").strip()
                raise CodexBridgeError(
                    detail or f"codex exec failed with exit code {completed.returncode}"
                )
            return CodexExecResult(
                exit_code=int(completed.returncode),
                final_message=final_message.strip(),
                version_warning=installation.warning,
                argv=tuple(argv),
            )


def _final_message_from_jsonl(stdout: str) -> str:
    messages: list[str] = []
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
        if event.get("type") == "item.completed" and isinstance(item, dict):
            if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                messages.append(item["text"])
    return messages[-1] if messages else ""
