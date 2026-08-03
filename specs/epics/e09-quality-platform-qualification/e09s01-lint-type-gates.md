STORY KEY: e09s01
TITLE:     Run lint and typing as terminal release gates
TYPE:      Story
PARENT:    e09
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      M
type:      fix
context:   infra
risk:      P0

### 1. Business narrative [reviewed]

The official check can pass while lint or type regressions exist outside the test suite.

### 2. Value statement [reviewed]

Maintainers get reproducible, terminal Ruff and mypy failures before broad stabilization changes accumulate.

### 3. Actors and permissions [reviewed]

Developers and release automation run locked offline-capable tools; tests retain injectable boundaries.

### 4. Trigger and preconditions [reviewed]

Current recorded Ruff/mypy findings are clear, and `uv.lock` remains authoritative.

### 5. Main flow and business logic [reviewed]

Lock tools/config, resolve current findings without broad suppression, and insert both commands as fail-fast `scripts/check.sh` stages.

### 6. Alternative flows and exceptions [reviewed]

Missing tools, config errors, or findings fail the gate with actionable output; no fail-open `|| true` paths are allowed.

### 7. Interface elements [reviewed]

Developer commands are `uv run ruff check .` and `uv run mypy src/orbitrelay`; the official check invokes both.

### 8. Domain model [reviewed]

A quality stage has locked tool identity, command, scope, and terminal pass/fail result.

### 9. Integrations and boundaries [reviewed]

Touches `pyproject.toml`, `uv.lock`, production typing, test doubles, and `scripts/check.sh`.

### 10. Background processes [reviewed]

None.

### 11. Notifications [reviewed]

The check names the failing stage and preserves the command exit status.

### 12. Audit and logging [reviewed]

Tool output contains source diagnostics only and no runtime credentials.

### 13. Solution variabilities [reviewed]

Ruff [OK] and mypy [OK] are mature, scoped development tools; broad ignores and untyped escape hatches require review.

### 14. Architecture decisions [reviewed]

Configure tools in `pyproject.toml` and keep shell orchestration linear. Reason for Depth: none; separate framework/config layers would not improve the gate.

### 15. Test strategy [reviewed]

Run each tool independently, the project suite, and the official check; preserve injected clients/stores/runners.

### 16. Observability [reviewed]

Check output clearly identifies lint and typing stages.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Official release check

**Before:** `scripts/check.sh` does not run Ruff or mypy and can pass despite their findings.

**After:** Locked Ruff and mypy checks are terminal stages, current findings are resolved, and either regression fails the official check.

```gherkin
Feature: Terminal lint and type gates
  Scenario: Clean source passes
    When Ruff, mypy, tests, and the official check run
    Then every stage exits zero

  Scenario: Lint regression exists
    Given a controlled lint fixture
    When the official check runs
    Then it exits nonzero at the lint stage

  Scenario: Type regression exists
    Given a controlled type fixture
    When the official check runs
    Then it exits nonzero at the typing stage
```

### 18. Dependencies and sequencing [reviewed]

Land immediately after e05s01 so later implementation runs under the gate.

### 19. Out of scope [reviewed]

Formatting rewrites, broad suppressions, coverage/audit/security policy, or CI-provider configuration.

### 20. Definition of done [reviewed]

Ruff, mypy, project tests, lock check, official check, and affected-path security review pass.

## Implementation Steps

1. Lock/configure Ruff and mypy without broad suppressions → verify: `uv run ruff check . && uv run mypy src/orbitrelay`
2. Resolve current findings while preserving runtime/test contracts → verify: `uv run ruff check . && uv run mypy src/orbitrelay && uv run python -m unittest discover -s tests -v`
3. Make the official check fail on either regression → verify: `./scripts/check.sh`

## Verification Script (Step-by-Step)

1. Run both tools independently and inspect configured scope.
2. Run the full offline test suite.
3. Use controlled fixtures to prove each gate fails, then restore and run `scripts/check.sh`.

