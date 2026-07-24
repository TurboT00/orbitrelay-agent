STORY KEY: e04s04
TITLE:     List show and delete sessions
TYPE:      Story
PARENT:    e04
STATUS:    Todo
AUTHOR:    OrbitRelay team           DATE: 2026-07-24
MATURITY:  3
SIZE:      S
type:      feat
context:   domain
risk:      P1

### 1. Business narrative [reviewed]

Users need explicit control to inspect and delete stored sessions under keep-until-delete retention.

### 2. Value statement [reviewed]

Session lifecycle commands list, show (secret-free), delete, and delete-all.

### 3. Actors and permissions [reviewed]

- Local user starts/resumes runs and manages sessions.
- Model produces text/tools; cannot alter event integrity or approval policy.
- OrbitRelay owns event emission, redaction, and storage permissions.

### 4. Trigger and preconditions [reviewed]

- Baseline 0.4.0 agent loop, approvals, and profiles available.
- For session stories: writable ORBITRELAY_HOME test double.

### 5. Main flow and business logic [reviewed]

See acceptance criteria; implementation details deferred to plan-work/TDD.

### 6. Alternative flows and exceptions [reviewed]

Fail closed on corruption, permission errors, and secret-serialization attempts.

### 7. Interface elements [reviewed]

CLI flags/commands finalized in plan-work; must remain secret-free.

### 8. Domain model [reviewed]

Event model and session store types as introduced by e04s01/e04s03.

### 9. Integrations and boundaries [reviewed]

Extends agent loop; composes ProfileStore safety patterns; provider stream at edge only.

### 10. Background processes [reviewed]

Not applicable beyond run lifetime.

### 11. Notifications [reviewed]

Terminal stream/summary only.

### 12. Audit and logging [reviewed]

Events/summaries are the audit surface; no plaintext secret files.

### 13. Solution variabilities [reviewed]

Exact JSON field names and CLI flag spellings are plan-work.

### 14. Architecture decisions [reviewed]

Build minimal OrbitRelay-owned event/session layer; do not adopt heavy frameworks.

### 15. Test strategy [reviewed]

Offline unit/integration tests with fakes; no live network.

### 16. Observability [reviewed]

Events and summaries only.

### 17. Acceptance criteria [reviewed]

```gherkin
Feature: Session lifecycle CLI
  Scenario: List and show sessions
    Given two stored sessions
    When the user lists sessions
    Then both ids appear with timestamps and no secrets
    When the user shows one session
    Then metadata and redacted event summaries are printed

  Scenario: Delete removes session data
    Given a stored session
    When the user deletes it
    Then list no longer includes it and files are gone

  Scenario: Delete-all requires explicit confirmation flag/path tested offline
    Given multiple sessions
    When delete-all is invoked with the required explicit flag
    Then the sessions directory has no session entries
```

### 18. Dependencies and sequencing [reviewed]

e04s01 first; e04s02-e04s06 depend on events; e04s07 last.

### 19. Out of scope [reviewed]

Encryption, auto-TTL, cloud sync, Codex event coupling.

### 20. Definition of done [reviewed]

Tasks green; threat model controls for this story addressed.
