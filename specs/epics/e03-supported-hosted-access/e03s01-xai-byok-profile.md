STORY KEY: e03s01
TITLE:     Run OrbitRelay with an xAI BYOK profile
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

Users who already hold an xAI API key cannot express a first-class xAI profile
today without manually inventing OpenAI-compatible env vars. P3 must make BYOK
xAI as easy and safe as other API-key profiles while keeping secrets in the OS
keyring.

### 2. Value statement [reviewed]

For a developer with an `XAI_API_KEY`, OrbitRelay can select an xAI profile and
run the existing tool loop against Grok without secret leakage.

### 3. Actors and permissions [reviewed]

- Local user creates/selects profiles and supplies the API key.
- OrbitRelay stores the key only via CredentialStore.
- Model never sees or sets credentials.

### 4. Trigger and preconditions [reviewed]

- User creates an xAI `api_key` profile or exports `XAI_API_KEY`.
- Defaults: base URL `https://api.x.ai/v1`, model `grok-4.5`.

### 5. Main flow and business logic [reviewed]

1. User creates profile with xAI defaults (or env migration resolves config).
2. Secret is stored in keyring; metadata remains secret-free.
3. Run resolves profile → OpenAI client with xAI base URL and bearer key.
4. Existing Chat Completions agent loop and approvals execute unchanged.

### 6. Alternative flows and exceptions [reviewed]

- Missing key fails before client creation.
- Invalid base URL rejected by existing profile validation.
- Generic OpenAI-compatible profiles remain available.

### 7. Interface elements [reviewed]

- Profile create flags/docs for xAI preset.
- Optional `XAI_API_KEY` env path documented beside `OPENAI_*`.

### 8. Domain model [reviewed]

#### ADDED: xAI BYOK preset defaults
Default endpoint/model constants for xAI API-key profiles.

#### MODIFIED: Env config resolution
May accept `XAI_API_KEY` (and documented companions) without mixing partial
dotenv/process sources.

### 9. Integrations and boundaries [reviewed]

- Reuses OpenAI Python SDK Chat Completions.
- No SuperGrok OAuth in this story.

### 10. Background processes [reviewed]

Not applicable.

### 11. Notifications [reviewed]

CLI errors for missing/invalid credentials only.

### 12. Audit and logging [reviewed]

Never print API keys; redaction unchanged.

### 13. Solution variabilities [reviewed]

Prefer constants + profile docs over a new dependency.

### 14. Architecture decisions [reviewed]

Extend `api_key` path; do not invent a separate BYOK runtime.

### 15. Test strategy [reviewed]

Offline fakes for config/profile/CLI; no live xAI calls.

### 16. Observability [reviewed]

Existing verbose mode only; no new telemetry.

### 17. Acceptance criteria [reviewed]

```gherkin
Feature: xAI BYOK profile
  Scenario: Create and run with keyring-backed xAI profile
    Given a temp profile home and fake credential store
    When the user creates an xAI api_key profile with a secret
    Then metadata contains base_url https://api.x.ai/v1 and model grok-4.5
    And the secret is absent from metadata and stdout
    And a run resolves an OpenAI client config from that profile

  Scenario: XAI_API_KEY env migration
    Given process env has XAI_API_KEY and no conflicting partial OpenAI mix
    When config is resolved without an explicit profile
    Then the API config uses the xAI key and documented defaults

  Scenario: Missing credential fails closed
    Given an xAI profile without a stored secret
    When the user starts a run with that profile
    Then OrbitRelay exits before creating a network client
```

### 18. Dependencies and sequencing [reviewed]

No story dependency. Foundation for e03s03 BYOK fallback messaging.

### 19. Out of scope [reviewed]

OAuth, Codex, streaming, local models.

### 20. Definition of done [reviewed]

Tasks green; docs mention xAI BYOK; `./scripts/check.sh` still passes after
implementation of later stories keeps this green.
