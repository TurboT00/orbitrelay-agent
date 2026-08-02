# Code Audit — e02s04 Read-Only and Unattended Safety

- Mode: `audit-code --gate`
- Story baseline: `86488c5`
- Merge base: `8bcefba610a4fd1c66c47e665247325b04ecfdb2`
- Result: **PASS after one required refactor loop**

## Initial finding and resolution

The first scan found `approvals.py` over the 300-line file limit and two touched
functions over the 20-line clarity limit. The loop extracted terminal response
classification, CLI approval-option configuration, and the safe request-formatting
module. Re-audit: all production files are below 300 lines and touched functions
are 20 lines or fewer; tests and Ty/Ruff remain green.

Resolution commit: `3e32249`.

## Gate checklist

### PASS — Supply Chain & Security

- ✓ No dependency or lockfile changes; selectors and math are standard-library.
- ✓ Diff secret scan found zero credential patterns.
- ✓ `specs/security/REVIEW.md` reports zero unresolved HIGH/CRITICAL findings at confidence ≥8.
- ✓ The pre-approved parser mode remains fail-closed until e02s05 provides explicit allowlists.

### PASS — Authorization, Input, and Boundaries

- ✓ Read-only mode bypasses interactive input and permits only read-category calls.
- ✓ Confirm mode denies non-TTY, EOF, timeout, malformed-input exhaustion, and unavailable sources before dispatch.
- ✓ Timeout is numeric, finite, positive, and capped at 300 seconds before provider client creation.
- ✓ Retry count is fixed at three; entered text is not persisted or reflected.
- ✓ Existing agent correlation and workspace/symlink confinement remain unchanged.

### PASS — Types, Architecture, and Readability

- ✓ Safe request display is isolated in `approval_format.py` behind a read-only protocol.
- ✓ Terminal I/O, session policy, CLI parsing, and output formatting have separate responsibilities.
- ✓ Every touched production function is ≤20 lines; production files are <300 lines.
- ✓ Ty/Ruff diagnostics are zero across affected source and tests.

### PASS — Test Coverage and F.I.R.S.T

- ✓ Public tests cover read-only behavior, input timeout, malformed retry exhaustion, non-TTY denial, CLI pre-network validation, agent no-side-effect denials, and existing confinement regressions.
- ✓ Fast: 64 affected tests in 0.366 seconds; full 134-test project suite in 0.462 seconds.
- ✓ Independent/Repeatable: fake streams and timeout sources avoid real waiting; temporary workspaces and patched boundaries avoid external effects.
- ✓ Self-Validating: assertions cover reasons, prompts, provider construction, call correlation, and filesystem sentinels.
- ✓ Timely: policy/timeout behavior used RED/GREEN commits; inherited agent/tool behavior gained narrow regressions only.

### PASS — Scope and Defensive Code

- ✓ No remote approval, Windows certification, persistence, arbitrary shell execution, or pre-approval allowlist was added.
- ✓ Graceful degradation returns structured denial while allowing confined reads and final model text.
- ✓ Existing process timeout remains distinct from approval timeout.

## F.I.R.S.T quick result

**PASS — Fast, Independent, Repeatable, Self-Validating, and Timely.**

## Rationalizations rejected

- “Piped stdin can be treated as approval” was rejected: no trusted interactive authority exists.
- “Any invalid input means deny once” was rejected: a bounded retry makes explicit choices recoverable without hanging.
- “Pre-approved can be accepted now and implemented later” was rejected: it remains fail-closed pending e02s05.
