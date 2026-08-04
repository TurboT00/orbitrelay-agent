STORY KEY: e08s01
TITLE:     Prevent concurrent ownership of one active session
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

Two processes can currently load and rewrite one session concurrently, risking lost or interleaved history.

### 2. Value statement [reviewed]

One process owns a session for the complete run while independent sessions remain concurrent.

### 3. Actors and permissions [reviewed]

Run processes request exclusive ownership; list/show inspect secret-free state concurrently; deletion also requires ownership.

### 4. Trigger and preconditions [reviewed]

D-03 is authoritative; lock conflict must occur before any provider request.

### 5. Main flow and business logic [reviewed]

Acquire a kernel-backed session lease before history load, hold it through model/tools/checkpoint, and release it on every exit.

### 6. Alternative flows and exceptions [reviewed]

Default conflict fails immediately; an explicit bounded wait may retry until timeout; crash releases the kernel lock.

### 7. Interface elements [reviewed]

Run/resume accepts an explicit finite wait option; list/show identify active sessions; errors use e06s05 streams.

### 8. Domain model [reviewed]

A session lease carries session ID, acquisition mode, bounded deadline, and active-state metadata without secret content.

### 9. Integrations and boundaries [reviewed]

Touches CLI session preparation, `SessionStore`, provider-call ordering, agent callbacks, session commands, and deletion.

### 10. Background processes [reviewed]

None; bounded waiting occurs in the foreground without indefinite sleep.

### 11. Notifications [reviewed]

Conflict/timeout returns a concise nonzero diagnostic before network or tool activity.

### 12. Audit and logging [reviewed]

Active status may expose process-neutral state, not PID-derived authority, history, or credentials.

### 13. Solution variabilities [reviewed]

Use stdlib `fcntl` on the qualified macOS platform; no new lock package is proposed.

### 14. Architecture decisions [reviewed]

Introduce a `SessionLease` context managed by `SessionStore`. Reason for Depth: ownership must span load, external calls, callbacks, and final checkpoint rather than one file operation.

### 15. Test strategy [reviewed]

Spawn real processes for conflict, wait, timeout, crash release, independent sessions, and pre-provider failure ordering.

### 16. Observability [reviewed]

List/show report active status safely; lock implementation details remain internal.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Session ownership

**Before:** Session load and writes are individually uncoordinated across processes.

**After:** One process exclusively owns a session from load through final durable checkpoint; conflict fails or explicitly waits for a finite bound before any provider request.

```gherkin
Feature: Exclusive session ownership
  Scenario: Concurrent owner conflicts
    Given one process owns a session
    When another resumes without a wait
    Then it exits nonzero before any provider request

  Scenario: Bounded wait succeeds or times out
    Given an explicit finite wait
    When ownership becomes available or the deadline expires
    Then the process acquires it or fails without waiting indefinitely

  Scenario: Independent sessions run concurrently
    Given two different session IDs
    When two processes run them
    Then neither blocks the other
```

### 18. Dependencies and sequencing [reviewed]

Depends on e05s01/e09s01; precedes e08s02, e08s03, and e06s04.

### 19. Out of scope [reviewed]

Merged concurrent edits, distributed locks, Windows locking, indefinite waits, or cloud sessions.

### 20. Definition of done [reviewed]

Multi-process, session, agent, CLI-error, and security tests pass.

## Implementation Steps

1. Add real multi-process conflict, wait, timeout, crash, and independent-session contracts → verify: `uv run python -m unittest tests.test_session_concurrency -v`
2. Hold ownership from load through provider/tools to final checkpoint → verify: `uv run python -m unittest tests.test_session_concurrency tests.test_sessions tests.test_agent -v`
3. Fail before provider access while keeping secret-free list/show available → verify: `uv run python -m unittest tests.test_session_concurrency tests.test_sessions tests.test_cli_errors -v`

## Verification Script (Step-by-Step)

1. Start a helper process that owns a temp session.
2. Exercise immediate conflict, successful finite wait, timeout, and crash release.
3. Assert the fake provider has zero calls on conflict and list/show reports active state.

