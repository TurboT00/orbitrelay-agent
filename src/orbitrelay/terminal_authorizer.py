# story: e02s04
# story: e02s06

import selectors
from typing import Any, Protocol, TextIO, cast

from .approval_format import format_approval_request
from .approvals import (
    ApprovalDecision,
    ApprovalRequest,
    MAX_APPROVAL_ATTEMPTS,
    ToolCategory,
)


class ApprovalInput(Protocol):
    def readline(self) -> str: ...


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
        requests: tuple[ApprovalRequest, ...],
    ) -> tuple[ApprovalDecision, ...]:
        disabled_tools: set[str] = set()
        decisions = []
        for request in requests:
            decision = self._decision_for(request, disabled_tools)
            if decision.reason == "user_disabled_tool":
                disabled_tools.add(request.tool_name)
            decisions.append(decision)
        return tuple(decisions)

    def _decision_for(
        self, request: ApprovalRequest, disabled_tools: set[str]
    ) -> ApprovalDecision:
        if request.tool_name in disabled_tools:
            return ApprovalDecision.deny(reason="tool_disabled_for_run")
        return self._authorize(request)

    def _authorize(self, request: ApprovalRequest) -> ApprovalDecision:
        if request.category is ToolCategory.READ:
            return ApprovalDecision.approve(reason="read_allowed")
        for _attempt in range(MAX_APPROVAL_ATTEMPTS):
            decision = self._prompt_once(request)
            if decision is not None:
                return decision
        return ApprovalDecision.deny(reason="approval_invalid_input")

    def _prompt_once(self, request: ApprovalRequest) -> ApprovalDecision | None:
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
