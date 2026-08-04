STORY KEY: e06s04
TITLE:     Resume an explicitly persisted sensitive session safely
TYPE:      Story
PARENT:    e06
STATUS:    Complete
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      L
type:      feat
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Sensitive turns are ephemeral by default, but a user may explicitly need resumable local history.

### 2. Value statement [reviewed]

A user can separately consent to local sensitive persistence and must renew exact disclosure authority before every replay.

### 3. Actors and permissions [reviewed]

The user supplies persistence consent and renewed read authority; the model cannot persist or replay sensitive history on its own.

### 4. Trigger and preconditions [reviewed]

e06s03 authority and e08s01/e08s02 exclusive, replay-safe transactions are complete.

### 5. Main flow and business logic [reviewed]

Mark sensitivity without content, checkpoint complete groups only after separate consent, and validate renewed authority before loading any sensitive history.

### 6. Alternative flows and exceptions [reviewed]

Missing, incomplete, expired, or mismatched authority fails before history load or provider request; ordinary sessions remain unchanged.

### 7. Interface elements [reviewed]

A separate CLI opt-in controls sensitive persistence; resume diagnostics explain the required renewed declaration.

### 8. Domain model [reviewed]

Session metadata adds a versioned, secret-free sensitivity marker and the minimum authorization descriptors needed to validate resume.

### 9. Integrations and boundaries [reviewed]

Touches session metadata/messages, CLI preparation, context replay, checkpoints, redaction, and provider-call ordering.

### 10. Background processes [reviewed]

None.

### 11. Notifications [reviewed]

Denied resume exits nonzero on stderr before provider access and gives recovery guidance.

### 12. Audit and logging [reviewed]

Store no exception token or credential; record consent and sensitivity metadata only.

### 13. Solution variabilities [reviewed]

Older unmarked sessions remain ordinary unless a migration can prove sensitivity; indeterminate forms fail closed rather than being auto-marked.

### 14. Architecture decisions [reviewed]

Extend the versioned session transaction instead of adding a second sensitive store. Reason for Depth: one checkpoint must keep sensitivity metadata and replay-safe messages consistent.

### 15. Test strategy [reviewed]

Test consent combinations, crash boundaries, complete tool groups, renewed exact authority, old sessions, and provider-call absence on denial.

### 16. Observability [reviewed]

List/show may report a session as sensitive without exposing paths or content.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Sensitive session persistence and resume

**Before:** Session callbacks persist turns without a sensitivity marker, and resume has no renewed sensitive-read gate.

**After:** Sensitive turns are ephemeral unless separately persisted; persisted sessions are marked and require renewed exact authority before every load or provider request.

```gherkin
Feature: Sensitive session resume
  Scenario: Default run stays ephemeral
    Given an authorized sensitive read without persistence consent
    When the run completes
    Then the sensitive turn is absent from session storage

  Scenario: Separate consent persists safely
    Given authority and explicit persistence consent
    When a complete replay-safe group checkpoints
    Then the group and sensitivity marker commit atomically

  Scenario: Resume lacks renewed authority
    Given a marked sensitive session
    When resume starts without matching authority
    Then history is not loaded and no provider request occurs
```

### 18. Dependencies and sequencing [reviewed]

Depends on e06s03, e08s01, and e08s02; must not be implemented on the current unlocked rewrite path.

### 19. Out of scope [reviewed]

Encryption, automatic retention expiry, persistent exceptions, cloud sync, or implicit content classification.

### 20. Definition of done [reviewed]

Consent, transaction, migration, resume, redaction, and security tests pass.

## Implementation Steps

1. Add contracts for separate persistence consent and secret-free sensitivity metadata → verify: `uv run python -m unittest tests.test_workspace_privacy tests.test_sessions -v`
2. Persist complete sensitive groups only after consent and mark them atomically → verify: `uv run python -m unittest tests.test_workspace_privacy tests.test_sessions tests.test_context_budget -v`
3. Require renewed exact authority before every sensitive load or provider request → verify: `uv run python -m unittest tests.test_workspace_privacy tests.test_sessions tests.test_agent -v`

## Verification Script (Step-by-Step)

1. Run an authorized sensitive read without persistence consent and inspect storage.
2. Repeat with consent and interrupt at checkpoint boundaries.
3. Resume with missing, wrong, and correct renewed authority; inspect fake-provider calls.
