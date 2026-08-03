STORY KEY: e08s03
TITLE:     Inspect and delete corrupt sessions explicitly
TYPE:      Story
PARENT:    e08
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      M
type:      fix
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Corrupt sessions can disappear from listings yet survive cleanup, preventing users from understanding or removing local state.

### 2. Value statement [reviewed]

Users can see secret-free corrupt/active state and explicitly remove inactive corrupt sessions.

### 3. Actors and permissions [reviewed]

Users list/show/delete; active owners retain exclusive authority; corrupt content is never replayed.

### 4. Trigger and preconditions [reviewed]

e08s01 ownership and e08s02 checkpoint/corruption categories exist.

### 5. Main flow and business logic [reviewed]

Enumerate session directories safely, classify valid/active/corrupt, render safe state, and acquire exclusive ownership before deletion.

### 6. Alternative flows and exceptions [reviewed]

Malformed metadata, truncated JSONL, wrong modes/owner, symlinks, permission errors, and active sessions remain visible and fail closed.

### 7. Interface elements [reviewed]

`session list`, `session show`, `session delete`, and delete-all report per-session outcomes; incomplete delete-all exits nonzero.

### 8. Domain model [reviewed]

Session inspection state is valid, active, corrupt, inaccessible, or unsafe with a bounded secret-free reason.

### 9. Integrations and boundaries [reviewed]

Touches session CLI/store, redaction, permissions, symlink checks, leases, and top-level errors.

### 10. Background processes [reviewed]

None.

### 11. Notifications [reviewed]

Partial cleanup names session IDs and safe reasons, never history content.

### 12. Audit and logging [reviewed]

Deletion results are explicit; no corrupt payload is copied into logs.

### 13. Solution variabilities [reviewed]

Corruption categories may be additive; deletion never attempts to repair content implicitly.

### 14. Architecture decisions [reviewed]

Separate safe inspection metadata from content loading. Reason for Depth: list/delete must identify corrupt state without parsing it as resumable history.

### 15. Test strategy [reviewed]

Use temp homes plus helper lock processes for every corrupt, unsafe, permission, active, and partial-delete branch.

### 16. Observability [reviewed]

List/show expose status, timestamp when trustworthy, and safe diagnostic only.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Corrupt session lifecycle

**Before:** Corrupt sessions may be omitted and can survive delete-all without a complete failure report.

**After:** Corrupt sessions remain visible, inactive corrupt sessions are explicitly deletable, and every partial cleanup failure is reported with nonzero exit.

```gherkin
Feature: Corrupt session lifecycle
  Scenario: Corrupt session remains visible
    Given malformed metadata or truncated JSONL
    When list/show runs
    Then the session ID and safe corrupt state are shown without content

  Scenario: Active session cannot be deleted
    Given another process owns the session
    When deletion runs
    Then it fails without modifying files

  Scenario: Delete-all is partial
    Given deletable and active/corrupt-inaccessible sessions
    When delete-all runs
    Then every outcome is reported and exit is nonzero if any remain
```

### 18. Dependencies and sequencing [reviewed]

Depends on e08s01/e08s02 and uses e06s05 error presentation.

### 19. Out of scope [reviewed]

Automatic repair, content display for corrupt sessions, force-deleting active owners, or cloud cleanup.

### 20. Definition of done [reviewed]

Session, concurrency, CLI, permission, redaction, and security tests pass.

## Implementation Steps

1. Add malformed, truncated, permission, symlink, and active-deletion contracts → verify: `uv run python -m unittest tests.test_sessions tests.test_session_concurrency -v`
2. Keep corrupt sessions visible with secret-free state → verify: `uv run python -m unittest tests.test_sessions tests.test_cli_errors -v`
3. Delete inactive corrupt sessions and report delete-all partial failures nonzero → verify: `uv run python -m unittest tests.test_sessions tests.test_session_concurrency -v`

## Verification Script (Step-by-Step)

1. Create each invalid session form in a temp OrbitRelay home.
2. Run list/show and inspect safe status.
3. Hold one lease, run individual/delete-all operations, and inspect files and exits.

