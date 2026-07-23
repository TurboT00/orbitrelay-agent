# story: e02s01
# story: e02s03
# story: e02s04

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
import selectors
from typing import Any, Protocol, TextIO, cast

from .approval_format import SafeContext, format_approval_request


class ToolCategory(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class ApprovalDisposition(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"


class ApprovalMode(StrEnum):
    CONFIRM = "confirm"
    READ_ONLY = "read-only"
    PRE_APPROVED = "pre-approved"


MAX_APPROVAL_ATTEMPTS = 3


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


BatchAuthorizer = Callable[
    [tuple["ApprovalRequest", ...]], Sequence[ApprovalDecision]
]


class ApprovalInput(Protocol):
    def readline(self) -> str: ...


class ApprovalSession:
    def __init__(
        self,
        authorizer: BatchAuthorizer | None = None,
        *,
        mode: ApprovalMode = ApprovalMode.CONFIRM,
    ) -> None:
        self._authorizer = (
            self._authorize_read_only
            if mode is ApprovalMode.READ_ONLY
            else self._authorize_pre_approved
            if mode is ApprovalMode.PRE_APPROVED
            else authorizer or self._authorize_safe_defaults
        )
        self._disabled_tools: set[str] = set()

    @property
    def disabled_tools(self) -> frozenset[str]:
        return frozenset(self._disabled_tools)

    def authorize(
        self,
        requests: tuple["ApprovalRequest", ...],
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

    @staticmethod
    def _authorize_read_only(
        requests: tuple["ApprovalRequest", ...],
    ) -> tuple[ApprovalDecision, ...]:
        return tuple(
            ApprovalDecision.approve(reason="read_allowed")
            if request.category is ToolCategory.READ
            else ApprovalDecision.deny(reason="read_only_policy")
            for request in requests
        )

    @staticmethod
    def _authorize_pre_approved(
        requests: tuple["ApprovalRequest", ...],
    ) -> tuple[ApprovalDecision, ...]:
        return tuple(
            ApprovalDecision.approve(reason="read_allowed")
            if request.category is ToolCategory.READ
            else ApprovalDecision.deny(reason="pre_approval_unavailable")
            for request in requests
        )


class TerminalAuthorizer:
    def __init__(
        self,
        input_stream: ApprovalInput,
        output_stream: TextIO,
        *,
        timeout_seconds: float = 60.0,
        require_tty: bool = False,
    ) -> None:
        self._input_stream = input_stream
        self._output_stream = output_stream
        self._timeout_seconds = timeout_seconds
        self._require_tty = require_tty

    def __call__(
        self,
        requests: tuple["ApprovalRequest", ...],
    ) -> tuple[ApprovalDecision, ...]:
        disabled_tools: set[str] = set()
        decisions = []
        for request in requests:
            if request.tool_name in disabled_tools:
                decision = ApprovalDecision.deny(reason="tool_disabled_for_run")
            else:
                decision = self._authorize(request)
            if decision.reason == "user_disabled_tool":
                disabled_tools.add(request.tool_name)
            decisions.append(decision)
        return tuple(decisions)

    def _authorize(self, request: "ApprovalRequest") -> ApprovalDecision:
        if request.category is ToolCategory.READ:
            return ApprovalDecision.approve(reason="read_allowed")
        for _attempt in range(MAX_APPROVAL_ATTEMPTS):
            decision = self._prompt_once(request)
            if decision is not None:
                return decision
        return ApprovalDecision.deny(reason="approval_invalid_input")

    def _prompt_once(self, request: "ApprovalRequest") -> ApprovalDecision | None:
        if self._require_tty and not _is_tty(self._input_stream):
            return ApprovalDecision.deny(reason="approval_noninteractive")
        print(
            f"Approve {format_approval_request(request)}? [y/N/d=disable]: ",
            end="",
            file=self._output_stream,
            flush=True,
        )
        try:
            response = self._read_response()
        except TimeoutError:
            return ApprovalDecision.deny(reason="approval_timeout")
        return _decision_for_response(response)

    def _read_response(self) -> str:
        if self._require_tty:
            with selectors.DefaultSelector() as selector:
                selector.register(cast(Any, self._input_stream), selectors.EVENT_READ)
                if not selector.select(self._timeout_seconds):
                    raise TimeoutError
        return self._input_stream.readline()


def _decision_for_response(response: str) -> ApprovalDecision | None:
    normalized = response.strip().lower()
    if normalized in {"y", "yes"}:
        return ApprovalDecision.approve(reason="user_approved")
    if normalized in {"d", "disable"}:
        return ApprovalDecision.disable_tool()
    if response == "":
        return ApprovalDecision.deny(reason="approval_eof")
    if normalized in {"n", "no"}:
        return ApprovalDecision.deny(reason="user_denied")
    return None


def _is_tty(stream: ApprovalInput) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


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
