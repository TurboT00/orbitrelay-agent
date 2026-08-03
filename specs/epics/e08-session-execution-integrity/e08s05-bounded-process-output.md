STORY KEY: e08s05
TITLE:     Bound local tool and Codex process output
TYPE:      Story
PARENT:    e08
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      M
type:      fix
context:   infra
risk:      P0

### 1. Business narrative [reviewed]

Python tools and Codex subprocesses can capture unbounded output, consuming memory and leaking discarded data into results.

### 2. Value statement [reviewed]

Local execution remains bounded, non-deadlocking, and explicit about truncation and timeout.

### 3. Actors and permissions [reviewed]

Approved tools and the official Codex CLI produce output; OrbitRelay bounds capture and exposes safe metadata.

### 4. Trigger and preconditions [reviewed]

Existing approval, subprocess injection, and redaction contracts remain active.

### 5. Main flow and business logic [reviewed]

Stream/drain both pipes, retain up to documented named byte limits, terminate on timeout, and return truncation/timeout metadata.

### 6. Alternative flows and exceptions [reviewed]

Large stdout/stderr, mixed output, child error, timeout, and termination failure remain bounded and truthful.

### 7. Interface elements [reviewed]

Tool results/events/summaries report truncated fields and original/retained sizes where safely known.

### 8. Domain model [reviewed]

A bounded process result contains status, retained stdout/stderr, truncation flags, byte counts, exit code, and timeout state.

### 9. Integrations and boundaries [reviewed]

Touches Python tool execution, Codex bridge, tool results, events, summaries, and redaction.

### 10. Background processes [reviewed]

Subprocesses are foreground with bounded lifetime and deterministic cleanup.

### 11. Notifications [reviewed]

Users/models see bounded content and explicit truncation, never silent loss presented as complete.

### 12. Audit and logging [reviewed]

Discarded content and raw arguments are never copied into events or summaries.

### 13. Solution variabilities [reviewed]

Exact limits/timeouts are selected from tests and current UX, then documented as named constants; no new subprocess package is proposed.

### 14. Architecture decisions [reviewed]

Share a bounded-process result contract while retaining separate tool/Codex runners. Reason for Depth: events and summaries need identical truncation truth without coupling credential ownership.

### 15. Test strategy [reviewed]

Use deterministic helper processes for large/mixed output, boundary sizes, timeout, and termination branches.

### 16. Observability [reviewed]

Emit status, counts, duration, timeout, and truncation flags only.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Local process output capture

**Before:** Python and Codex paths can retain unbounded subprocess output.

**After:** Both paths drain safely, retain documented bounded output, and expose truthful truncation/timeout metadata without discarded content.

```gherkin
Feature: Bounded local process output
  Scenario: Output exceeds the limit
    When a helper writes beyond stdout and stderr bounds
    Then the process completes without deadlock and retained output stays within limits

  Scenario: Process times out
    When a helper exceeds the deadline
    Then it is terminated and timeout is reported truthfully

  Scenario: Discarded output is sensitive
    Given sentinel data beyond the retained bound
    Then events, summaries, and errors contain no discarded sentinel
```

### 18. Dependencies and sequencing [reviewed]

Uses e07s03 Codex normalization and shared e08 result vocabulary; precedes e10 evidence.

### 19. Out of scope [reviewed]

Interactive terminal emulation, streaming Codex account output, unlimited configuration, or background jobs.

### 20. Definition of done [reviewed]

Boundary, deadlock, timeout, event, summary, redaction, and security tests pass.

## Implementation Steps

1. Add large-output and timeout contracts for Python and Codex paths → verify: `uv run python -m unittest tests.test_tools tests.test_codex_bridge -v`
2. Enforce deterministic limits and truncation metadata without deadlock → verify: `uv run python -m unittest tests.test_tools tests.test_codex_bridge tests.test_events -v`
3. Keep failures/summaries free of arguments, credentials, and discarded output → verify: `uv run python -m unittest tests.test_tools tests.test_codex_bridge tests.test_run_summary tests.test_redaction -v`

## Verification Script (Step-by-Step)

1. Run helpers below, at, and above each named byte/time bound.
2. Exercise mixed stdout/stderr and a process that ignores graceful termination.
3. Scan retained results, events, summaries, and errors for discarded sentinels.

