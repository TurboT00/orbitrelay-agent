from dataclasses import dataclass
from enum import StrEnum
from collections.abc import Callable, Sequence


class ToolCategory(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class ApprovalDisposition(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"


SafeContext = tuple[tuple[str, str | int], ...]


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    disposition: ApprovalDisposition
    reason: str

    @property
    def approved(self) -> bool:
        return self.disposition is ApprovalDisposition.APPROVED

    @classmethod
    def approve(cls, *, reason: str) -> "ApprovalDecision":
        return cls(disposition=ApprovalDisposition.APPROVED, reason=reason)

    @classmethod
    def deny(cls, *, reason: str) -> "ApprovalDecision":
        return cls(disposition=ApprovalDisposition.DENIED, reason=reason)


BatchAuthorizer = Callable[
    [tuple["ApprovalRequest", ...]], Sequence[ApprovalDecision]
]


class ApprovalSession:
    def __init__(self, authorizer: BatchAuthorizer | None = None) -> None:
        self._authorizer = authorizer or self._authorize_safe_defaults

    def authorize(
        self,
        requests: tuple["ApprovalRequest", ...],
    ) -> tuple[ApprovalDecision, ...]:
        decisions = tuple(self._authorizer(requests))
        if len(decisions) != len(requests):
            raise RuntimeError("Approval session returned the wrong decision count")
        if not all(isinstance(decision, ApprovalDecision) for decision in decisions):
            raise RuntimeError("Approval session returned an invalid decision")
        return decisions

    @staticmethod
    def _authorize_safe_defaults(
        requests: tuple["ApprovalRequest", ...],
    ) -> tuple[ApprovalDecision, ...]:
        return tuple(
            ApprovalDecision.approve(reason="read_allowed")
            if request.category is ToolCategory.READ
            else ApprovalDecision.deny(reason="approval_unavailable")
            for request in requests
        )


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    call_id: str
    tool_name: str
    category: ToolCategory
    safe_context: SafeContext

    @classmethod
    def for_write(
        cls,
        *,
        call_id: str,
        target: str,
        content_length: int,
    ) -> "ApprovalRequest":
        return cls(
            call_id=call_id,
            tool_name="write_file",
            category=ToolCategory.WRITE,
            safe_context=(
                ("target", target),
                ("content_length", content_length),
            ),
        )
