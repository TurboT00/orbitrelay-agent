STORY KEY: e03s05
TITLE:     Delegate Codex login and logout to the official CLI
TYPE:      Story
PARENT:    e03
STATUS:    Done
AUTHOR:    OrbitRelay team           DATE: 2026-07-24
MATURITY:  3
SIZE:      M
type:      feat
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Codex owns ChatGPT sign-in. OrbitRelay must never reproduce that OAuth flow or
touch auth.json; it should launch documented Codex login/logout/status commands.

### 2. Value statement [reviewed]

For a user with Codex installed, OrbitRelay can start login, check status, and
logout through the official CLI only.

### 3. Actors and permissions [reviewed]

- User completes Codex browser/device login UX owned by Codex.
- OrbitRelay spawns fixed argv commands and relays exit codes.

### 4. Trigger and preconditions [reviewed]

- e03s04 detection available=true (or clear missing error).

### 5. Main flow and business logic [reviewed]

1. `codex login` (default browser) or `codex login --device-auth`.
2. `codex login status` for automation-friendly check (exit 0 ⇒ credentials present).
3. `codex logout` to clear Codex-managed credentials.

### 6. Alternative flows and exceptions [reviewed]

- Missing codex → install guidance.
- Non-zero login/status → propagate failure without reading auth files.
- Do not implement `--with-api-key` piping of OrbitRelay secrets unless explicitly added later.

### 7. Interface elements [reviewed]

- OrbitRelay subcommands that delegate to Codex.

### 8. Domain model [reviewed]

#### ADDED: CodexAuthBridge
login/logout/status operations over subprocess.

### 9. Integrations and boundaries [reviewed]

Official Codex CLI only; documented flags from developers.openai.com.

### 10. Background processes [reviewed]

Not applicable.

### 11. Notifications [reviewed]

Codex owns browser prompts; OrbitRelay prints that delegation occurred.

### 12. Audit and logging [reviewed]

Log command name + exit code; never capture tokens from Codex output beyond status text already public.

### 13. Solution variabilities [reviewed]

Whether to stream Codex TTY fully or just spawn and wait — prefer full inheritance of stdio for interactive login.

### 14. Architecture decisions [reviewed]

Process boundary; EXTERNAL_FIRST_PARTY_CLI alignment.

### 15. Test strategy [reviewed]

Fake codex script recording argv and exit codes.

### 16. Observability [reviewed]

Status command.

### 17. Acceptance criteria [reviewed]

```gherkin
Feature: Codex login delegation
  Scenario: Login delegates to codex login
    Given a fake codex that records argv
    When the user runs OrbitRelay Codex login
    Then argv begins with login and OrbitRelay does not read auth.json

  Scenario: Device login flag
    When the user requests device auth login
    Then argv includes --device-auth

  Scenario: Status and logout
    When the user runs status and logout
    Then OrbitRelay invokes `login status` and `logout` respectively
```

### 18. Dependencies and sequencing [reviewed]

Depends on e03s04.

### 19. Out of scope [reviewed]

codex exec runtime, reading credentials, API-key stdin login automation.

### 20. Definition of done [reviewed]

Fake-subprocess tests prove argv contracts.
