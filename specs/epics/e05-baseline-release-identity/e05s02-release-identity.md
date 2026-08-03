STORY KEY: e05s02
TITLE:     Identify a reproducible stabilization candidate
TYPE:      Story
PARENT:    e05
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      M
type:      fix
context:   infra
risk:      P0

### 1. Business narrative [reviewed]

Post-0.5.0 code still reports 0.5.0, so source, package, and installed command do not identify a distinct candidate.

### 2. Value statement [reviewed]

A maintainer can build one artifact whose package, module, CLI, documentation, and evidence agree on the selected post-0.5.0 identity.

### 3. Actors and permissions [reviewed]

Maintainers select the identifier from e05s01 compatibility evidence; release and publish authority remain separate.

### 4. Trigger and preconditions [reviewed]

e05s01 is accepted and the compatibility effect of post-0.5.0 breaking provider commits is recorded.

### 5. Main flow and business logic [reviewed]

Write failing identity contracts, select the semantically justified version, update one source of truth and consumers, then test an isolated wheel.

### 6. Alternative flows and exceptions [reviewed]

If compatibility evidence cannot justify a version, leave the candidate version unset and block the release rather than guessing.

### 7. Interface elements [reviewed]

`orbitrelay --version`, module/package metadata, wheel metadata, and operator docs expose the same value.

### 8. Domain model [reviewed]

Release identity is one semantic version plus the immutable candidate revision recorded in evidence.

### 9. Integrations and boundaries [reviewed]

Touches `pyproject.toml`, `src/orbitrelay/__init__.py`, CLI parsing, Hatchling build output, README, roadmap, and active state.

### 10. Background processes [reviewed]

None.

### 11. Notifications [reviewed]

Identity drift fails tests and the release check.

### 12. Audit and logging [reviewed]

Build evidence records version, revision, artifact hash, and command only.

### 13. Solution variabilities [reviewed]

The selected version is an output of e05s01; the plan does not pre-authorize a major, minor, or patch bump.

### 14. Architecture decisions [reviewed]

Use one package-owned version source and derive CLI/module output from it. Reason for Depth: a shared constant prevents metadata drift without introducing a version service.

### 15. Test strategy [reviewed]

Assert source and built metadata consistency, both entry points, and isolated-wheel behavior.

### 16. Observability [reviewed]

`--version` writes the identity to stdout with no credential-store initialization.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Release identity

**Before:** Post-release source, package metadata, and commands still identify as 0.5.0 or expose no version command.

**After:** One evidence-selected post-0.5.0 version is consistent in source, package metadata, both CLI entry points, documentation, and the installed wheel.

```gherkin
Feature: Reproducible release identity
  Scenario: Source identity is consistent
    Given the selected stabilization version
    When identity contracts inspect package, module, and CLI output
    Then every surface reports the same version

  Scenario: Installed identity is consistent
    Given a wheel built from a clean checkout
    When its command runs in isolation
    Then it reports the selected version

  Scenario: Version selection lacks evidence
    Given no accepted compatibility disposition
    When release identity is evaluated
    Then the candidate remains blocked instead of guessing a version
```

### 18. Dependencies and sequencing [reviewed]

Depends on e05s01; precedes e09s03, e09s04, e10s02, and e10s03.

### 19. Out of scope [reviewed]

Tagging, publishing, pushing, release creation, or changing provider behavior.

### 20. Definition of done [reviewed]

All identity tests and the isolated-wheel check pass with no new security findings in affected paths.

## Implementation Steps

1. Add failing package, module, and CLI identity contracts → verify: `uv run python -m unittest tests.test_release_identity -v`
2. Select and expose the evidence-backed post-0.5.0 identifier without provider behavior changes → verify: `uv run python -m unittest tests.test_release_identity tests.test_cli_connections -v`
3. Prove a clean checkout builds an isolated artifact with the selected identity → verify: `./scripts/check.sh`

## Verification Script (Step-by-Step)

1. Read the accepted e05s01 compatibility disposition.
2. Run the identity tests and compare package, module, and command output.
3. Run `./scripts/check.sh` and inspect the isolated-wheel smoke result.
4. Confirm no tag, release, publish, or push occurred.
