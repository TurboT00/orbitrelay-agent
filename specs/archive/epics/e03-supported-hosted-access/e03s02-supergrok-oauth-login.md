STORY KEY: e03s02
TITLE:     Sign in and out of SuperGrok subscription OAuth
TYPE:      Story
PARENT:    e03
STATUS:    Done
AUTHOR:    OrbitRelay team           DATE: 2026-07-24
MATURITY:  3
SIZE:      L
type:      feat
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

SuperGrok / X Premium usage is billed on a subscription track distinct from
`XAI_API_KEY`. Users need a first-class OrbitRelay login that uses xAI account
OAuth without reading `~/.grok/auth.json` or storing plaintext tokens.

### 2. Value statement [reviewed]

For a SuperGrok subscriber, OrbitRelay can complete OAuth login, refresh,
status, and logout using only the OS keyring for secrets.

### 3. Actors and permissions [reviewed]

- Local user approves login in a browser/device flow.
- OrbitRelay performs device-code and/or browser+PKCE against pinned auth.x.ai endpoints.
- No foreign CLI may be required for OrbitRelay-managed SuperGrok auth.

### 4. Trigger and preconditions [reviewed]

- Interactive terminal (or headless device-code with user browser elsewhere).
- Pinned OAuth endpoints from research (auth.x.ai).

### 5. Main flow and business logic [reviewed]

1. User starts SuperGrok login.
2. OrbitRelay obtains device code or starts PKCE authorize URL.
3. User approves; OrbitRelay exchanges for access+refresh tokens.
4. Tokens stored only via CredentialStore / secret contract; profile metadata is secret-free.
5. Status reports logged-in vs logged-out without printing tokens.
6. Logout deletes OrbitRelay-managed tokens.

### 6. Alternative flows and exceptions [reviewed]

- Timeout / denial / invalid_grant → clear re-auth guidance.
- Never read `~/.grok/auth.json` or Hermes auth files.
- Refresh skew before expiry; quarantine dead refresh tokens.

### 7. Interface elements [reviewed]

- CLI commands for login/status/logout (exact names in plan-work).
- Prints verification URL + user code for device flow; never prints tokens.

### 8. Domain model [reviewed]

#### ADDED: SuperGrok OAuth session credential
Access/refresh token bundle managed by OrbitRelay credential contract.

#### ADDED or MODIFIED: Auth kind / profile metadata
Express subscription OAuth without weakening existing AuthKind validation.

### 9. Integrations and boundaries [reviewed]

- HTTPS to auth.x.ai only for this story (no inference yet).
- Client ID/scope pins are candidates pending final plan-work acceptance of
  shared Grok CLI client compatibility.

### 10. Background processes [reviewed]

Optional proactive refresh may run at session start; no always-on daemon required.

### 11. Notifications [reviewed]

Terminal instructions for browser/device approval only.

### 12. Audit and logging [reviewed]

Log outcome (success/failure reason codes) without tokens, codes, or raw bodies.

### 13. Solution variabilities [reviewed]

Device-code-first recommended (headless-friendly); browser+PKCE optional.

### 14. Architecture decisions [reviewed]

Build OrbitRelay-owned OAuth client; compose protocol pins from Hermes/Pi; do
not vendor those packages.

### 15. Test strategy [reviewed]

Fake OAuth HTTP server covering device poll, token refresh, logout, timeout.

### 16. Observability [reviewed]

Status command only.

### 17. Acceptance criteria [reviewed]

```gherkin
Feature: SuperGrok OAuth login lifecycle
  Scenario: Device-code login stores tokens only in credential store
    Given a fake auth.x.ai device/token server and temp profile home
    When the user completes SuperGrok login
    Then access and refresh material are available via CredentialStore
    And no auth.json plaintext token file is written under the profile home
    And stdout/stderr contain no access or refresh token

  Scenario: Status and logout
    Given a stored SuperGrok OAuth session
    When the user checks status
    Then OrbitRelay reports authenticated without secrets
    When the user logs out
    Then subsequent status reports logged out and get_secret fails closed

  Scenario: Refresh failure requires re-auth
    Given a refresh token rejected with invalid_grant
    When OrbitRelay attempts refresh
    Then it fails closed with a re-authentication message and does not loop
```

### 18. Dependencies and sequencing [reviewed]

Independent of Codex stories. Blocks e03s03.

### 19. Out of scope [reviewed]

Inference calls, media APIs, reading Grok CLI auth files.

### 20. Definition of done [reviewed]

Offline OAuth tests green; threat model T1–T3 addressed for login path.
