STORY KEY: e03s07
TITLE:     Document and verify hosted-access offline
TYPE:      Story
PARENT:    e03
STATUS:    Done
AUTHOR:    OrbitRelay team           DATE: 2026-07-24
MATURITY:  3
SIZE:      S
type:      docs
context:   domain
risk:      P1

### 1. Business narrative [reviewed]

Hosted access fails in practice when users cannot tell BYOK from SuperGrok, or
Codex install/login from OrbitRelay’s own agent loop. Docs and the mechanical
gate must make the supported matrix explicit.

### 2. Value statement [reviewed]

For operators and future agents, README/roadmap/check.sh prove the three paths
and their security boundaries without live credentials.

### 3. Actors and permissions [reviewed]

- Maintainers update docs/tests.
- CI/local `./scripts/check.sh` is the gate.

### 4. Trigger and preconditions [reviewed]

- e03s01–e03s06 behaviors implemented or stubs landed enough to document.

### 5. Main flow and business logic [reviewed]

1. Document Codex install (document-only), login, exec path.
2. Document xAI BYOK (`XAI_API_KEY`, defaults) vs SuperGrok OAuth billing distinction.
3. Document 403 entitlement + BYOK fallback.
4. Ensure offline unit tests cover all three paths; check.sh remains green.

### 6. Alternative flows and exceptions [reviewed]

- No live network tests required in check.sh.

### 7. Interface elements [reviewed]

README sections + `--help` text consistency.

### 8. Domain model [reviewed]

Docs only; no domain change.

### 9. Integrations and boundaries [reviewed]

Links to official Codex and xAI docs.

### 10. Background processes [reviewed]

Not applicable.

### 11. Notifications [reviewed]

Not applicable.

### 12. Audit and logging [reviewed]

Docs restate secret-free logging rules.

### 13. Solution variabilities [reviewed]

None.

### 14. Architecture decisions [reviewed]

Verification culture unchanged: offline fakes only.

### 15. Test strategy [reviewed]

Full `./scripts/check.sh`.

### 16. Observability [reviewed]

Not applicable.

### 17. Acceptance criteria [reviewed]

```gherkin
Feature: Hosted access docs and gate
  Scenario: README explains three paths
    When a user reads README hosted-access sections
    Then Codex process-boundary, xAI BYOK, and SuperGrok OAuth are distinct
    And foreign auth.json reading is explicitly disallowed

  Scenario: Mechanical gate stays green offline
    When ./scripts/check.sh runs
    Then project tests, example tests, and package smoke pass without network credentials
```

### 18. Dependencies and sequencing [reviewed]

Last story in epic; can track docs continuously.

### 19. Out of scope [reviewed]

CI introduction, Windows docs certification.

### 20. Definition of done [reviewed]

`./scripts/check.sh` green; README updated; release notes draftable.
