from typing import Protocol

SafeValue = str | int | tuple[str, ...]
SafeContext = tuple[tuple[str, SafeValue], ...]
MAX_SAFE_VALUE_LENGTH = 200


class ApprovalDisplay(Protocol):
    @property
    def tool_name(self) -> str: ...

    @property
    def safe_context(self) -> SafeContext: ...


def format_approval_request(request: ApprovalDisplay) -> str:
    context = " ".join(
        f"{key}={_safe_value(value)}" for key, value in request.safe_context
    )
    if not context:
        return request.tool_name
    return f"{request.tool_name} ({context})"


def _safe_value(value: SafeValue) -> str:
    if isinstance(value, int):
        visible = str(value)
    elif isinstance(value, tuple):
        visible = f"[{', '.join(ascii(item) for item in value)}]"
    else:
        visible = ascii(value)
    if len(visible) <= MAX_SAFE_VALUE_LENGTH:
        return visible
    return f"{visible[:MAX_SAFE_VALUE_LENGTH]}...<truncated>"
