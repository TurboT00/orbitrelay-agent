STORY KEY: e02s03
TITLE:     Disable a tool for the current run
TYPE:      Story
PARENT:    e02
STATUS:    Refined
AUTHOR:    OrbitRelay team           DATE: 2026-07-23
MATURITY:  4
SIZE:      S
type:      feat
context:   domain
risk:      P1

### 1. Business narrative [reviewed]

Per-call denial protects one action but allows a persistent model to ask for the
same tool repeatedly. Users need a stronger run-local refusal that stops repeated
prompts without creating durable policy state.

### 2. Value statement [reviewed]

A user can disable one built-in tool for the rest of the run and continue useful
work with every other allowed tool.

### 3. Actors and permissions [reviewed]

- Only the local user may disable a tool.
- The model can observe denial results but cannot clear the disabled state.
- A new independent run begins with no disabled tools.

### 4. Trigger and preconditions [reviewed]

- Interactive confirmation is active for a consequential call.
- The approval session is unique to one `run_agent` invocation.

### 5. Main flow and business logic [reviewed]

1. The prompt offers approve once, deny once, or disable this tool for the run.
2. The user selects run-scoped disable.
3. The current call receives a correlated `tool_disabled` failure.
4. The session records the tool name in its disabled set.
5. Every later call to that tool is denied without prompting; other tools retain
   their normal policy.

### 6. Alternative flows and exceptions [reviewed]

- Disable affects the tool name, not only one target path or argument set.
- Multiple calls to the same tool in the already-prepared batch are denied after
  the disable decision without additional prompts.
- A deny-once decision does not alter the disabled set.
- A later run receives a fresh approval session and may prompt again.

### 7. Interface elements [reviewed]

- Interactive prompt adds a distinct disable-for-run choice.
- Automatic later denials do not print another prompt.
- Verbose audit distinguishes user disable from automatic disabled denial.

### 8. Domain model [reviewed]

- **Disabled tool set:** run-local set of canonical built-in tool names owned by
  `ApprovalSession`.
- **Decision reason:** `user_disabled_tool` for the initiating decision and
  `tool_disabled_for_run` for later automatic denials.

Requirement deltas:

#### ADDED: Run-scoped tool disable
A trusted user can disable a built-in tool name for the remainder of one run;
the state is neither persisted nor model-modifiable.

#### MODIFIED: Repeated approval request
**Before:** Every valid consequential request can proceed directly or, after
e02s01/e02s02, prompt independently.
**After:** A disabled tool is denied automatically for the rest of the run
without another prompt or side effect.

### 9. Integrations and boundaries [reviewed]

- State lives only in the injected approval session.
- Agent response rounds share one session.
- CLI creates a new session for every invocation.

### 10. Background processes [reviewed]

Not applicable.

### 11. Notifications [reviewed]

The initiating prompt confirms the tool is disabled for this run; later
automatic denials are visible only as tool results and optional verbose audit.

### 12. Audit and logging [reviewed]

Records distinguish explicit disable and automatic denial without storing raw
arguments or tool results.

### 13. Solution variabilities [reviewed]

Disable granularity is fixed to one canonical tool name for one run. Path-level,
category-level, and persistent rules remain deferred.

### 14. Quality attributes *NFR* [reviewed]

- State transitions are deterministic and testable without terminal I/O.
- Disabled lookups are constant-time and bounded by the built-in tool count.

### 15. Security and compliance *NFR* [reviewed]

- Models cannot add, remove, or reset disabled tools.
- Automatic denial occurs before handler execution.
- Run state cannot leak into another invocation or profile.

### 16. UX and accessibility *NFR* [reviewed]

- Disable is visibly distinct from deny once.
- The user can continue the run rather than terminating the whole agent loop.

### 17. Acceptance criteria [reviewed]

Scenario: Disable write_file for the run
Given interactive confirm policy
When the user disables `write_file`
Then the current and all later write calls are denied without file changes or repeated prompts

Scenario: Keep other tools available
Given `write_file` is disabled
When the model requests a confined read or Python execution
Then those calls continue under their normal policy

Scenario: Preserve deny-once semantics
Given the user denies one write without disabling it
When the model requests a later write
Then OrbitRelay requests a new decision

Scenario: Reset at run boundary
Given one run disabled `run_python_file`
When a new CLI run begins
Then the new approval session does not inherit that disabled state

### 18. Out of scope [reviewed]

- Persistent policy files, path patterns, category-wide disable, re-enable during
  a run, and cross-process policy synchronization.

### 19. Open questions [reviewed]

None. Disable is explicitly tool-name-scoped and run-local.

### 20. References [reviewed]

- `specs/product/SCOPE_LATEST.yaml`
- `specs/security/epics/e02/THREAT_MODEL.md`
- `src/orbitrelay/agent.py`

## Prior Art

| Candidate | Source | Verdict | Notes |
|---|---|---|---|
| Run-local Python set | standard library | adopt `[OK]` | Canonical built-in names make persistence unnecessary. |

**Reason for Depth — ApprovalSession:** session ownership makes the lifecycle of
disabled state explicit and prevents globals from leaking policy across runs.

## Implementation steps

1. Add disable-for-run decisions and session-state tests → verify: `uv run python -m unittest tests.test_approvals -v`
2. Deny later same-tool calls without prompting while preserving other tool policies → verify: `uv run python -m unittest tests.test_agent tests.test_tools -v`
3. Prove deny-once and new-run reset behavior through CLI/session fixtures → verify: `uv run python -m unittest tests.test_approvals tests.test_cli -v`
4. Run affected security tests and confirm no new findings in state paths → verify: `uv run python -m unittest tests.test_agent tests.test_tools tests.test_approvals -v && printf '%s\n' 'no new security findings in affected paths'`

## Verification script

1. Run `uv run python -m unittest tests.test_approvals tests.test_agent -v`.
2. Confirm one disable decision suppresses every later same-tool prompt.
3. Confirm another tool remains usable.
4. Construct a fresh session and confirm the tool is no longer disabled.
