STORY KEY: e07s04
TITLE:     Disconnect and log out of Codex with explicit ownership
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

OrbitRelay metadata and official Codex authentication have different owners, so unclear disconnect/logout behavior can mutate the wrong state.

### 2. Value statement [reviewed]

Users can remove OrbitRelay metadata, delegate logout, or explicitly combine them with truthful partial-result handling.

### 3. Actors and permissions [reviewed]

OrbitRelay owns profile/selection metadata; the official CLI exclusively owns authentication.

### 4. Trigger and preconditions [reviewed]

D-05 is authoritative and e07s03 supplies normalized delegated outcomes.

### 5. Main flow and business logic [reviewed]

Plain disconnect removes metadata only; plain logout delegates only; combined `logout --disconnect` logs out first and removes metadata only after success.

### 6. Alternative flows and exceptions [reviewed]

Logout failure leaves metadata unchanged; later metadata-removal failure reports a partial result and recovery guidance; no automatic provider selection occurs.

### 7. Interface elements [reviewed]

`provider disconnect codex`, `orbitrelay codex logout`, and `orbitrelay codex logout --disconnect` have distinct help and outcomes.

### 8. Domain model [reviewed]

Lifecycle outcome records official-auth result, metadata result, selection result, completeness, and safe recovery action.

### 9. Integrations and boundaries [reviewed]

Touches provider CLI, Codex CLI/bridge, profile repository, selection, connection service, and e06s05 errors.

### 10. Background processes [reviewed]

Official logout is a bounded foreground subprocess.

### 11. Notifications [reviewed]

Every unchanged, complete, or partial state is stated on stderr/stdout according to CLI result rules.

### 12. Audit and logging [reviewed]

No official credentials or raw account output are inspected, stored, or printed.

### 13. Solution variabilities [reviewed]

Partial operations are explicit results, not rollback claims across ownership domains.

### 14. Architecture decisions [reviewed]

Use a small lifecycle-result value at the command boundary. Reason for Depth: the two owners cannot share a transaction, so callers need a precise partial-state contract.

### 15. Test strategy [reviewed]

Cover the full logout/metadata/selection success-failure matrix with injected runner and repositories.

### 16. Observability [reviewed]

Report what changed, what did not, and the safe recovery command.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Codex disconnect and logout ownership

**Before:** Metadata disconnect and official logout semantics are not fully separated or transactionally described.

**After:** Plain operations affect only their owner; the explicit combined operation is logout-first with truthful partial results and no fallback selection.

```gherkin
Feature: Codex lifecycle ownership
  Scenario: Metadata-only disconnect
    When provider disconnect codex runs
    Then OrbitRelay metadata/selection are updated and official authentication is untouched

  Scenario: Plain delegated logout
    When codex logout succeeds without --disconnect
    Then official authentication changes and OrbitRelay metadata remains

  Scenario: Combined operation is partial
    Given logout succeeds and metadata removal fails
    When logout --disconnect runs
    Then the partial result and recovery guidance are reported without fallback selection
```

### 18. Dependencies and sequencing [reviewed]

Depends on e07s03 and e06s05; profile repository concurrency guarantees remain intact.

### 19. Out of scope [reviewed]

Credential inspection, automatic provider fallback, cross-owner rollback, or logging into Codex.

### 20. Definition of done [reviewed]

Lifecycle matrix, profile, connection, CLI stream, redaction, and security tests pass.

## Implementation Steps

1. Add lifecycle contracts for metadata disconnect, logout, and combined operation → verify: `uv run python -m unittest tests.test_provider_cli tests.test_codex_bridge -v`
2. Keep plain disconnect and plain logout within their ownership boundaries → verify: `uv run python -m unittest tests.test_provider_cli tests.test_codex_bridge tests.test_connection_service -v`
3. Execute combined logout-first and report complete/unchanged/partial states truthfully → verify: `uv run python -m unittest tests.test_provider_cli tests.test_codex_bridge tests.test_cli_connections -v`

## Verification Script (Step-by-Step)

1. Run the injected success/failure matrix for official logout and metadata removal.
2. Assert exact profile/selection state after every branch.
3. Confirm the official credential boundary and no automatic fallback selection.
