STORY KEY: e08s04
TITLE:     Bound resumable history without splitting tool pairs
TYPE:      Story
PARENT:    e08
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      L
type:      fix
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Outbound context is bounded, but persisted messages/events grow in repeatedly rewritten files and resume can retain stale system instructions.

### 2. Value statement [reviewed]

Long sessions use bounded segments and replay memory without deleting durable user history, splitting tool groups, or retaining stale system instructions.

### 3. Actors and permissions [reviewed]

Users retain resumable recent history; OrbitRelay applies deterministic bounds before provider access.

### 4. Trigger and preconditions [reviewed]

e08s02 generation checkpoints and current `context_budget.py` pair preservation are available.

### 5. Main flow and business logic [reviewed]

Measure the current baseline, select documented limits, append bounded message/event segments, load only a complete-group replay window, and inject current system instructions separately.

### 6. Alternative flows and exceptions [reviewed]

A single indivisible group may occupy its own bounded segment; unsafe legacy forms fail before provider access and no automatic history deletion occurs.

### 7. Interface elements [reviewed]

Resume diagnostics report migration, segment, and replay-window state without exposing content.

### 8. Domain model [reviewed]

Durable history is segmented messages/events kept until user deletion; replay groups are atomic user/assistant/tool units with correlated IDs and unknown provider fields preserved; current system instructions are run configuration rather than durable conversation.

### 9. Integrations and boundaries [reviewed]

Touches session message/event storage, context budget, current prompts, streaming extension replay, checkpoints, and CLI errors.

### 10. Background processes [reviewed]

None.

### 11. Notifications [reviewed]

Limit selection is documented; migration/rejection and current-instruction replacement are explicit before a provider request.

### 12. Audit and logging [reviewed]

Record segment/replay counts, bytes, and migration outcome, not conversation content.

### 13. Solution variabilities [reviewed]

Exact segment, event, and replay-memory bounds are selected from measured baseline during RED tests and become named constants plus documented contracts, not hidden literals.

### 14. Architecture decisions [reviewed]

Reuse one replay-group partitioner for segmented storage and outbound replay, while storing events in aligned bounded segments. Reason for Depth: independent segment/replay logic could disagree, orphan tool results, or load stale instructions.

### 15. Test strategy [reviewed]

Generate long messages/events with multi-call tool groups, extension fields, legacy system messages, oversized groups, and repeated resumes.

### 16. Observability [reviewed]

Expose segment counts, replayed/omitted group counts, event counts, and safe migration status.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Retained and replayed session history

**Before:** Outbound history is bounded, while messages/events grow in rewritten files and persisted system instructions can be replayed after safety guidance changes.

**After:** Named measured limits bound segment/file size and resume memory, full durable history remains until user deletion, replay uses complete groups, events are segmented, current system instructions replace persisted old instructions, and valid old sessions migrate deterministically.

```gherkin
Feature: Bounded session history
  Scenario: Long history is segmented and replay is bounded
    Given messages and events beyond the selected segment and memory bounds
    When the session checkpoints or resumes
    Then durable groups remain in bounded segments and only complete recent groups enter provider context

  Scenario: Provider extension fields survive
    Given unknown assistant fields in retained groups
    When history is bounded
    Then those fields are preserved byte-for-value

  Scenario: Current safety instructions win
    Given a legacy session with a persisted system message
    When it resumes under a newer OrbitRelay version
    Then current system instructions are injected and the old system message is not replayed as current instruction

  Scenario: Legacy form cannot migrate safely
    When resume validates it
    Then it fails before provider access with deterministic guidance
```

### 18. Dependencies and sequencing [reviewed]

Depends on e08s02; precedes final matrix and release evidence.

### 19. Out of scope [reviewed]

Semantic summarization, cloud archival, automatic retention expiry, destructive compaction, or splitting one tool group.

### 20. Definition of done [reviewed]

Long message/event, segmentation, migration, current-instruction, replay, streaming, CLI, and security tests pass.

## Implementation Steps

1. Add message/event segmentation, replay-memory, pair-integrity, current-instruction, and compatibility contracts → verify: `uv run python -m unittest tests.test_sessions tests.test_events tests.test_context_budget -v`
2. Bound segment/file and replay memory without deleting durable groups or orphaning extension fields/results → verify: `uv run python -m unittest tests.test_sessions tests.test_events tests.test_context_budget tests.test_streaming -v`
3. Migrate safe old forms with current instructions or reject unsafe forms before provider access → verify: `uv run python -m unittest tests.test_sessions tests.test_context_budget tests.test_cli_errors -v`

## Verification Script (Step-by-Step)

1. Record the selected segment, event, file-size, and resume-memory limits and their measured baseline.
2. Generate message/event histories immediately below, at, and above each boundary and confirm full durable retention.
3. Resume legacy system-message, malformed, and extension-bearing fixtures and inspect provider calls/current instructions.
