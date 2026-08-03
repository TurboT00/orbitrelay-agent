STORY KEY: e10s01
TITLE:     Record the authorized macOS readiness evidence
TYPE:      Story
PARENT:    e10
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      M
type:      feat
context:   infra
risk:      P0

### 1. Business narrative [reviewed]

Automated offline tests cannot prove native keyring, authorized provider/Codex, and macOS Python behavior, while unsafe evidence can leak credentials.

### 2. Value statement [reviewed]

Release owners receive revision-bound, sanitized evidence for every explicitly authorized macOS scenario and an honest record of skipped work.

### 3. Actors and permissions [reviewed]

An authorized operator runs the disposable environment; reviewers inspect sanitized results; agents never infer authorization.

### 4. Trigger and preconditions [reviewed]

The e05 prerequisite subset and e09 per-minor credential evidence are recorded, automated gates pass on one candidate revision, and the user separately authorizes each remaining credential-bearing/live scenario.

### 5. Main flow and business logic [reviewed]

Update the runbook/evidence form and executable validator, execute only approved scenarios, sanitize immediately, and validate completeness/revision binding.

### 6. Alternative flows and exceptions [reviewed]

Unauthorized, unavailable, skipped, failed, or deferred scenarios remain explicit and cannot be converted to pass.

### 7. Interface elements [reviewed]

The local manual record includes command category, expected contract, result, revision, environment, sanitization check, and residual risk.

### 8. Domain model [reviewed]

Evidence state is passed, failed, skipped, unavailable, or deferred with authorization and revision metadata.

### 9. Integrations and boundaries [reviewed]

Covers D-01 privacy, D-02 providers, D-03 sessions, D-04 matrix/keyring, D-05 Codex, and release artifact behavior.

### 10. Background processes [reviewed]

None outside bounded test commands; disposable state is cleaned according to the runbook.

### 11. Notifications [reviewed]

Any leak, unexpected credential mutation, or incomplete required scenario blocks evidence acceptance.

### 12. Audit and logging [reviewed]

Never retain keys, tokens, provider payloads, account data, protected workspace content, request IDs, or raw Codex status output.

### 13. Solution variabilities [reviewed]

No external package is proposed; local evidence remains untracked/private unless explicitly approved for publication.

### 14. Architecture decisions [reviewed]

Use a strict evidence schema plus manual runbook rather than automating credentials into the suite. Reason for Depth: explicit authorization and sanitization cannot be safely represented by ordinary offline tests.

### 15. Test strategy [reviewed]

Automated tests validate evidence structure/redaction; humans execute only authorized scenarios on the exact candidate.

### 16. Observability [reviewed]

The evidence summary distinguishes automated, manual, skipped, and deferred proof.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: macOS readiness evidence

**Before:** Existing manual records cover an earlier contract/revision and leave required stabilization scenarios incomplete.

**After:** Required authorized scenarios use the current contracts and exact candidate revision, with sanitized outcomes and explicit skips/deferred platforms.

```gherkin
Feature: Authorized macOS readiness evidence
  Scenario: Scenario is authorized and executed
    Given explicit user authorization and a disposable environment
    When the runbook step completes
    Then result, revision, environment, and sanitization evidence are recorded

  Scenario: Scenario is not authorized
    When evidence is collected
    Then the scenario remains skipped and no live command runs

  Scenario: Evidence contains a forbidden sentinel
    When validation scans the record
    Then acceptance fails and the record is sanitized or destroyed
```

### 18. Dependencies and sequencing [reviewed]

Depends on accepted e05–e09 completion and one immutable candidate revision; precedes e10s02.

### 19. Out of scope [reviewed]

Unapproved live tests, publishing private records, provider benchmarking, Linux/Windows qualification, push, or release.

### 20. Definition of done [reviewed]

Evidence contracts/redaction pass and every required authorized scenario has an honest revision-bound outcome.

## Implementation Steps

1. Update the disposable macOS runbook, evidence schema, and executable evidence validator for the stabilized contracts → verify: `uv run python -m unittest tests.test_release_evidence -v`
2. Execute only explicitly authorized scenarios, sanitize every result, and validate the separate revision-bound evidence record → verify: `uv run python scripts/validate_release_evidence.py --record docs/manual-test-results-stabilization.md --revision "$(git rev-parse HEAD)" --required-set stabilization`
3. Validate completeness, revision binding, sanitization, and skipped/deferred state → verify: `uv run python -m unittest tests.test_release_evidence tests.test_redaction -v`

## Verification Script (Step-by-Step)

1. Record the exact candidate revision and disposable macOS environment.
2. Ask for explicit authorization before each credential-bearing or live scenario.
3. Execute approved MT scenarios from the local runbook; mark all others skipped/unavailable/deferred.
4. Sanitize results immediately and run release-evidence/redaction tests.
5. Confirm no private record is staged or included in a package.
