from typing import Protocol

SafeValue = str | int | tuple[str, ...]
SafeContext = tuple[tuple[str, SafeValue], ...]
MAX_SAFE_VALUE_LENGTH = 200
VERBOSE_CONTEXT_KEYS = frozenset(
    {"target", "file", "content_length", "argument_count", "python", "workspace"}
)


class ApprovalDisplay(Protocol):
    @property
    def tool_name(self) -> str: ...

    @property
    def safe_context(self) -> SafeContext: ...


class ApprovalRecordDisplay(Protocol):
    @property
    def sequence(self) -> int: ...

    @property
    def call_id(self) -> str: ...

    @property
    def tool_name(self) -> str: ...

    @property
    def category(self) -> object: ...

    @property
    def disposition(self) -> object: ...

    @property
    def reason(self) -> str: ...

    @property
    def safe_target(self) -> str | None: ...

    @property
    def argument_count(self) -> int | None: ...


def format_approval_request(request: ApprovalDisplay) -> str:
    context = " ".join(
        f"{key}={_safe_value(value)}" for key, value in request.safe_context
    )
    if not context:
        return request.tool_name
    return f"{request.tool_name} ({context})"


def format_prepared_call(request: ApprovalDisplay) -> str:
    context = " ".join(
        f"{key}={_safe_value(value)}"
        for key, value in request.safe_context
        if key in VERBOSE_CONTEXT_KEYS
    )
    if not context:
        return request.tool_name
    return f"{request.tool_name} ({context})"


def format_approval_record(record: ApprovalRecordDisplay) -> str:
    fields = [
        f"seq={record.sequence}",
        f"call_id={_safe_token(record.call_id)}",
        f"tool={_safe_token(record.tool_name)}",
        f"category={_safe_token(str(record.category))}",
        f"disposition={_safe_token(str(record.disposition))}",
        f"reason={_safe_token(record.reason)}",
    ]
    if record.safe_target is not None:
        fields.append(f"target={_safe_token(record.safe_target)}")
    if record.argument_count is not None:
        fields.append(f"argument_count={record.argument_count}")
    return "approval " + " ".join(fields)


def _safe_token(value: str) -> str:
    if value.isascii() and value.isprintable() and " " not in value:
        if len(value) <= MAX_SAFE_VALUE_LENGTH:
            return value
        return f"{value[:MAX_SAFE_VALUE_LENGTH]}...<truncated>"
    return _safe_value(value)


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
