STORY KEY: e07s02
TITLE:     Verify a provider explicitly without retaining probe content
TYPE:      Story
PARENT:    e07
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      M
type:      feat
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Offline readiness cannot prove current connectivity, while implicit probes would surprise users and risk retaining provider data.

### 2. Value statement [reviewed]

A user can explicitly request a minimal live verification and retain only sanitized historical evidence.

### 3. Actors and permissions [reviewed]

The invoking user authorizes the live operation; injected clients make automated tests offline.

### 4. Trigger and preconditions [reviewed]

e07s01 structured status exists, valid credentials resolve, and live execution has separate explicit authorization.

### 5. Main flow and business logic [reviewed]

Resolve one stored connection, issue the smallest supported request, classify outcome, and atomically store timestamp, outcome, route, and model only.

### 6. Alternative flows and exceptions [reviewed]

Absent/unavailable credentials, timeout, provider error, and profile-write failure produce truthful nonzero or partial results without probe retention.

### 7. Interface elements [reviewed]

`provider verify <profile>` is the only API-provider readiness command allowed to perform a network call.

### 8. Domain model [reviewed]

Historical verification includes timestamp, outcome, route, and model; it explicitly excludes content, account data, credentials, and request identifiers.

### 9. Integrations and boundaries [reviewed]

Reuse the injected OpenAI-compatible client shape already used by `client.chat.completions.create(model=..., messages=...)`; do not enter the agent/tool loop.

### 10. Background processes [reviewed]

None; timeout is bounded and foreground.

### 11. Notifications [reviewed]

Output labels the result as a historical verification, not durable connectivity.

### 12. Audit and logging [reviewed]

Persist the allowlisted fields only and recursively redact errors before presentation.

### 13. Solution variabilities [reviewed]

Probe text and response are intentionally non-durable implementation details; provider-specific special cases are forbidden outside the catalog/service boundary.

### 14. Architecture decisions [reviewed]

Add verification to the connection service with an injected probe client and clock. Reason for Depth: network execution, outcome classification, and metadata persistence must remain testable and separate from command formatting.

### 15. Test strategy [reviewed]

Fake success, failure, timeout, credential states, and persistence errors; scan profiles and streams for sentinel payloads.

### 16. Observability [reviewed]

Show current command outcome and last historical metadata separately.

### 17. Acceptance criteria [reviewed]

#### ADDED: Explicit provider verification

Only an explicit command performs a minimal live probe, and only sanitized historical metadata is retained.

```gherkin
Feature: Explicit provider verification
  Scenario: Verification succeeds
    Given a valid stored API connection and explicit command
    When the fake probe succeeds
    Then success is reported and only timestamp, outcome, route, and model persist

  Scenario: Ordinary status remains offline
    Given the same profile
    When provider status runs
    Then no probe client method is called

  Scenario: Probe contains sensitive sentinels
    Given request, response, and error sentinels
    When verification completes or fails
    Then none appear in profiles, events, summaries, or CLI output
```

### 18. Dependencies and sequencing [reviewed]

Depends on e07s01 and profile schema migration planning. User-run live side
testing is optional and outside e10s01 release evidence.

### 19. Out of scope [reviewed]

Background health checks, retries that hide failure, provider benchmarks, content retention, or status-triggered probes.

### 20. Definition of done [reviewed]

Offline fake-provider, profile migration, redaction, CLI, and security checks pass.

## Implementation Steps

1. Add fake-provider contracts for success, failure, timeout, and unavailable credentials → verify: `uv run python -m unittest tests.test_provider_verification -v`
2. Run a minimal probe only from the explicit command and keep status network-free → verify: `uv run python -m unittest tests.test_provider_verification tests.test_provider_cli -v`
3. Persist only sanitized historical timestamp, outcome, route, and model → verify: `uv run python -m unittest tests.test_provider_verification tests.test_profiles tests.test_redaction -v`

## Verification Script (Step-by-Step)

1. Run all automated scenarios with an injected fake client and clock.
2. Inspect stored profile JSON and both streams for sentinel payloads.
3. Do not run a real provider probe as part of the release workflow; a separately
   requested live side check still requires explicit user authorization.
