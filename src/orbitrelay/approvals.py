# story: e02s01
# story: e02s03
# story: e02s04
# story: e02s05
# story: e02s06

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from .approval_format import SafeContext, SafeValue

MAX_APPROVAL_ATTEMPTS = 3
DISABLED_REASONS = frozenset({"user_disabled_tool", "tool_disabled_for_run"})


class ToolCategory(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class ApprovalDisposition(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"


class RecordDisposition(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    DISABLED = "disabled"


class ApprovalMode(StrEnum):
    CONFIRM = "confirm"
    READ_ONLY = "read-only"
    PRE_APPROVED = "pre-approved"


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

    @classmethod
    def disable_tool(cls) -> "ApprovalDecision":
        return cls.deny(reason="user_disabled_tool")


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    sequence: int
    call_id: str
    tool_name: str
    category: ToolCategory
    disposition: RecordDisposition
    reason: str
    safe_target: str | None
    argument_count: int | None


BatchAuthorizer = Callable[
    [tuple["ApprovalRequest", ...]], Sequence[ApprovalDecision]
]


class ApprovalSession:
    def __init__(
        self,
        authorizer: BatchAuthorizer | None = None,
        *,
        mode: ApprovalMode = ApprovalMode.CONFIRM,
        approved_tools: frozenset[str] = frozenset(),
    ) -> None:
        self._disabled_tools: set[str] = set()
        self._approved_tools = approved_tools
        self._records: list[ApprovalRecord] = []
        self._authorizer = (
            _authorize_read_only
            if mode is ApprovalMode.READ_ONLY
            else self._authorize_pre_approved
            if mode is ApprovalMode.PRE_APPROVED
            else authorizer or _authorize_safe_defaults
        )

    @property
    def disabled_tools(self) -> frozenset[str]:
        return frozenset(self._disabled_tools)

    @property
    def records(self) -> tuple[ApprovalRecord, ...]:
        return tuple(self._records)

    def authorize(
        self,
        requests: tuple["ApprovalRequest", ...],
    ) -> tuple[ApprovalDecision, ...]:
        outcomes = self._decisions_for(requests)
        for request, decision in zip(requests, outcomes, strict=True):
            self._records.append(_record_for(len(self._records) + 1, request, decision))
        return outcomes

    def _decisions_for(
        self, requests: tuple["ApprovalRequest", ...]
    ) -> tuple[ApprovalDecision, ...]:
        pending_indexes = tuple(
            index
            for index, request in enumerate(requests)
            if request.tool_name not in self._disabled_tools
        )
        pending = tuple(requests[index] for index in pending_indexes)
        decisions = tuple(self._authorizer(pending)) if pending else ()
        self._validate_decisions(pending, decisions)
        candidates = dict(zip(pending_indexes, decisions, strict=True))
        return tuple(
            self._apply_policy(request, candidates.get(index))
            for index, request in enumerate(requests)
        )

    @staticmethod
    def _validate_decisions(
        requests: tuple["ApprovalRequest", ...],
        decisions: tuple[ApprovalDecision, ...],
    ) -> None:
        if len(decisions) != len(requests):
            raise RuntimeError("Approval session returned the wrong decision count")
        if not all(isinstance(decision, ApprovalDecision) for decision in decisions):
            raise RuntimeError("Approval session returned an invalid decision")

    def _apply_policy(
        self,
        request: "ApprovalRequest",
        candidate: ApprovalDecision | None,
    ) -> ApprovalDecision:
        if request.tool_name in self._disabled_tools:
            return ApprovalDecision.deny(reason="tool_disabled_for_run")
        if candidate is None:
            raise AssertionError("Enabled approval request did not have a decision")
        if candidate.reason == "user_disabled_tool":
            self._disabled_tools.add(request.tool_name)
        return candidate

    def _authorize_pre_approved(
        self,
        requests: tuple["ApprovalRequest", ...],
    ) -> tuple[ApprovalDecision, ...]:
        return tuple(
            ApprovalDecision.approve(reason="read_allowed")
            if request.category is ToolCategory.READ
            else ApprovalDecision.approve(reason="explicit_preapproval")
            if request.tool_name in self._approved_tools
            else ApprovalDecision.deny(reason="tool_not_preapproved")
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

    @classmethod
    def for_execution(
        cls,
        *,
        call_id: str,
        workspace: str,
        target: str,
        arguments: Sequence[str],
    ) -> "ApprovalRequest":
        return cls(
            call_id=call_id,
            tool_name="run_python_file",
            category=ToolCategory.EXECUTE,
            safe_context=(
                ("python", "current-interpreter"),
                ("workspace", workspace),
                ("file", target),
                ("arguments", tuple(arguments)),
                ("argument_count", len(arguments)),
            ),
        )


def _authorize_safe_defaults(
    requests: tuple[ApprovalRequest, ...],
) -> tuple[ApprovalDecision, ...]:
    return tuple(
        ApprovalDecision.approve(reason="read_allowed")
        if request.category is ToolCategory.READ
        else ApprovalDecision.deny(reason="approval_unavailable")
        for request in requests
    )


def _authorize_read_only(
    requests: tuple[ApprovalRequest, ...],
) -> tuple[ApprovalDecision, ...]:
    return tuple(
        ApprovalDecision.approve(reason="read_allowed")
        if request.category is ToolCategory.READ
        else ApprovalDecision.deny(reason="read_only_policy")
        for request in requests
    )


def _record_for(
    sequence: int,
    request: ApprovalRequest,
    decision: ApprovalDecision,
) -> ApprovalRecord:
    return ApprovalRecord(
        sequence=sequence,
        call_id=request.call_id,
        tool_name=request.tool_name,
        category=request.category,
        disposition=_record_disposition(decision),
        reason=decision.reason,
        safe_target=_context_str(request.safe_context, "target", "file"),
        argument_count=_context_int(request.safe_context, "argument_count"),
    )


def _record_disposition(decision: ApprovalDecision) -> RecordDisposition:
    if decision.approved:
        return RecordDisposition.ALLOWED
    if decision.reason in DISABLED_REASONS:
        return RecordDisposition.DISABLED
    return RecordDisposition.DENIED


def _context_value(context: SafeContext, *keys: str) -> SafeValue | None:
    values = dict(context)
    for key in keys:
        if key in values:
            return values[key]
    return None


def _context_str(context: SafeContext, *keys: str) -> str | None:
    value = _context_value(context, *keys)
    return value if isinstance(value, str) else None


def _context_int(context: SafeContext, *keys: str) -> int | None:
    value = _context_value(context, *keys)
    return value if isinstance(value, int) else None


def __getattr__(name: str) -> object:
    if name == "TerminalAuthorizer":
        from .terminal_authorizer import TerminalAuthorizer

        return TerminalAuthorizer
    if name == "format_approval_request":
        from .approval_format import format_approval_request

        return format_approval_request
    raise AttributeError(name)
