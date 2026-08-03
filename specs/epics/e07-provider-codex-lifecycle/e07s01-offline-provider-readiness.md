STORY KEY: e07s01
TITLE:     Inspect API-provider readiness offline
TYPE:      Story
PARENT:    e07
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      L
type:      fix
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

The current “connected” label conflates stored metadata, credential availability, selection, and actual readiness.

### 2. Value statement [reviewed]

A user can inspect conservative local facts without contacting a provider or exposing credentials.

### 3. Actors and permissions [reviewed]

Users inspect status; provider catalog, profile repository, and credential backend supply independent facts.

### 4. Trigger and preconditions [reviewed]

D-02 is authoritative; provider listing remains metadata-only and keyring-free.

### 5. Main flow and business logic [reviewed]

Collect configured, selected, catalog/model, and credential facts, then derive only `local-ready`, `not-ready`, or `unknown`.

### 6. Alternative flows and exceptions [reviewed]

Credential-backend failure reports `unavailable` and readiness `unknown`; it is never collapsed into absent or success.

### 7. Interface elements [reviewed]

`provider status` prints structured offline facts; `provider list` retains its metadata-only behavior.

### 8. Domain model [reviewed]

Credential state is `present`, `absent`, or `unavailable`; readiness is `local-ready`, `not-ready`, or `unknown`.

### 9. Integrations and boundaries [reviewed]

Touches provider catalog, profiles, credentials, connection service, provider CLI, and top-level dispatch.

### 10. Background processes [reviewed]

None; no network request is permitted.

### 11. Notifications [reviewed]

Status output separates each fact and gives safe recovery guidance.

### 12. Audit and logging [reviewed]

No credential values, provider payloads, keyring exception details, or account data are printed or stored.

### 13. Solution variabilities [reviewed]

Human-readable output is primary; structured internal facts must remain independently testable.

### 14. Architecture decisions [reviewed]

Introduce one provider-readiness value object populated at the connection-service boundary. Reason for Depth: API and delegated routes need a shared truthful vocabulary while retaining different credential owners.

### 15. Test strategy [reviewed]

Use fake profile and credential stores to cover the full fact-state matrix and assert zero network calls.

### 16. Observability [reviewed]

Status is observable CLI output but not a current-connectivity claim.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: API-provider status

**Before:** Provider output can call metadata “connected” and cannot distinguish absent from unavailable credentials.

**After:** Offline status reports independent facts and derives only conservative readiness states without network access.

```gherkin
Feature: Offline provider readiness
  Scenario: Local facts support readiness
    Given valid catalog metadata, selected profile, and present credentials
    When status runs offline
    Then the facts are reported and readiness is local-ready

  Scenario: Credential backend is unavailable
    Given a valid profile and unavailable keyring
    When status runs
    Then credential state and readiness are unknown without a traceback

  Scenario: Listing providers
    When provider list runs
    Then it does not initialize the credential backend or contact a provider
```

### 18. Dependencies and sequencing [reviewed]

Depends on e05s01 and e09s01; precedes e07s02 and supplies vocabulary for e07s03.

### 19. Out of scope [reviewed]

Implicit live checks, credential repair, new provider routes, or account inspection.

### 20. Definition of done [reviewed]

Provider, connection, credential, CLI, and security tests pass offline.

## Implementation Steps

1. Add contracts for configured, selected, catalog/model, and three-state credential facts → verify: `uv run python -m unittest tests.test_provider_cli tests.test_connection_service -v`
2. Derive conservative readiness without network access or credential exposure → verify: `uv run python -m unittest tests.test_provider_cli tests.test_connection_service tests.test_credentials -v`
3. Keep provider listing keyring-free and make status tolerate backend absence/unavailability → verify: `uv run python -m unittest tests.test_provider_cli tests.test_cli_connections -v`

## Verification Script (Step-by-Step)

1. Run the status matrix with fake profiles and credential stores.
2. Assert no fake provider client receives a request.
3. Run provider list with a credential-store factory that would fail if initialized.

