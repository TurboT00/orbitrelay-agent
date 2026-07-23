# Threat Model — e02 Tool Approval Policies

## Assets

- Workspace files and directories.
- Local process execution authority.
- Provider credentials and environment secrets.
- User intent, run policy, and approval decisions.
- Tool-call correlation and decision records.

## Trust boundaries

1. Model-generated tool names and JSON arguments are untrusted.
2. The selected workspace and CLI policy are trusted user inputs.
3. Approval input is trusted only when received from the configured user-facing
   approval source; model output can never satisfy it.
4. Filesystem mutation and subprocess creation are consequential side-effect
   boundaries.
5. Verbose terminal output and run-local records are disclosure boundaries.

## Threats and required mitigations

| Threat | Severity | Required mitigation |
|---|---|---|
| Side effect begins before consent | Critical | Prepare and authorize the complete batch before executing any consequential call; tests assert zero write/process effects on denial, EOF, timeout, and malformed input. |
| Model selects or changes policy | Critical | Construct policy only from explicit CLI values and inject it into the run; ignore environment, workspace, and model attempts to override it. |
| Pre-approved mode becomes blanket bypass | Critical | Require an explicit allowlist of consequential tool names and continue all workspace, symlink, and argument validation. |
| Invalid later call follows an earlier side effect | High | Preserve existing structural prevalidation of every call before any prompt or execution. |
| Mixed batch loses call correlation | High | Return exactly one ordered tool result for every validated call, including stable structured approval failures. |
| Prompt text spoofs the terminal | High | Escape control characters, bound preview size, and use fixed trusted prompt labels for model-controlled paths and arguments. |
| Approval waits forever unattended | High | Detect unavailable/noninteractive input and apply the configured timeout; every failure defaults to deny. |
| Repeated denied calls harass the user | Medium | Support run-scoped tool disable and automatically deny later calls without reprompting. |
| Decision logs expose file content, arguments, or credentials | High | Never record write content or raw process arguments; record only call ID, tool, disposition, safe target, argument count, and reason; recursively redact diagnostic mappings. |
| Verbose output corrupts normal command output | Medium | Emit sanitized decision events to stderr only under `--verbose`. |

## Residual risks

- A user can explicitly pre-approve a dangerous built-in tool. The CLI must make
  the allowlist visible, but intentional authorization remains user risk.
- The interactive execution prompt displays command arguments so the user can
  make an informed decision. Those arguments may contain sensitive model output;
  they are terminal-visible but never persisted in decision records.
- P2 secures OrbitRelay's built-in dispatch path; direct invocation of Python
  library handler functions by another local program remains outside the CLI
  consent contract.

## Security verification focus

- Mixed batches, duplicate calls, malformed JSON, and invalid arguments.
- Denied write/process side-effect sentinels.
- EOF, timeout, closed stdin, and noninteractive confirmation.
- ANSI/control-character and oversized preview handling.
- Pre-approved allowlist with path/symlink escapes.
- Decision records and verbose stderr with credential-like fixtures.
