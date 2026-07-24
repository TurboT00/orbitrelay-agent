STORY KEY: e03s04
TITLE:     Detect Codex CLI availability and version
TYPE:      Story
PARENT:    e03
STATUS:    Todo
AUTHOR:    OrbitRelay team           DATE: 2026-07-24
MATURITY:  3
SIZE:      S
type:      feat
context:   domain
risk:      P1

### 1. Business narrative [reviewed]

Users cannot use the Codex bridge if OrbitRelay cannot tell whether the official
CLI is installed. Detection must be separate from model API profiles.

### 2. Value statement [reviewed]

For any user, OrbitRelay reports whether `codex` is available and which version
string it reports, with install guidance when missing.

### 3. Actors and permissions [reviewed]

- Local user invokes status/detect.
- OrbitRelay only executes a fixed version/path probe argv.

### 4. Trigger and preconditions [reviewed]

- Optional `codex` on PATH (or injectable resolver for tests).

### 5. Main flow and business logic [reviewed]

1. Resolve `codex` executable path without shell interpolation.
2. Run version probe (`codex --version` or documented equivalent).
3. Report available/missing + version text.
4. Warn-only if below a future documented floor; never hard-block unknowns.

### 6. Alternative flows and exceptions [reviewed]

- Missing binary → install guidance (document-only; no auto-install).
- Non-zero version probe → unavailable with stderr sanitized.

### 7. Interface elements [reviewed]

- Status command or `orbitrelay codex status` style surface (final name in plan-work).

### 8. Domain model [reviewed]

#### ADDED: CodexInstallation
path, version, available bool, warning optional.

### 9. Integrations and boundaries [reviewed]

Subprocess only; never reads CODEX_HOME/auth.json.

### 10. Background processes [reviewed]

Not applicable.

### 11. Notifications [reviewed]

Terminal status lines only.

### 12. Audit and logging [reviewed]

No secrets expected; still sanitize.

### 13. Solution variabilities [reviewed]

PATH lookup vs explicit binary override flag.

### 14. Architecture decisions [reviewed]

Connect toward AuthKind.EXTERNAL_FIRST_PARTY_CLI metadata without executing OAuth.

### 15. Test strategy [reviewed]

Fake executable scripts in temp PATH.

### 16. Observability [reviewed]

Status output only.

### 17. Acceptance criteria [reviewed]

```gherkin
Feature: Codex detection
  Scenario: Detect installed codex
    Given a fake codex executable on PATH printing a version
    When the user requests Codex status
    Then OrbitRelay reports available=true and the version string

  Scenario: Missing codex
    Given no codex on PATH
    When the user requests Codex status
    Then OrbitRelay reports available=false and install guidance
    And it does not read any auth.json path
```

### 18. Dependencies and sequencing [reviewed]

Foundation for e03s05/e03s06.

### 19. Out of scope [reviewed]

Login, exec, bundling codex.

### 20. Definition of done [reviewed]

Offline detect tests green.
