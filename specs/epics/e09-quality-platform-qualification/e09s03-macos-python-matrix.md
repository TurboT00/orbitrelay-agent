STORY KEY: e09s03
TITLE:     Install and run OrbitRelay on Python 3.12 through 3.14
TYPE:      Story
PARENT:    e09
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      L
type:      feat
context:   infra
risk:      P0

### 1. Business narrative [reviewed]

OrbitRelay declares Python 3.14+ without evidence that a lower floor is necessary, narrowing macOS installation.

### 2. Value statement [reviewed]

Users receive a proven macOS Python 3.12–3.14 support range backed by one lock, complete tests, quality gates, build, wheel smoke, and credential checks.

### 3. Actors and permissions [reviewed]

Maintainers run automated matrix jobs; authorized operators run native credential checks in disposable environments.

### 4. Trigger and preconditions [reviewed]

e05s02 identity and e09s01/e09s02 gates are complete; D-04 forbids metadata change before every minor passes.

### 5. Main flow and business logic [reviewed]

Generate a disposable candidate manifest/lock without changing tracked metadata, run the full automated matrix on 3.12/3.13/3.14, collect separately authorized macOS credential evidence, then apply the proven candidate metadata/lock and rerun.

### 6. Alternative flows and exceptions [reviewed]

Any minor failure blocks metadata change until fixed or a new explicit product decision is approved.

### 7. Interface elements [reviewed]

`scripts/check-python-matrix.sh` can stage a disposable candidate floor for qualification, run the complete per-minor contract, validate an explicit local evidence record, and report each interpreter/stage.

### 8. Domain model [reviewed]

A matrix result records OS, architecture, Python minor, lock revision, stage results, artifact identity, and authorized credential evidence reference.

### 9. Integrations and boundaries [reviewed]

Touches a temporary candidate `requires-python`/classifiers/lock, then the accepted tracked metadata and lock, dependencies, examples, quality tools, build, entry points, and separately authorized keyring checks.

### 10. Background processes [reviewed]

None; matrix stages are sequential or isolated and bounded.

### 11. Notifications [reviewed]

The matrix names the exact interpreter and failed stage.

### 12. Audit and logging [reviewed]

Credential evidence records outcome only and follows the local sanitized runbook.

### 13. Solution variabilities [reviewed]

`uv` [OK] and Hatchling [OK] remain the lock/build tools. The provisional candidate lock lives only in the disposable qualification checkout until acceptance; no permanent second lock or packaging backend is proposed.

### 14. Architecture decisions [reviewed]

Use one script parameterized by interpreter and candidate floor, not three divergent scripts. Reason for Depth: one sequence prevents per-minor gate drift while keeping provisional metadata and environments isolated.

### 15. Test strategy [reviewed]

For every minor: candidate lock/sync, import, full tests, examples, Ruff, mypy, coverage/audits, build, isolated wheel, and both entry points; validate separately authorized per-minor keyring evidence before tracked metadata changes.

### 16. Observability [reviewed]

Produce a concise matrix table and revision-bound evidence paths.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Supported Python floor

**Before:** Package metadata and classifier require Python 3.14 without a 3.12/3.13 qualification matrix.

**After:** Metadata declares Python 3.12–3.14 only after every macOS minor passes the complete locked release contract.

```gherkin
Feature: macOS Python compatibility matrix
  Scenario: Every declared minor passes
    Given one lock and Python 3.12, 3.13, and 3.14 on macOS
    When the matrix runs
    Then every disposable-candidate test, quality, build, wheel, and CLI stage passes and authorized credential evidence is complete

  Scenario: One minor fails
    When any required stage fails
    Then metadata remains at the previous floor and release is blocked

  Scenario: Metadata changes
    Given complete accepted matrix evidence
    When the floor is lowered
    Then lock, classifiers, docs, and installed behavior remain consistent

  Scenario: Provisional qualification
    Given tracked metadata still requires Python 3.14
    When the candidate-floor matrix runs
    Then only a disposable checkout receives the provisional 3.12 metadata and tracked files remain unchanged
```

### 18. Dependencies and sequencing [reviewed]

Depends on e05s02, e09s01, and e09s02; precedes e09s04 and e10.

### 19. Out of scope [reviewed]

Qualified Linux/Windows, alternative package managers, multiple locks, or metadata-first experimentation.

### 20. Definition of done [reviewed]

All three minors pass the full matrix and metadata changes only afterward with no security regression.

## Implementation Steps

1. Add contracts and a disposable candidate-manifest/lock procedure that leaves tracked Python 3.14 metadata unchanged → verify: `uv run python -m unittest tests.test_python_matrix -v`
2. Run complete automated tests, quality, build, wheel, and CLI checks against the disposable 3.12-floor candidate on every minor → verify: `./scripts/check-python-matrix.sh --candidate-floor 3.12 --automated-only`
3. Validate separately authorized per-minor credential evidence, apply the proven candidate metadata/lock, and rerun the committed matrix → verify: `uv run python -m unittest tests.test_release_identity tests.test_python_matrix -v && ./scripts/check-python-matrix.sh --evidence-file docs/manual-test-results-stabilization.md --require-credential-evidence`

## Verification Script (Step-by-Step)

1. Verify all three interpreters are available and tracked metadata still requires Python 3.14.
2. Run the disposable candidate-floor matrix and confirm it leaves tracked files unchanged.
3. Obtain separate authorization for per-minor native credential checks and record sanitized results in the local evidence file.
4. Apply the proven candidate metadata/lock only after both automated and required manual evidence pass, then rerun the committed matrix.
