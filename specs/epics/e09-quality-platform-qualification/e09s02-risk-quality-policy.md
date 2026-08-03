STORY KEY: e09s02
TITLE:     Enforce coverage dependency and security policy
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

Passing tests do not currently enforce branch coverage, vulnerable dependencies, or common Python source-security findings.

### 2. Value statement [reviewed]

Release owners receive reproducible, independently failing risk gates with explicit baseline and waiver policy.

### 3. Actors and permissions [reviewed]

Developers run locked tools; release owners approve documented waivers; scanners never contact live providers.

### 4. Trigger and preconditions [reviewed]

Focused e06/e07/e08 regressions exist and e09s01 terminal stages are active.

### 5. Main flow and business logic [reviewed]

Measure baselines, select thresholds/policies, lock tools, add fail-fast stages, and prove each stage fails independently.

### 6. Alternative flows and exceptions [reviewed]

Audit-database unavailability is explicit and cannot silently pass; waivers are scoped, expiring, justified records.

### 7. Interface elements [reviewed]

`scripts/check.sh` reports coverage, dependency audit, and source-security stages with recovery commands.

### 8. Domain model [reviewed]

A gate policy records tool/version, scope, threshold/rule set, baseline, waiver, and terminal result.

### 9. Integrations and boundaries [reviewed]

Touches development dependencies, `uv.lock`, `pyproject.toml`, quality fixtures, tests, and official check.

### 10. Background processes [reviewed]

None; any advisory database access follows documented cache/network behavior and is not a provider test.

### 11. Notifications [reviewed]

Failure output names the specific gate and actionable finding without secret-bearing runtime data.

### 12. Audit and logging [reviewed]

Waivers and baselines are versioned; scanner output is secret-free project metadata.

### 13. Solution variabilities [reviewed]

coverage.py [OK], pip-audit [OK], and Bandit [OK] are mature scoped tools. Thresholds are selected from measured accepted baseline and recorded as named policy, never hidden defaults.

### 14. Architecture decisions [reviewed]

Keep independent linear check stages plus focused regression fixtures. Reason for Depth: a quality framework would obscure each tool's exit status and fail-open risk.

### 15. Test strategy [reviewed]

Create isolated controlled failures for below-threshold coverage, vulnerable dependency fixture, source finding, unavailable audit data, and waiver expiry.

### 16. Observability [reviewed]

The gate summary reports measured coverage and scanner/audit outcome by stage.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Release quality policy

**Before:** The official check has no terminal coverage, dependency-audit, or source-security policy.

**After:** Locked tools enforce documented measured thresholds/rules, each gate fails independently, and no passing unit suite can bypass them.

```gherkin
Feature: Risk-based quality policy
  Scenario: Accepted baseline passes
    When all quality stages run on accepted source
    Then coverage meets policy and audit/security stages pass

  Scenario: One gate regresses
    Given a controlled regression for one stage
    When the official check runs
    Then it exits nonzero even when unit tests pass

  Scenario: Audit evidence unavailable
    When required advisory data cannot be obtained or cached
    Then the result is explicit and does not silently pass
```

### 18. Dependencies and sequencing [reviewed]

Depends on e09s01 and focused e06/e07/e08 tests; precedes e09s03 and e10.

### 19. Out of scope [reviewed]

Paid scanners, live credentials, arbitrary score chasing, CI-vendor setup, or permanent broad waivers.

### 20. Definition of done [reviewed]

Quality-gate regressions and the official check pass with no new security findings in affected paths.

## Implementation Steps

1. Define measured coverage, dependency, and source-security policy with locked tools → verify: `uv run python -m unittest tests.test_quality_gate -v`
2. Add all stages to the official check with actionable terminal failures → verify: `./scripts/check.sh`
3. Prove each new gate fails independently of a passing unit suite → verify: `uv run python -m unittest tests.test_quality_gate -v`

## Verification Script (Step-by-Step)

1. Record current branch coverage and scanner/audit baselines.
2. Review selected thresholds, rules, cache behavior, and waiver format.
3. Run every controlled regression independently, then run `scripts/check.sh` cleanly.

