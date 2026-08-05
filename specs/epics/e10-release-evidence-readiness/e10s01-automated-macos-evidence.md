STORY KEY: e10s01
TITLE:     Record automated macOS readiness evidence
TYPE:      Story
PARENT:    e10
STATUS:    Complete
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      M
type:      feat
context:   infra
risk:      P0

### 1. Business narrative [reviewed]

The release needs one revision-bound automated record proving the supported
macOS package, Python matrix, safety boundaries, and release commands.

### 2. Value statement [reviewed]

Release owners receive reproducible, secret-free evidence without waiting for
credential-bearing or live-provider checks.

### 3. Actors and permissions [reviewed]

Maintainers run automated commands; reviewers inspect generated evidence and
the command definitions. User-run side testing is outside the release contract.

### 4. Trigger and preconditions [reviewed]

The e05 finding oracle and e09 automated matrix pass on one candidate revision.

### 5. Main flow and business logic [reviewed]

Run every required automated gate, record command identity and exit status,
validate completeness and revision binding, and publish only allowlisted data.

### 6. Alternative flows and exceptions [reviewed]

Any failed, missing, stale, or non-reproducible required command blocks evidence
acceptance. Platform exclusions remain explicit and cannot be converted to pass.

### 7. Interface elements [reviewed]

The tracked evidence record contains command category, expected contract,
result, revision, environment class, and residual risk.

### 8. Domain model [reviewed]

Automated evidence is passed, failed, stale, or not applicable and is bound to
one command definition and candidate revision.

### 9. Integrations and boundaries [reviewed]

Covers D-01 privacy, D-02 providers, D-03 sessions, D-04 matrix, D-05 Codex,
quality gates, package construction, and installed-wheel behavior.

### 10. Background processes [reviewed]

None outside bounded automated commands and disposable build environments.

### 11. Notifications [reviewed]

Any missing gate, revision drift, secret sentinel, or unexpected state mutation
blocks evidence acceptance.

### 12. Audit and logging [reviewed]

Never retain credentials, provider payloads, account data, protected workspace
content, request identifiers, or raw delegated-CLI status output.

### 13. Solution variabilities [reviewed]

No external package is proposed. The evidence is tracked because its schema is
strict, generated from automated results, and safe for a clean checkout.

### 14. Architecture decisions [reviewed]

Use a strict generated evidence schema backed only by automated commands. Reason
for Depth: reproducible release gates must not depend on operator-only state.

### 15. Test strategy [reviewed]

Automated tests validate evidence generation, completeness, revision binding,
redaction, failure propagation, and package exclusion rules.

### 16. Observability [reviewed]

The evidence summary publishes passed gates, failed gates, exclusions, and
residual risks.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: automated macOS readiness evidence

**Before:** Release readiness depended on operator-run scenarios and a private
record outside the reproducible checkout.

**After:** Every required readiness claim is produced by an automated,
revision-bound, secret-free command in a clean checkout.

```gherkin
Feature: Automated macOS readiness evidence
  Scenario: Required gates pass
    Given the exact candidate revision and a disposable environment
    When the automated evidence command completes
    Then every required gate has a passed revision-bound result

  Scenario: A required gate is missing or fails
    When evidence is validated
    Then readiness fails without inferring or substituting a pass

  Scenario: Evidence contains a forbidden sentinel
    When validation scans the record
    Then acceptance fails and no unsafe record is published
```

### 18. Dependencies and sequencing [reviewed]

Depends on accepted e05–e09 completion and one immutable candidate revision;
precedes e10s02.

### 19. Out of scope [reviewed]

Live-provider checks, credential-bearing side tests, provider benchmarking,
Linux/Windows qualification, push, or release.

### 20. Definition of done [reviewed]

Evidence generation, completeness, revision-binding, and redaction checks pass
for every required automated gate.

## Implementation Steps

1. Add the automated evidence schema, generator, and validator for the stabilized contracts → verify: `uv run python -m unittest tests.test_release_evidence -v`
2. Generate and validate the revision-bound automated evidence record → verify: `uv run python scripts/validate_release_evidence.py --record specs/verifications/release-evidence.json --revision "$(git rev-parse HEAD)" --required-set automated`
3. Validate completeness, revision binding, redaction, and explicit platform exclusions → verify: `uv run python -m unittest tests.test_release_evidence tests.test_redaction -v`

## Verification Script (Step-by-Step)

1. Freeze and record the exact candidate revision.
2. Run every required automated release gate in a disposable environment.
3. Generate and validate the tracked allowlisted evidence record.
4. Run release-evidence and redaction tests.
5. Confirm the evidence record is reproducible from a clean checkout.
