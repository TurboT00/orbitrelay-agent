STORY KEY: e08s06
TITLE:     Receive truthful crash-safe local tool outcomes
TYPE:      Story
PARENT:    e08
STATUS:    Complete
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      L
type:      fix
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Denied/failed tools can emit misleading phases, and direct workspace writes are vulnerable to interruption and path changes after validation.

### 2. Value statement [reviewed]

Users receive truthful outcomes and approved writes either commit safely within the workspace or leave the prior file intact.

### 3. Actors and permissions [reviewed]

The model requests tools; preparation validates the full batch; user policy authorizes; execution returns typed outcomes.

### 4. Trigger and preconditions [reviewed]

Complete-batch validation, approval ordering, path confinement, and e08s02 checkpoints remain non-negotiable.

### 5. Main flow and business logic [reviewed]

Define typed prepared/execution outcomes, emit phases only when true, and implement writes with confined handles, unique temporary files, sync, and atomic replacement.

### 6. Alternative flows and exceptions [reviewed]

Validation failure, denial, execution error, interruption, symlink/path race, sync failure, and replacement failure leave truthful results and no false success.

### 7. Interface elements [reviewed]

Tool results, events, and summaries expose stable outcome/status/reason metadata without raw arguments or content.

### 8. Domain model [reviewed]

Outcomes include validation-failed, denied, execution-failed, interrupted, and succeeded with correlated call ID.

### 9. Integrations and boundaries [reviewed]

Touches tool registry/preparation, approvals, agent loop, path safety, write tool, events, summaries, sessions, and redaction.

### 10. Background processes [reviewed]

None beyond the bounded execution already modeled.

### 11. Notifications [reviewed]

Denied work is never announced as executing; failed writes give safe recovery guidance.

### 12. Audit and logging [reviewed]

Record tool name/category, call ID, phase, status, and reason only.

### 13. Solution variabilities [reviewed]

Use stdlib filesystem primitives; no new atomic-write package is proposed.

### 14. Architecture decisions [reviewed]

Introduce one typed `ToolOutcome` consumed by results, events, and summaries. Reason for Depth: three observers must agree on denial/failure/success while preserving full-batch and correlation invariants.

### 15. Test strategy [reviewed]

Fault-inject every outcome and write syscall boundary; race symlink/path replacement without touching outside the workspace.

### 16. Observability [reviewed]

Outcome metadata is consistent across live events, persisted events, tool results, and summaries.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Local tool outcomes and writes

**Before:** Some denied/failed work can appear as executing/successful, and writes replace target content without a crash-safe transaction.

**After:** Typed outcomes are truthful everywhere, and approved writes commit atomically inside the validated workspace or preserve prior state.

```gherkin
Feature: Truthful crash-safe tools
  Scenario: Denied tool
    When policy denies a prepared call
    Then no executing phase is emitted and every observer reports denied

  Scenario: Write is interrupted
    Given an existing target
    When interruption occurs before atomic replacement
    Then the original target remains intact and no success is emitted

  Scenario: Path changes after validation
    When a target or parent becomes a symlink before commit
    Then the write fails within confinement and no outside file changes
```

### 18. Dependencies and sequencing [reviewed]

Depends on e08s02 and shared e06s05 presentation; coordinates with e08s05 result metadata.

### 19. Out of scope [reviewed]

Filesystem transactions across multiple files, undo, privilege escalation, or weakened preapproval validation.

### 20. Definition of done [reviewed]

Outcome matrix, path-race, crash, agent, event, summary, approval, session, and security tests pass.

## Implementation Steps

1. Add end-to-end contracts for success, denial, validation/execution failure, and interruption → verify: `uv run python -m unittest tests.test_tools tests.test_agent tests.test_events -v`
2. Make approved writes crash-safe and validation-to-use resistant without weakening confinement → verify: `uv run python -m unittest tests.test_tools tests.test_sandbox -v`
3. Emit truthful phases, results, events, and summaries for every outcome → verify: `uv run python -m unittest tests.test_agent tests.test_events tests.test_run_summary tests.test_approvals -v`

## Verification Script (Step-by-Step)

1. Run the full typed outcome matrix and compare all observers.
2. Inject interruption at temporary write, sync, and replacement boundaries.
3. Race target/parent symlinks and inspect workspace/outside files.

