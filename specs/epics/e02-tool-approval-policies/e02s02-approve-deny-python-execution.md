STORY KEY: e02s02
TITLE:     Approve or deny local Python execution
TYPE:      Story
PARENT:    e02
STATUS:    Refined
AUTHOR:    OrbitRelay team           DATE: 2026-07-23
MATURITY:  4
SIZE:      M
type:      feat
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

After file writes are governed, `run_python_file` remains the other built-in
consequential tool. It currently launches a validated local Python file without
asking the user. This story extends the same batch-first consent boundary to
process creation.

### 2. Value statement [reviewed]

Users can inspect and control every local process OrbitRelay proposes before it
receives execution authority.

### 3. Actors and permissions [reviewed]

- The local user may approve or deny execution.
- The model may propose a file and arguments but cannot approve them.
- OrbitRelay may spawn only an approved, workspace-confined Python command.

### 4. Trigger and preconditions [reviewed]

- e02s01 approval preparation and batch orchestration exist.
- A model requests `run_python_file` with a valid workspace file and arguments.
- The run uses interactive confirm policy.

### 5. Main flow and business logic [reviewed]

1. OrbitRelay prepares the execution without starting a subprocess.
2. It displays the trusted Python executable label, escaped file path, escaped
   arguments, and selected workspace.
3. It collects execution decisions with every other decision in the batch.
4. Approval allows the existing subprocess boundary to run in original order.
5. Denial returns a correlated structured failure and starts no process.

### 6. Alternative flows and exceptions [reviewed]

- A missing, non-regular, non-Python, unsafe, or malformed request returns its
  validation error without prompting.
- Empty arguments are displayed as an empty list.
- Control characters and oversized values are escaped/truncated in display but
  the validated original values are passed to an approved process.
- Existing 30-second process execution timeout remains distinct from the
  approval timeout.

### 7. Interface elements [reviewed]

- Prompt identifies `run_python_file`, workspace, Python file, and arguments.
- Choices are approve once and deny once in this slice.
- Display is trusted framing plus escaped model-controlled values.

### 8. Domain model [reviewed]

This story reuses `PreparedToolCall`, `ApprovalSession`, `ApprovalDecision`, and
the execute category introduced by e02s01.

Requirement deltas:

#### MODIFIED: Built-in Python execution
**Before:** A valid `run_python_file` request launches immediately during tool
dispatch.
**After:** The command is prepared and included in complete-batch authorization;
the subprocess starts only after explicit approval.

#### ADDED: Execution approval preview
The user sees the selected workspace, Python file, and arguments inside trusted,
control-escaped framing before deciding.

#### ADDED: Correlated execution denial
A denied execution returns one machine-readable `approval_denied` tool result
and produces no subprocess call.

### 9. Integrations and boundaries [reviewed]

- `run_python_file` remains the sole subprocess boundary.
- Tool preparation must validate the handler signature and path before prompting.
- Agent batch order and result correlation remain unchanged.

### 10. Background processes [reviewed]

No background process is added. An approved process remains synchronous and
bounded by the existing execution timeout.

### 11. Notifications [reviewed]

The terminal approval prompt is the only notification.

### 12. Audit and logging [reviewed]

Decision records include file path and argument count, not raw argument values,
stdout, stderr, environment values, or process results.

### 13. Solution variabilities [reviewed]

- Approval timeout and process timeout remain separate concepts.
- P2 approves only the existing Python-file tool, not arbitrary shell commands.

### 14. Quality attributes *NFR* [reviewed]

- Tests patch the subprocess boundary and never run untrusted fixture code.
- Approval adds no change to process result formatting or 30-second timeout.

### 15. Security and compliance *NFR* [reviewed]

- No process starts before every batch decision is collected.
- The model cannot replace the trusted workspace or Python executable.
- Prompt escaping prevents ANSI/control-sequence spoofing.
- Audit output excludes raw arguments and process output.

### 16. UX and accessibility *NFR* [reviewed]

- The command preview is readable in a keyboard-only terminal.
- Long arguments are bounded with an explicit truncation marker.
- Denial is reported as an ordinary tool outcome.

### 17. Acceptance criteria [reviewed]

Scenario: Approve Python execution
Given a valid workspace Python file and fake subprocess boundary
When the user approves the prepared request
Then the process starts once with the validated file, arguments, and workspace

Scenario: Deny Python execution
Given a valid request and subprocess sentinel
When the user denies
Then the sentinel proves no process started and the model receives `approval_denied`

Scenario: Reject invalid execution without prompting
Given an unsafe path, non-Python file, or malformed arguments
When OrbitRelay prepares the request
Then it returns a validation failure without requesting approval or starting a process

Scenario: Escape hostile prompt values
Given arguments containing control characters and an oversized value
When the approval request is displayed
Then trusted framing remains intact and no raw control character is emitted

### 18. Out of scope [reviewed]

- Arbitrary shell execution, background jobs, remote execution, process
  streaming, run-scoped disable, and unattended policy modes.

### 19. Open questions [reviewed]

None. Process execution keeps its existing 30-second timeout; approval uses the
separately configured default of 60 seconds.

### 20. References [reviewed]

- `specs/security/epics/e02/THREAT_MODEL.md`
- `specs/epics/e02-tool-approval-policies/e02s01-approve-deny-workspace-write.md`
- `src/orbitrelay/tools/run_python_file.py`
- `tests/test_sandbox.py`

## Prior Art

| Candidate | Source | Verdict | Notes |
|---|---|---|---|
| Existing subprocess wrapper | `tools.run_python_file` | extend `[OK]` | Preserve cwd, output capture, and timeout. |
| Standard-library escaping | Python `ascii`/bounded formatting | adopt `[OK]` | No terminal-formatting package is needed. |

**Reason for Depth — shared approval session:** write and execution consent use
one small policy interface so the security invariants cannot drift by handler.

## Implementation steps

1. Add execution approval preview and decision tests with hostile argument fixtures → verify: `uv run python -m unittest tests.test_approvals -v`
2. Prepare and validate Python execution without launching a process → verify: `uv run python -m unittest tests.test_tools tests.test_sandbox -v`
3. Gate subprocess creation through complete-batch authorization and preserve correlated outcomes → verify: `uv run python -m unittest tests.test_agent -v`
4. Exercise CLI approve/deny execution using fake input and a fake subprocess boundary → verify: `uv run python -m unittest tests.test_cli tests.test_approvals -v`
5. Run execution security regressions and confirm no new findings in affected paths → verify: `uv run python -m unittest tests.test_agent tests.test_tools tests.test_sandbox tests.test_approvals -v && printf '%s\n' 'no new security findings in affected paths'`

## Verification script

1. Run `uv run python -m unittest tests.test_approvals tests.test_agent tests.test_sandbox -v`.
2. Confirm the approved fixture calls the fake process exactly once.
3. Confirm denied and invalid fixtures never call the fake process.
4. Inspect captured prompt and decision records for raw control sequences,
   argument values, stdout, and stderr.
