"""Explicit provider verification: probe outcomes without retaining content."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
)


class VerificationOutcome(StrEnum):
    OK = "ok"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class VerificationEvidence:
    """Secret-free historical verification metadata only."""

    checked_at: float
    outcome: VerificationOutcome
    route: str
    model: str
    historical: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "checked_at": self.checked_at,
            "outcome": self.outcome.value,
            "route": self.route,
            "model": self.model,
            "historical": True,
        }

    @classmethod
    def from_dict(cls, value: object) -> VerificationEvidence:
        if not isinstance(value, dict):
            raise ValueError("verification evidence must be an object")
        outcome_raw = value.get("outcome")
        route = value.get("route")
        model = value.get("model")
        checked_at = value.get("checked_at")
        if not isinstance(outcome_raw, str):
            raise ValueError("verification outcome is required")
        if not isinstance(route, str) or not route.strip():
            raise ValueError("verification route is required")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("verification model is required")
        if not isinstance(checked_at, (int, float)):
            raise ValueError("verification checked_at must be a number")
        return cls(
            checked_at=float(checked_at),
            outcome=VerificationOutcome(outcome_raw),
            route=route.strip(),
            model=model.strip(),
            historical=True,
        )

    def lines(self, *, prefix: str = "last_verification") -> tuple[str, ...]:
        return (
            f"{prefix}: historical",
            f"{prefix}_at: {self.checked_at}",
            f"{prefix}_outcome: {self.outcome.value}",
            f"{prefix}_route: {self.route}",
            f"{prefix}_model: {self.model}",
        )


class ProviderProbe(Protocol):
    def __call__(self, *, base_url: str, api_key: str, model: str) -> None:
        """Perform a minimal authenticated probe; raise on failure."""


def default_openai_compatible_probe(
    *, base_url: str, api_key: str, model: str, timeout: float = 15.0
) -> None:
    """Minimal authenticated OpenAI-compatible call; discard response body."""
    del model  # model is retained only as historical metadata, not required for list
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    # Consume the page iterator without retaining model identifiers or payloads.
    for _ in client.models.list():
        break


def classify_probe_error(exc: BaseException) -> tuple[VerificationOutcome, str]:
    """Map probe failures to sanitized outcomes without exception text."""
    if isinstance(exc, APITimeoutError):
        return VerificationOutcome.TIMEOUT, "provider probe timed out"
    if isinstance(exc, APIConnectionError):
        return VerificationOutcome.FAILED, "provider probe could not connect"
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        if isinstance(status, int):
            return (
                VerificationOutcome.FAILED,
                f"provider probe failed (HTTP {status})",
            )
        return VerificationOutcome.FAILED, "provider probe failed"
    return VerificationOutcome.FAILED, "provider probe failed"


Clock = Callable[[], float]
