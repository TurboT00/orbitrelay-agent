from dataclasses import dataclass
from enum import StrEnum


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
