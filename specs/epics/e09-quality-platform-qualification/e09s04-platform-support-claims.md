STORY KEY: e09s04
TITLE:     Publish truthful platform and installation support
TYPE:      Story
PARENT:    e09
STATUS:    Complete
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      S
type:      fix
context:   infra
risk:      P1

### 1. Business narrative [reviewed]

Support claims can drift across package classifiers, README, roadmap, and active state or lead qualification evidence.

### 2. Value statement [reviewed]

Users receive installation guidance that exactly matches the proven Python/platform matrix.

### 3. Actors and permissions [reviewed]

Maintainers update claims only from accepted evidence; users install from the built artifact.

### 4. Trigger and preconditions [reviewed]

e09s03 has complete accepted macOS 3.12–3.14 evidence.

### 5. Main flow and business logic [reviewed]

Update metadata/docs/state from one support matrix and test all claims for consistency and clean first-run behavior.

### 6. Alternative flows and exceptions [reviewed]

Missing Linux evidence keeps Linux preview/unverified; Windows remains deferred.

### 7. Interface elements [reviewed]

README installation/first-run text, package classifiers, roadmap, and active state are the public surfaces.

### 8. Domain model [reviewed]

Platform state is qualified, preview/unverified, or deferred, each with evidence requirements.

### 9. Integrations and boundaries [reviewed]

Touches package metadata, README, roadmap, AGENTS, state, and release-identity tests.

### 10. Background processes [reviewed]

None.

### 11. Notifications [reviewed]

Installation guidance names the proven floor and platform status without marketing overclaim.

### 12. Audit and logging [reviewed]

Claims link to sanitized evidence, not credentials or private payloads.

### 13. Solution variabilities [reviewed]

No external package is proposed.

### 14. Architecture decisions [reviewed]

Keep support truth in package metadata plus active state and validate mirrors. Reason for Depth: none; a new support registry would duplicate current release metadata.

### 15. Test strategy [reviewed]

Parse metadata/docs/state for consistency and run clean installation/first-run smoke through the matrix.

### 16. Observability [reviewed]

The matrix and release audit show the evidence behind each claim.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Platform and installation claims

**Before:** Python/platform claims are incomplete or can drift from package metadata and current evidence.

**After:** macOS is qualified on proven Python 3.12–3.14, Linux is preview/unverified, Windows is deferred, and all installation surfaces agree.

```gherkin
Feature: Truthful support claims
  Scenario: Project surfaces agree
    When consistency tests parse metadata, README, roadmap, and state
    Then Python and platform claims are identical

  Scenario: Clean macOS install
    Given the selected wheel and supported minor
    When a user follows README guidance
    Then import, command, and first-run guidance work

  Scenario: Unverified platform
    Given no accepted Linux or Windows evidence
    Then no surface describes either as qualified
```

### 18. Dependencies and sequencing [reviewed]

Depends on e09s03 and e05s02; precedes e10 re-audit/candidate.

### 19. Out of scope [reviewed]

Linux/Windows qualification, new installers, Homebrew, or provider capability claims.

### 20. Definition of done [reviewed]

Identity/claim consistency and clean matrix smoke pass with no security regression.

## Implementation Steps

1. Add consistency checks across classifiers, README, roadmap, and state → verify: `uv run python -m unittest tests.test_release_identity -v`
2. Publish macOS qualified, Linux preview, and Windows deferred claims → verify: `uv run python -m unittest tests.test_release_identity -v`
3. Verify clean macOS installation/first-run guidance against the selected artifact → verify: `./scripts/check-python-matrix.sh`

## Verification Script (Step-by-Step)

1. Run the identity consistency test and inspect every support surface.
2. Follow README installation steps with the isolated wheel on each supported minor.
3. Confirm no unverified platform is described as qualified.

