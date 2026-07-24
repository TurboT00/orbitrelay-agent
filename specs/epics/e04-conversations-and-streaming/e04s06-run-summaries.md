STORY KEY: e04s06
TITLE:     Emit structured run summaries
TYPE:      Story
PARENT:    e04
STATUS:    Done
AUTHOR:    OrbitRelay team           DATE: 2026-07-24
MATURITY:  3
SIZE:      S
type:      feat
context:   domain
risk:      P1

### 1. Business narrative [reviewed]

Operators need a compact end-of-run summary for terminals and later telemetry without scraping logs.

### 2. Value statement [reviewed]

Each run can emit a structured summary with status, usage, tool counts, and error codes—secret-free.

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
Feature: Run summaries
  Scenario: Successful run summary
    Given a completed run with tools and usage
    When the summary is produced
    Then it includes status=completed, response_count, tool counts, and usage fields
    And it excludes secrets

  Scenario: Failed run summary
    Given a run that ends in provider error
    When the summary is produced
    Then status reflects failure and error_code is present
```

### 18. Dependencies and sequencing [reviewed]

e04s01 first; e04s02-e04s06 depend on events; e04s07 last.

### 19. Out of scope [reviewed]

Encryption, auto-TTL, cloud sync, Codex event coupling.

### 20. Definition of done [reviewed]

Tasks green; threat model controls for this story addressed.
