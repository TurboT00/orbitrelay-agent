STORY KEY: e02s01
TITLE:     Approve or deny a workspace file write
TYPE:      Story
PARENT:    e02
STATUS:    Verified
AUTHOR:    OrbitRelay team           DATE: 2026-07-23
MATURITY:  4
SIZE:      M
type:      feat
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

OrbitRelay currently executes a valid `write_file` request immediately after the
model returns it. A malicious, confused, or over-eager model can therefore
change workspace files without the local user's informed consent.

This tracer-bullet story places one complete approval path across CLI, agent
batching, tool preparation, user decision, write execution, model feedback, and
offline verification.

### 2. Value statement [reviewed]

For a user delegating coding work, every proposed file mutation is visible and
controllable before it can change the workspace.

### 3. Actors and permissions [reviewed]

- The local user alone may approve or deny a write.
- The model may request a write but cannot choose policy or submit a decision.
- OrbitRelay may mutate the target only after trusted approval.

### 4. Trigger and preconditions [reviewed]

- The model returns a structurally valid `write_file` call.
- The workspace and target path pass existing confinement checks.
- The run uses the default `confirm` policy with interactive approval input.

### 5. Main flow and business logic [reviewed]

1. OrbitRelay validates every call in the model's response.
2. It prepares each call without executing a handler and derives a safe preview.
3. Read calls require no decision; each write displays an escaped target path
   and content length, never file content.
4. OrbitRelay collects every required decision for the batch before executing
   any call.
5. Approved calls execute in original order; denied calls produce correlated
   structured failures.
6. The model receives exactly one tool result per validated call.

### 6. Alternative flows and exceptions [reviewed]

- Deny-once changes no file and does not disable future calls.
- Invalid JSON, unknown tools, missing arguments, and unsafe paths return tool
  errors without prompting.
- A mixed batch may contain approved and denied calls; after all decisions are
  collected, approved calls execute in original order.
- EOF, timeout, noninteractive behavior, and run-scoped disable are completed by
  later e02 stories through the same approval boundary.

### 7. Interface elements [reviewed]

- Trusted prompt label identifies `write_file`.
- Preview includes escaped target path, selected workspace, and content length.
- Choices in this slice are approve once and deny once.
- Prompt and decision messages are separate from model-generated text.

### 8. Domain model [reviewed]

- **PreparedToolCall:** immutable validated handler, arguments, category,
  workspace, and safe preview; it performs no side effect.
- **ApprovalSession:** trusted run dependency that evaluates prepared calls and
  owns decisions.
- **ApprovalDecision:** approved or denied with a stable reason.
- **ToolCategory:** read, write, or execute.

Requirement deltas:

#### MODIFIED: Built-in write dispatch
**Before:** A structurally valid `write_file` call is dispatched immediately in
the agent loop.
**After:** The complete batch is prepared and authorized first; `write_file`
executes only after a trusted approve decision.

#### ADDED: Correlated approval failure
A denied write returns a machine-readable error with call ID, stable
`approval_denied` code, safe message, and no file content.

#### MODIFIED: Verbose write visibility
**Before:** Verbose dispatch can print raw write arguments, including content.
**After:** Approval and dispatch output uses a bounded, control-escaped preview
that excludes write content.

### 9. Integrations and boundaries [reviewed]

- CLI constructs the trusted run policy and approval source.
- Agent owns batch correlation and ordering.
- Tool dispatcher prepares and executes validated calls.
- Existing path-safety helpers remain mandatory and unchanged in authority.

### 10. Background processes [reviewed]

Not applicable: approval and writing are synchronous in the active run.

### 11. Notifications [reviewed]

The terminal prompt is the only user notification; no external channel is added.

### 12. Audit and logging [reviewed]

The run records call ID, tool name, safe target, decision, and reason. It never
records file content. User-visible verbose audit output is completed in e02s06.

### 13. Solution variabilities [reviewed]

- Batch semantics are fixed: authorize the complete batch, then execute approved
  calls in order.
- No external dependency is added; standard-library enums/dataclasses and an
  injected approval source are sufficient.

