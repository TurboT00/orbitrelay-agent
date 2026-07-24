# story: e04s06

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .events import EventType, RunEvent
from .redaction import redact_secrets


@dataclass(frozen=True)
class RunSummary:
    status: str
    response_count: int
    tool_requested: int
    tool_results_ok: int
    tool_results_error: int
    approvals: dict[str, int]
    prompt_tokens: int | None
    completion_tokens: int | None
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        # Numeric usage fields intentionally bypass key-name redaction ("token").
        # String error fields still pass through redact_secrets for safety.
        error_fields = redact_secrets(
            {
                "error_type": self.error_type,
                "error_message": self.error_message,
            }
        )
        if not isinstance(error_fields, dict):
            raise TypeError("summary error fields must redact to a mapping")
        return {
            "status": self.status,
            "response_count": self.response_count,
            "tool_requested": self.tool_requested,
            "tool_results_ok": self.tool_results_ok,
            "tool_results_error": self.tool_results_error,
            "approvals": dict(self.approvals),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "error_type": error_fields.get("error_type"),
            "error_message": error_fields.get("error_message"),
        }


def summarize_run(events: Sequence[RunEvent]) -> RunSummary:
    """Build a secret-free summary from ordered run events."""
    status = "unknown"
    error_type: str | None = None
    error_message: str | None = None
    response_numbers: set[int] = set()
    tool_requested = 0
    tool_ok = 0
    tool_error = 0
    approvals: Counter[str] = Counter()
    prompt_tokens = 0
    completion_tokens = 0
    saw_usage = False

    for event in events:
        data = event.data
        if event.type is EventType.USAGE_REPORTED:
            number = data.get("response_number")
            if isinstance(number, int):
                response_numbers.add(number)
            if data.get("available") is True:
                saw_usage = True
                if isinstance(data.get("prompt_tokens"), int):
                    prompt_tokens += data["prompt_tokens"]
                if isinstance(data.get("completion_tokens"), int):
                    completion_tokens += data["completion_tokens"]
        elif event.type is EventType.MODEL_DELTA:
            number = data.get("response_number")
            if isinstance(number, int):
                response_numbers.add(number)
        elif event.type is EventType.TOOL_REQUESTED:
            tool_requested += 1
        elif event.type is EventType.TOOL_RESULT:
            if data.get("status") == "error":
                tool_error += 1
            else:
                tool_ok += 1
        elif event.type is EventType.APPROVAL_DECIDED:
            disposition = data.get("disposition")
            if isinstance(disposition, str) and disposition:
                approvals[disposition] += 1
        elif event.type is EventType.RUN_ERROR:
            error_type = (
                data.get("error_type")
                if isinstance(data.get("error_type"), str)
                else None
            )
            error_message = (
                data.get("message") if isinstance(data.get("message"), str) else None
            )
        elif event.type is EventType.RUN_COMPLETED:
            completed_status = data.get("status")
            if isinstance(completed_status, str) and completed_status:
                status = completed_status

    return RunSummary(
        status=status,
        response_count=len(response_numbers),
        tool_requested=tool_requested,
        tool_results_ok=tool_ok,
        tool_results_error=tool_error,
        approvals=dict(sorted(approvals.items())),
        prompt_tokens=prompt_tokens if saw_usage else None,
        completion_tokens=completion_tokens if saw_usage else None,
        error_type=error_type,
        error_message=error_message,
    )


def format_run_summary(summary: RunSummary) -> str:
    payload = summary.to_dict()
    approvals = payload.get("approvals") or {}
    approval_text = (
        ",".join(f"{name}={count}" for name, count in approvals.items())
        if approvals
        else "none"
    )
    parts = [
        f"status={payload['status']}",
        f"responses={payload['response_count']}",
        f"tools_requested={payload['tool_requested']}",
        f"tools_ok={payload['tool_results_ok']}",
        f"tools_error={payload['tool_results_error']}",
        f"approvals={approval_text}",
    ]
    if payload.get("prompt_tokens") is not None:
        parts.append(f"prompt_tokens={payload['prompt_tokens']}")
    if payload.get("completion_tokens") is not None:
        parts.append(f"completion_tokens={payload['completion_tokens']}")
    if payload.get("error_type"):
        parts.append(f"error_type={payload['error_type']}")
    return "Run summary: " + " ".join(parts)
