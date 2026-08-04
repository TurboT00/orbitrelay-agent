STORY KEY: e10s02
TITLE:     Re-audit the stabilization candidate
TYPE:      Story
PARENT:    e10
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      M
type:      fix
context:   infra
risk:      P0

### 1. Business narrative [reviewed]

The release needs a current verdict against the exact candidate, not confidence inferred from task completion or a dated review.

### 2. Value statement [reviewed]

Release owners can see whether every critical/major concern is resolved, accepted, or deliberately deferred with evidence and residual risk.

### 3. Actors and permissions [reviewed]

Reviewers run automated evidence and independent review; release owners accept residual risk separately from implementation.

### 4. Trigger and preconditions [reviewed]

e10s01 evidence is complete and the candidate revision is unchanged.

### 5. Main flow and business logic [reviewed]

Run the current finding oracle, link every result to evidence, independently review the changed boundaries, and issue a secret-free readiness verdict.

### 6. Alternative flows and exceptions [reviewed]

Open critical findings block automatically; open major findings require explicit acceptance/defer rationale or block; changed revision invalidates evidence.

### 7. Interface elements [reviewed]

The re-audit report distinguishes automated proof, independent review, waiver, accepted risk, deferred work, and blocker.

### 8. Domain model [reviewed]

A verdict binds revision, finding dispositions, evidence references, waivers, residual risks, and release recommendation.

### 9. Integrations and boundaries [reviewed]

Consumes e05 finding data, tracked verification artifacts, impact constraints, diffs, tests, and release gates.

### 10. Background processes [reviewed]

None.

### 11. Notifications [reviewed]

The verdict is READY, NOT READY, or READY WITH EXPLICIT ACCEPTANCE; it never hides incomplete evidence.

### 12. Audit and logging [reviewed]

Only allowlisted, secret-free references enter the verdict; private payloads are rejected.

### 13. Solution variabilities [reviewed]

No external package is proposed; the re-audit may recommend another fix loop but cannot waive itself.

### 14. Architecture decisions [reviewed]

Reuse the e05 executable oracle and add independent review evidence. Reason for Depth: none; a second competing finding registry would create drift.

### 15. Test strategy [reviewed]

Validate completeness, severity decision rules, revision binding, evidence classes, and redaction; run independent security/code review on affected paths.

### 16. Observability [reviewed]

Publish counts, blockers, accepted residual risks, and evidence classes.

### 17. Acceptance criteria [reviewed]

#### ADDED: Candidate re-audit verdict

The exact candidate receives a complete, secret-free verdict with no open critical concern and explicit treatment of every major concern.

```gherkin
Feature: Stabilization candidate re-audit
  Scenario: Evidence is complete
    Given the exact candidate and all required artifacts
    When the oracle and independent review run
    Then every finding links to current automated evidence or explicit risk treatment

  Scenario: Critical concern remains
    When the verdict is calculated
    Then release is NOT READY without a waiver path

  Scenario: Candidate revision changes
    When evidence revision differs from source
    Then the verdict is invalid until evidence is rerun
```

### 18. Dependencies and sequencing [reviewed]

Depends on e10s01 and all earlier accepted stories; precedes e10s03.

### 19. Out of scope [reviewed]

Implementing fixes inside the audit, silent waivers, publishing private evidence, or creating a release.

### 20. Definition of done [reviewed]

Baseline/evidence/redaction tests and independent code/security reviews support one explicit candidate verdict.

## Implementation Steps

1. Re-run the current finding oracle against the exact revision and link evidence → verify: `uv run python -m unittest tests.test_release_baseline tests.test_release_evidence -v`
2. Require every critical/major concern to be fixed, accepted, or deferred by policy → verify: `uv run python -m unittest tests.test_release_baseline -v`
3. Produce a secret-free verdict separating automated proof, waivers, residual risk, and independent review evidence → verify: `uv run python -m unittest tests.test_release_baseline tests.test_redaction -v && uv run python scripts/validate_release_evidence.py --record specs/verifications/release-evidence.json --revision "$(git rev-parse HEAD)" --required-set automated --require-review`

## Verification Script (Step-by-Step)

1. Freeze and record the candidate revision.
2. Run all automated gates and validate generated evidence revision binding.
3. Conduct independent code and security review of affected paths.
4. Calculate and review the final verdict and residual risks.
