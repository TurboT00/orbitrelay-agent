# Security Review — e02s02 Python Execution Approval

- Reviewed at: `2026-07-23T21:20:00Z`
- Story baseline: `a84c622`
- Merge base: `8bcefba610a4fd1c66c47e665247325b04ecfdb2`
- Scope: e02s02 production and test changes on `feat/tool-approval-policies`
- Threat model: `specs/security/epics/e02/THREAT_MODEL.md`

## Gate result

**PASS — no unresolved HIGH or CRITICAL findings with confidence >= 8.**

## Data-flow review

1. Model-controlled JSON enters `prepare_tool`, which resolves a fixed built-in
   handler, overwrites any supplied workspace, binds the handler signature, and
   requires a string Python path plus a list containing only string arguments.
2. `validate_python_target` resolves the path inside the trusted workspace and
   rejects escapes, missing/non-regular targets, symlinks outside the workspace,
   and non-`.py` files before an approval request is created.
3. `ApprovalRequest.for_execution` labels the fixed current interpreter and
   carries immutable workspace, path, argument tuple, and argument count context.
   Shared formatting bounds each value and escapes terminal control characters.
4. `ApprovalSession` obtains the complete batch of decisions before any prepared
   handler executes. A denial produces one correlated `approval_denied` result.
5. Approved execution reaches `run_python_file`, which repeats path confinement,
   uses `sys.executable`, constructs an argument list without a shell, sets the
   trusted workspace as `cwd`, and retains the existing 30-second process timeout.

## Vulnerability assessment

| Category | Result | Evidence |
|---|---|---|
| Authorization bypass | PASS | Execute requests are consequential, default-denied, and start no process until the complete decision tuple returns. |
| Command injection | PASS | `subprocess.run` receives a list beginning with trusted `sys.executable`; no shell, interpolation, `eval`, or arbitrary command is introduced. |
| Path traversal | PASS | Preparation and execution both call `resolve_path_within`; outside, missing, non-Python, and symlink regressions pass. |
| Prompt spoofing | PASS | Workspace, path, and arguments use fixed labels with bounded `ascii`-escaped rendering; raw ESC/newline controls do not reach stderr. |
| Unsafe deserialization | PASS | Input uses `json.loads`, object checking, signature binding, and explicit path/argument runtime types. |
| Secrets exposure | PASS | Approval output is bounded; process stdout/stderr and environment values are not included in approval previews or decision fields. |

## False-positive filtering

- Replacing a workspace file between preparation and execution requires local
  filesystem authority inside the documented trusted-user boundary. Confinement
  is rechecked at execution, and theoretical local races are excluded.
- Executing model-selected Python is the explicit user-approved capability, not
  command injection: the executable is fixed, the target is confined, arguments
  are passed without a shell, and denial remains side-effect free.
- Provider receipt of an approved tool result is pre-existing agent behavior and
  is not a new logging or credential-exposure path in this story.

## Non-blocking residual risks

- Interactive approval timeout and unattended/TTY policy remain planned for
  e02s04; the current default continues to fail closed when approval is absent.
- Run-scoped disable, pre-approved automation, and sanitized verbose decision
  events remain scoped to e02s03, e02s05, and e02s06 respectively.
- Arbitrary shell commands, background processes, and remote execution remain
  out of scope.

## Security test evidence

- `tests.test_approvals`: bounded, control-escaped execution context.
- `tests.test_tools`: side-effect-free preparation and invalid target/argument rejection.
- `tests.test_agent`: complete-batch decisions, one approved process, correlated denial.
- `tests.test_cli`: real agent-loop approve/deny flows with fake input and subprocess.
- `tests.test_sandbox`: interpreter selection and symlink confinement.
- Affected security suite: 39 tests passed with zero external process execution.
- Configured Ty and Ruff diagnostics: zero.