### 14. Quality attributes *NFR* [reviewed]

- Denial tests use temporary workspaces and side-effect sentinels.
- Existing tool-call order and correlation remain deterministic.
- Approval contracts are independent from terminal I/O and fast to test.

### 15. Security and compliance *NFR* [reviewed]

- Model-controlled preview values are bounded and control-escaped.
- No write occurs before all batch decisions are collected.
- Approval cannot weaken path or symlink confinement.
- Raw write content is absent from prompts, records, and verbose diagnostics.

### 16. UX and accessibility *NFR* [reviewed]

- The prompt is keyboard-only and names the consequential action and target.
- Choices use explicit words/keys and reject ambiguous input.
- Denial is a normal outcome, not a CLI crash.

### 17. Acceptance criteria [reviewed]

Scenario: Approve one file write
Given confirm policy and an interactive fake approval source
When the model requests a valid workspace write and the user approves
Then the file changes only after approval and the model receives the write result

Scenario: Deny one file write
Given an existing target file
When the model requests a replacement and the user denies
Then the file remains byte-for-byte unchanged and the correlated result contains `approval_denied`

Scenario: Authorize a mixed batch before side effects
Given a response containing reads and multiple writes
When OrbitRelay collects one approval and one denial
Then no handler runs until every required decision exists and approved calls later run in original order

Scenario: Reject unsafe write without prompting
Given a write target outside the selected workspace
When OrbitRelay prepares the call
Then it returns the existing confinement error and never asks for approval

### 18. Out of scope [reviewed]

- Python execution approval, run-scoped disable, unattended policies,
  pre-approved automation, persistent decisions, and rich diff previews.

### 19. Open questions [reviewed]

None. Batch-first authorization, 60-second configurable timeout, per-tool
pre-approval, and verbose stderr audit were approved before planning.

### 20. References [reviewed]

- `specs/product/SCOPE_LATEST.yaml`
- `specs/IMPACT_LATEST.md`
- `specs/security/epics/e02/THREAT_MODEL.md`
- `src/orbitrelay/agent.py`
- `src/orbitrelay/tools/__init__.py`
- `src/orbitrelay/tools/write_file.py`

## Prior Art

| Candidate | Source | Verdict | Notes |
|---|---|---|---|
| Existing full-batch structural validation | `agent._validate_tool_calls` | extend `[OK]` | Preserve the no-side-effect-before-structural-validation invariant. |
| Standard-library dataclass/Enum | Python 3.14 | adopt `[OK]` | Small immutable contracts need no package. |
| Existing workspace resolver | `tools.path_safety` | reuse `[OK]` | Policy never replaces confinement. |

**Reason for Depth — ApprovalSession:** one decision interface hides trusted
input, policy, per-run state, failure semantics, and decision records from the
agent loop.

**Reason for Depth — PreparedToolCall:** one immutable value ensures approval and
execution refer to the same validated action without reparsing model input.

## Implementation steps

1. Add approval request/decision contracts and failing write decision tests → verify: `uv run python -m unittest tests.test_approvals -v`
2. Split tool preparation from side-effect execution and preserve trusted workspace validation → verify: `uv run python -m unittest tests.test_tools -v`
3. Authorize the complete agent batch before executing approved calls and append correlated denial results → verify: `uv run python -m unittest tests.test_agent -v`
4. Inject the default confirm approval session from CLI using fake terminal input in tests → verify: `uv run python -m unittest tests.test_cli tests.test_approvals -v`
5. Run affected security regressions and confirm no new findings in write paths → verify: `uv run python -m unittest tests.test_agent tests.test_tools tests.test_sandbox tests.test_approvals -v && printf '%s\n' 'no new security findings in affected paths'`

## Verification script

1. Run `uv run python -m unittest tests.test_approvals tests.test_agent tests.test_tools -v`.
2. Confirm the approve case mutates only its temporary target after the fake
   decision is returned.
3. Confirm deny and unsafe-path cases leave side-effect sentinels unchanged.
4. Inspect captured prompt/audit fixtures and confirm write content and control
   sequences are absent.
