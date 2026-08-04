STORY KEY: e05s01
TITLE:     Publish a current finding disposition
TYPE:      Story
PARENT:    e05
STATUS:    Complete
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      M
type:      fix
context:   infra
risk:      P0

### 1. Business narrative [reviewed]

The July readiness review is useful historical evidence, but its findings cannot be treated as the current release verdict after later fixes.

### 2. Value statement [reviewed]

A release owner can determine the current disposition of every reviewed finding from executable, revision-bound evidence.

### 3. Actors and permissions [reviewed]

- Maintainers run offline checks and classify findings.
- User-run live checks remain outside the release contract and do not block work.
- Public artifacts never receive local review records or secrets.

### 4. Trigger and preconditions [reviewed]

Run first on the clean `6f2dc09f4382e7009e1ebadbe3cc4360e6d8bc41`
planning baseline, before implementation changes or release-number selection.

### 5. Main flow and business logic [reviewed]

Create a machine-checkable finding inventory, re-run the applicable automated evidence, and publish one current status and release consequence per finding.

### 6. Alternative flows and exceptions [reviewed]

Missing or stale automated evidence keeps the finding open and cannot be reported as current proof.

### 7. Interface elements [reviewed]

The contract is an offline test plus a secret-free disposition document under `docs/` or `specs/verifications/`.

### 8. Domain model [reviewed]

A disposition contains finding ID, status (`fixed`, `open`, `accepted`, or `deferred`), evidence reference, revision, and release-blocking rationale.

### 9. Integrations and boundaries [reviewed]

Consumes source, tests, lock data, and `scripts/check.sh` without publishing private records.

### 10. Background processes [reviewed]

None; every automated check is foreground and offline.

### 11. Notifications [reviewed]

Failed or incomplete dispositions are explicit test failures and release blockers.

### 12. Audit and logging [reviewed]

Evidence records revision and command, but no credentials, provider payloads, workspace content, or account data.

### 13. Solution variabilities [reviewed]

The evidence file format may be YAML or Markdown if the test parses it deterministically and validates all finding IDs.

### 14. Architecture decisions [reviewed]

Keep the oracle in project tests and data files rather than adding a release framework. Reason for Depth: none; a parser and explicit records are sufficient.

### 15. Test strategy [reviewed]

Start with a failing completeness test, re-run focused regressions and the official check, then validate redaction and revision binding.

### 16. Observability [reviewed]

The disposition summary reports counts by state and names blockers without embedding sensitive evidence.

### 17. Acceptance criteria [reviewed]

#### ADDED: Current finding disposition oracle

Every July finding has exactly one current, evidence-backed disposition tied to the assessed revision.

```gherkin
Feature: Current finding disposition
  Scenario: Every historical finding is classified
    Given the July finding registry
    When the release-baseline contract runs
    Then every finding has one allowed status, current evidence, and release rationale

  Scenario: Evidence is stale or unavailable
    Given evidence from another revision or an unauthorized live probe
    When the finding is evaluated
    Then it is not reported as currently fixed or passed

  Scenario: Evidence is safe to retain
    Given the published disposition
    When redaction checks scan it
    Then no secret-bearing value or private payload is present

  Scenario: Automated evidence is sufficient
    Given the current source, tests, dependencies, and release behavior
    When the disposition is published
    Then every release claim is backed by revision-bound automated evidence or explicit risk treatment
```

### 18. Dependencies and sequencing [reviewed]

First stabilization story; e05s02 and all implementation stories consume its result.

### 19. Out of scope [reviewed]

Fixing findings, running live providers, publishing private review files, or beginning P5.

### 20. Definition of done [reviewed]

All tasks pass, every finding is classified, `scripts/check.sh` passes, and no new security findings exist in affected paths.

## Implementation Steps

1. Add the failing completeness and schema contract for every July finding → verify: `uv run python -m unittest tests.test_release_baseline -v`
2. Revalidate each finding against current source, tests, dependencies, and release behavior → verify: `uv run python -m unittest tests.test_release_baseline -v && ./scripts/check.sh`
3. Publish secret-free outcomes backed by revision-bound automated evidence and explicit risk treatment → verify: `uv run python -m unittest tests.test_release_baseline tests.test_redaction -v`

## Verification Script (Step-by-Step)

1. Run the release-baseline test and confirm an omitted or duplicate finding fails.
2. Run `./scripts/check.sh` from the assessed revision.
3. Inspect the disposition summary for evidence links, revision, and release blockers.
4. Confirm no live or credential-bearing command ran without separate authorization.

## Implementation Result

The executable, secret-free disposition contract is published at
`specs/verifications/current-finding-disposition.json` and validated by
`scripts/verify_release_baseline.py` plus `tests/test_release_baseline.py`.
It classifies all 26 July findings at the assessed revision using automated
evidence and explicit risk treatment. Release-version selection remains at its
human checkpoint.
