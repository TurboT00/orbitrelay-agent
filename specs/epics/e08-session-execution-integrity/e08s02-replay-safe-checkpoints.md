STORY KEY: e08s02
TITLE:     Recover from interruption at a replay-safe checkpoint
TYPE:      Story
PARENT:    e08
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      L
type:      fix
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Independent message/event rewrites can leave a session at a partial assistant tool-call boundary after interruption.

### 2. Value statement [reviewed]

Resume starts from the last complete replay-safe group without orphaned, duplicated, or reordered tool results.

### 3. Actors and permissions [reviewed]

The owning run checkpoints; resume validates; filesystem failures cannot authorize partial state.

### 4. Trigger and preconditions [reviewed]

e08s01 exclusive ownership is held for the transaction.

### 5. Main flow and business logic [reviewed]

Build one complete checkpoint, write unique temporary files, synchronize data/directories, and atomically replace the committed generation.

### 6. Alternative flows and exceptions [reviewed]

Interrupt before commit leaves the prior generation valid; malformed or mismatched generations are reported as corrupt.

### 7. Interface elements [reviewed]

Resume behavior is unchanged for valid sessions; corruption uses e06s05 diagnostics.

### 8. Domain model [reviewed]

A checkpoint generation contains versioned metadata, complete messages, correlated events, and a commit identity.

### 9. Integrations and boundaries [reviewed]

Touches sessions, event collector binding, message callbacks, context budgeting, redaction, and tool-pair validation.

### 10. Background processes [reviewed]

None.

### 11. Notifications [reviewed]

Durability/corruption failures are explicit and never presented as a successful save.

### 12. Audit and logging [reviewed]

Temporary/checkpoint metadata remains secret-free and uses restrictive permissions.

### 13. Solution variabilities [reviewed]

Older valid sessions are read compatibly and upgraded only after a successful complete checkpoint; incomplete old forms are rejected with guidance.

### 14. Architecture decisions [reviewed]

Use a generation-level checkpoint transaction rather than independent file replacement. Reason for Depth: messages, events, metadata, tool IDs, and sensitivity markers must commit as one replay boundary.

### 15. Test strategy [reviewed]

Inject failure/interruption at user, assistant, partial batch, complete batch, synchronization, replacement, and final-answer boundaries.

### 16. Observability [reviewed]

Expose checkpoint generation and corruption category, not content.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Session checkpoint durability

**Before:** Session components may be rewritten independently during tool rounds.

**After:** Only complete replay-safe groups become the durable generation through synchronized unique temporaries and atomic replacement.

```gherkin
Feature: Replay-safe checkpoints
  Scenario: Interruption during a tool batch
    Given a committed prior generation
    When interruption occurs before all tool results exist
    Then resume reads the prior generation with no orphaned calls

  Scenario: Complete group commits
    Given a complete correlated tool group
    When synchronization and replacement succeed
    Then resume sees it exactly once in original order

  Scenario: Legacy session is valid
    Given a complete older session
    When it resumes and checkpoints
    Then it upgrades without losing extension fields or tool pairs
```

### 18. Dependencies and sequencing [reviewed]

Depends on e08s01; precedes e06s04, e08s03, e08s04, and e08s06.

### 19. Out of scope [reviewed]

Database adoption, cloud replication, merging generations, or best-effort orphan repair.

### 20. Definition of done [reviewed]

Fault-injection, replay, context, agent, migration, permission, and security tests pass.

## Implementation Steps

1. Add interruption contracts at every replay boundary → verify: `uv run python -m unittest tests.test_session_transactions -v`
2. Commit complete groups with unique temporaries, durable sync, and atomic replacement → verify: `uv run python -m unittest tests.test_session_transactions tests.test_sessions tests.test_context_budget -v`
3. Resume without orphaning, reordering, or duplicating tool identifiers → verify: `uv run python -m unittest tests.test_session_transactions tests.test_agent tests.test_context_budget -v`

## Verification Script (Step-by-Step)

1. Seed a committed session and inject one interruption at each boundary.
2. Resume after every injection and validate complete message/tool groups.
3. Check file modes, temporary cleanup, generation identity, and extension-field preservation.

