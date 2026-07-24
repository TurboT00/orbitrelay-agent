STORY KEY: e03s03
TITLE:     Run the agent loop on a SuperGrok OAuth session
TYPE:      Story
PARENT:    e03
STATUS:    Todo
AUTHOR:    OrbitRelay team           DATE: 2026-07-24
MATURITY:  3
SIZE:      L
type:      feat
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Login alone is insufficient: SuperGrok users need OrbitRelay’s local tools and
approval policies while the model is backed by their subscription session.

### 2. Value statement [reviewed]

For a logged-in SuperGrok user, a normal OrbitRelay run uses subscription auth,
keeps P2 approvals, and fails closed on 401/403/missing login.

### 3. Actors and permissions [reviewed]

- User selects SuperGrok profile/session and approval policy.
- Model requests tools; approval session authorizes local side effects.
- xAI authorizes inference via OAuth bearer (and optional proxy).

### 4. Trigger and preconditions [reviewed]

- e03s02 login completed (or test double session).
- Workspace valid; approval policy selected.

### 5. Main flow and business logic [reviewed]

1. Resolve SuperGrok credentials (refresh if needed).
2. Construct model client for chosen transport (Completions-on-api.x.ai first;
   Responses/proxy if required by evidence during implementation).
3. Run existing agent loop with OrbitRelay tools + approvals.
4. Map provider 401/403 to actionable errors without side effects before approval.

### 6. Alternative flows and exceptions [reviewed]

- Missing login → refuse run.
- 403 entitlement → message distinguishing tier gating from bad tokens; suggest BYOK.
- Token refresh mid-run once; then fail closed.

### 7. Interface elements [reviewed]

- Profile/auth-kind selection for SuperGrok runs.
- Error text must not include tokens.

### 8. Domain model [reviewed]

#### MODIFIED: Executable auth kinds
Allow SuperGrok OAuth sessions to execute (not only api_key).

#### ADDED: Provider error classification
Stable reasons for missing_auth, reauth_required, entitlement_denied.

### 9. Integrations and boundaries [reviewed]

- Local tools/approvals unchanged in authority.
- No Codex path in this story.

### 10. Background processes [reviewed]

Not applicable beyond token refresh helper.

### 11. Notifications [reviewed]

CLI/runtime errors only.

### 12. Audit and logging [reviewed]

Approval audit remains secret-free; provider errors redacted.

### 13. Solution variabilities [reviewed]

Transport choice is the main variability; keep tool loop identical.

### 14. Architecture decisions [reviewed]

Prefer minimal change to agent.py tool correlation; isolate transport adapter.

### 15. Test strategy [reviewed]

Fake model HTTP + fake OAuth creds; approval path regressions.

### 16. Observability [reviewed]

Existing verbose approval events only.

### 17. Acceptance criteria [reviewed]

```gherkin
Feature: SuperGrok-backed agent loop
  Scenario: OAuth session runs tools under confirm policy
    Given a SuperGrok OAuth test double and fake model returning write_file
    When the user runs with confirm policy and approves
    Then the write executes once and tokens never appear in output

  Scenario: Missing SuperGrok login fails before tools
    Given no SuperGrok credential
    When the user selects the SuperGrok path
    Then OrbitRelay fails closed before any tool side effect

  Scenario: Entitlement 403 is actionable
    Given OAuth tokens that yield HTTP 403 on inference
    When the user runs
    Then the error identifies entitlement/permission failure and suggests BYOK fallback
```

### 18. Dependencies and sequencing [reviewed]

Depends on e03s02. Benefits from e03s01 BYOK docs for fallback.

### 19. Out of scope [reviewed]

Streaming UX, conversation persistence, media tools.

### 20. Definition of done [reviewed]

Offline SuperGrok loop tests + existing approval tests remain green.
