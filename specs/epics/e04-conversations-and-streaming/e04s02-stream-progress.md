STORY KEY: e04s02
TITLE:     Stream model tokens and tool progress
TYPE:      Story
PARENT:    e04
STATUS:    Todo
AUTHOR:    OrbitRelay team           DATE: 2026-07-24
MATURITY:  3
SIZE:      L
type:      feat
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Users cannot see progressive model output or tool progress during long runs. Streaming must opt-in without breaking scripts.

### 2. Value statement [reviewed]

An opted-in stream shows token/text deltas and tool-progress events live while remaining secret-free.

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
Feature: Streaming progress
  Scenario: Opt-in stream prints model deltas
    Given a fake streaming model yielding text deltas then completion
    When the user runs with streaming enabled
    Then deltas are emitted before run.completed
    And the final printed answer matches the assembled text

  Scenario: Default non-stream still works
    Given streaming is not enabled
    When the user runs a normal prompt
    Then only the final answer is printed to stdout by default

  Scenario: Tool progress events stream without raw secrets
    Given a model tool round during a streamed run
    When tools execute
    Then tool.progress/tool.result events reach the sink without credential leakage
```

### 18. Dependencies and sequencing [reviewed]

e04s01 first; e04s02-e04s06 depend on events; e04s07 last.

### 19. Out of scope [reviewed]

Encryption, auto-TTL, cloud sync, Codex event coupling.

### 20. Definition of done [reviewed]

Tasks green; threat model controls for this story addressed.
