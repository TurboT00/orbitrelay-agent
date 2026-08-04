"""Bounded subprocess capture shared by local tools and Codex bridge.

Drains stdout/stderr fully to avoid pipe deadlocks while retaining only a
documented character bound. Discarded content is never returned to callers.
"""

from __future__ import annotations

import contextlib
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import IO

DEFAULT_MAX_STDOUT_CHARS = 32_000
DEFAULT_MAX_STDERR_CHARS = 16_000
DEFAULT_PROCESS_TIMEOUT_SECONDS = 30.0
DEFAULT_CODEX_CAPTURE_TIMEOUT_SECONDS = 120.0
_READ_CHUNK = 4_096


@dataclass(frozen=True, slots=True)
class BoundedProcessResult:
    """Process outcome with truncation/timeout metadata only."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool
    duration_seconds: float
    timeout_seconds: float

    def format_tool_output(self) -> str:
        """Human-readable tool result without discarded content."""
        parts: list[str] = []
        if self.timed_out:
            parts.append(
                f"Error: process timed out after {self.timeout_seconds:g} seconds"
            )
        elif self.returncode != 0:
            parts.append(f"Process exited with code {self.returncode}")
        if self.stdout:
            parts.append(f"STDOUT:\n{self.stdout}")
        if self.stderr:
            parts.append(f"STDERR:\n{self.stderr}")
        if not self.stdout and not self.stderr and not self.timed_out:
            parts.append("No output produced")
        if self.stdout_truncated:
            parts.append(
                f"[stdout truncated: retained {len(self.stdout)} chars; "
                "discarded content omitted]"
            )
        if self.stderr_truncated:
            parts.append(
                f"[stderr truncated: retained {len(self.stderr)} chars; "
                "discarded content omitted]"
            )
        return "\n".join(parts)

    def safe_error_detail(self, *, max_chars: int = 400) -> str:
        """Bounded detail for bridge errors; never includes discarded tails."""
        if self.timed_out:
            return f"process timed out after {self.timeout_seconds:g} seconds"
        text = (self.stderr or self.stdout or "").strip()
        if not text:
            return f"process failed with exit code {self.returncode}"
        if len(text) > max_chars:
            return text[:max_chars]
        return text


def bound_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Retain a prefix of text and report whether truncation occurred."""
    if max_chars < 0:
        raise ValueError("max_chars must be non-negative")
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _drain_stream(
    stream: IO[str] | None,
    max_chars: int,
    sink: list[object],
) -> None:
    """Read stream to EOF, retaining only max_chars while discarding the rest."""
    if stream is None:
        sink[:] = ["", False]
        return
    chunks: list[str] = []
    retained = 0
    truncated = False
    try:
        while True:
            block = stream.read(_READ_CHUNK)
            if not block:
                break
            if retained < max_chars:
                room = max_chars - retained
                chunks.append(block[:room])
                retained += min(len(block), room)
                if len(block) > room:
                    truncated = True
            else:
                truncated = True
    finally:
        sink[:] = ["".join(chunks), truncated]


def run_bounded_subprocess(
    argv: Sequence[str],
    *,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_PROCESS_TIMEOUT_SECONDS,
    max_stdout_chars: int = DEFAULT_MAX_STDOUT_CHARS,
    max_stderr_chars: int = DEFAULT_MAX_STDERR_CHARS,
    popen: Callable[..., subprocess.Popen[str]] | None = None,
) -> BoundedProcessResult:
    """Run a process with bounded retained output and hard timeout."""
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if max_stdout_chars < 0 or max_stderr_chars < 0:
        raise ValueError("output bounds must be non-negative")
    starter = subprocess.Popen if popen is None else popen
    started = time.monotonic()
    process = starter(
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=None if env is None else dict(env),
    )
    stdout_sink: list[object] = []
    stderr_sink: list[object] = []
    stdout_thread = threading.Thread(
        target=_drain_stream,
        args=(process.stdout, max_stdout_chars, stdout_sink),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain_stream,
        args=(process.stderr, max_stderr_chars, stderr_sink),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)
    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    stdout = str(stdout_sink[0]) if stdout_sink else ""
    stdout_truncated = bool(stdout_sink[1]) if len(stdout_sink) > 1 else False
    stderr = str(stderr_sink[0]) if stderr_sink else ""
    stderr_truncated = bool(stderr_sink[1]) if len(stderr_sink) > 1 else False
    code = process.returncode
    if code is None:
        code = -1 if timed_out else 0
    duration = time.monotonic() - started
    return BoundedProcessResult(
        returncode=int(code),
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        duration_seconds=duration,
        timeout_seconds=float(timeout),
    )


def bound_completed_process(
    completed: subprocess.CompletedProcess[str],
    *,
    max_stdout_chars: int = DEFAULT_MAX_STDOUT_CHARS,
    max_stderr_chars: int = DEFAULT_MAX_STDERR_CHARS,
    timed_out: bool = False,
    timeout_seconds: float = DEFAULT_PROCESS_TIMEOUT_SECONDS,
    duration_seconds: float = 0.0,
) -> BoundedProcessResult:
    """Apply bounds to an already-captured CompletedProcess (tests/injection)."""
    stdout, stdout_truncated = bound_text(completed.stdout or "", max_stdout_chars)
    stderr, stderr_truncated = bound_text(completed.stderr or "", max_stderr_chars)
    return BoundedProcessResult(
        returncode=int(completed.returncode),
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        duration_seconds=duration_seconds,
        timeout_seconds=float(timeout_seconds),
    )
