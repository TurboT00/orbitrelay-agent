STORY KEY: e07s03
TITLE:     Inspect delegated Codex readiness without account leakage
TYPE:      Story
PARENT:    e07
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      M
type:      fix
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Codex authentication belongs to the official CLI, but OrbitRelay still needs conservative local status without relaying raw account output.

### 2. Value statement [reviewed]

A user can distinguish installation, delegated authentication, selection, and readiness while OrbitRelay never reads Codex credentials.

### 3. Actors and permissions [reviewed]

The official Codex CLI owns authentication; OrbitRelay invokes documented status commands and normalizes outcomes only.

### 4. Trigger and preconditions [reviewed]

D-02 and the existing subprocess runner/argv boundary remain authoritative.

### 5. Main flow and business logic [reviewed]

Detect installation/version, perform the delegated login-state check, normalize known outcomes, and map unclear failures to unknown.

### 6. Alternative flows and exceptions [reviewed]

Missing binary, timeout, nonzero status, or unrecognized output never becomes authenticated and never relays raw account text.

### 7. Interface elements [reviewed]

Provider status presents Codex with the same fact/readiness vocabulary as API providers while retaining delegated labels.

### 8. Domain model [reviewed]

Installation and authentication facts are independent; readiness is local-ready, not-ready, or unknown.

### 9. Integrations and boundaries [reviewed]

Touches `codex_bridge.py`, `codex_cli.py`, provider CLI, redaction, and connection selection metadata.

### 10. Background processes [reviewed]

Subprocess checks are foreground and bounded.

### 11. Notifications [reviewed]

Output gives recovery commands without copying account details.

### 12. Audit and logging [reviewed]

Store no Codex status output, account data, tokens, or credential locations.

### 13. Solution variabilities [reviewed]

Unknown official output maps to unknown until a sanitized fixture documents it.

### 14. Architecture decisions [reviewed]

Normalize at the Codex bridge and return structured facts to provider presentation. Reason for Depth: the bridge alone may interpret official CLI output while higher layers remain credential-agnostic.

### 15. Test strategy [reviewed]

Fixture missing, authenticated, unauthenticated, unknown, timeout, and sensitive raw outputs through an injected runner.

### 16. Observability [reviewed]

Only normalized facts and bounded safe diagnostics leave the bridge.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Delegated Codex status

**Before:** Codex status is CLI-oriented and may expose raw output rather than provider-ready facts.

**After:** OrbitRelay reports normalized installation and authentication facts without reading credentials or relaying account output.

```gherkin
Feature: Delegated Codex readiness
  Scenario: Official CLI is authenticated
    Given a sanitized authenticated result
    When provider status inspects Codex
    Then installation, authentication, selection, and local readiness are reported

  Scenario: Official output is unknown
    Given unrecognized or failed status output
    When it is normalized
    Then authentication/readiness are unknown, not successful

  Scenario: Raw output contains account data
    When status completes
    Then account data is absent from OrbitRelay output and storage
```

### 18. Dependencies and sequencing [reviewed]

Uses e07s01 status vocabulary; precedes e07s04 and e08s05 Codex output limits.

### 19. Out of scope [reviewed]

Reading Codex credential files, interpreting subscription entitlements, or replacing the official CLI.

### 20. Definition of done [reviewed]

Codex bridge, provider CLI, redaction, connection, and security checks pass.

## Implementation Steps

1. Add delegated readiness fixtures for missing, authenticated, unauthenticated, and unknown outcomes → verify: `uv run python -m unittest tests.test_codex_bridge tests.test_provider_cli -v`
2. Normalize installation/login checks without credential reads or raw account output → verify: `uv run python -m unittest tests.test_codex_bridge tests.test_provider_cli tests.test_redaction -v`
3. Present delegated facts consistently beside API-provider facts → verify: `uv run python -m unittest tests.test_provider_cli tests.test_cli_connections -v`

## Verification Script (Step-by-Step)

1. Run all injected Codex runner fixtures offline.
2. Compare API and Codex status labels for consistency.
3. Scan output and storage for raw account sentinels.
