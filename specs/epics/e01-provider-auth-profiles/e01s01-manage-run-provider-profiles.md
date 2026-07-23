STORY KEY: e01s01
TITLE:     Manage and run secure provider profiles
TYPE:      Story
PARENT:    e01
STATUS:    Refined
AUTHOR:    OrbitRelay team           DATE: 2026-07-22
MATURITY:  5
SIZE:      XL

### 1. Business narrative [reviewed]

OrbitRelay currently treats three environment variables as its entire provider
configuration. This is workable for one endpoint but makes switching providers
implicit, makes configuration hard to inspect, and provides no secure path for
persisted credentials.

P1 delivers one complete profile path through configuration, secure credential
storage, CLI management, client construction, and offline verification. The
same boundary also represents future delegated and local auth kinds without
claiming their later runtime integrations.

### 2. Value statement [reviewed]

For OrbitRelay users who work with multiple model endpoints, named profiles
provide explicit, reusable connections and native secret storage while retaining
the current environment workflow as a zero-migration fallback.

### 3. Actors and permissions [reviewed]

- A local user may manage only profiles in that operating-system account.
- OrbitRelay may read and write its own per-user metadata and keyring service.
- A model, workspace, or repository may not select, mutate, or inspect profiles.

### 4. Trigger and preconditions [reviewed]

- The user invokes a `profile` management action or runs OrbitRelay with a
  profile override, a saved selection, or an `OPENAI_*` environment fallback.
- A native keyring backend must be available before a secret-backed profile can
  be created or resolved.
- Profile metadata must validate before any provider client is constructed.

### 5. Main flow and business logic [reviewed]

1. The user creates a named profile and enters a secret through a hidden prompt
   or explicit standard-input mode.
2. OrbitRelay validates the name, endpoint, model, capabilities, and auth kind.
3. OrbitRelay writes the secret to the native keyring and writes only non-secret
   metadata to the per-user profile file.
4. The user lists, inspects, and selects the profile.
5. A run resolves `--profile`, then the saved selection, then the `OPENAI_*`
   compatibility profile.
6. An `api_key` profile constructs the existing OpenAI-compatible client and
   invokes the unchanged agent loop.
7. Deletion removes the keyring value and then metadata, with a retry-safe error
   if either boundary fails.

### 6. Alternative flows and exceptions [reviewed]

- Invalid or corrupt profile metadata fails before keyring or network access.
- Missing or unavailable keyring credentials fail closed with an actionable
  message and no plaintext fallback.
- `external_first_party_cli`, `local_none`, and `local_service_bearer` profiles
  validate and can be inspected, but P1 rejects them at runtime as unsupported.
- `local_none` rejects non-loopback endpoints to prevent unauthenticated LAN
  exposure.
- Creating an existing name requires explicit replacement; accidental overwrite
  is rejected.
- If no override, saved selection, or complete environment profile exists, the
  command reports the missing configuration before constructing a client.
- Deleting the selected profile clears the saved selection.

### 7. Interface elements [reviewed]

- Existing run interface: positional prompt, `--workspace`, and `--verbose`.
- New run option: `--profile NAME`.
- Profile actions: create, list, show, select, and delete.
- Secret input: hidden prompt by default or an explicit stdin mode; never a
  secret-valued command argument.
- Output identifies auth kind, endpoint, model, capabilities, and selection but
  never includes secret values.

### 8. Domain model [reviewed]

- **ProviderProfile:** safe name, endpoint URL, model, auth kind, and explicit
  capability set; it contains no credential value.
- **AuthKind:** `api_key`, `external_first_party_cli`, `local_none`, or
  `local_service_bearer`.
- **ProviderCapability:** a declared feature required by the agent, initially
  tool calling and provider-specific assistant-field replay.
- **ProfileRepository:** per-user metadata plus optional selected profile.
- **CredentialStore:** set/get/delete secret operations addressed by profile
  identity.
- **ResolvedProvider:** validated runtime endpoint, model, and in-memory secret.

Requirement deltas:

#### MODIFIED: Provider configuration source
**Before:** Every run reads only `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and
`OPENAI_MODEL`.
**After:** Every run resolves `--profile`, then the saved profile, then the same
environment variables as a compatibility profile.

#### ADDED: Secret-free profile persistence
Profile metadata is per-user and serializes no credential values; secret-backed
auth kinds use the native credential-store contract.

#### ADDED: Explicit auth and capability contracts
Every named profile declares one roadmap auth kind and the capabilities required
by the agent instead of inheriting behavior from its URL.

### 9. Integrations and boundaries [reviewed]

- Python `keyring` 25.7.x supplies the native credential backend.
- `openai.OpenAI` remains the API-key client boundary.
- The agent loop and workspace-confined local tools remain unchanged.
- JSON metadata is local per-user state and is never read from the workspace.

### 10. Background processes [reviewed]

Not applicable: profile operations are synchronous and start no daemon or
background migration.

### 11. Notifications [reviewed]

Not applicable: the CLI reports completion and errors directly; P1 adds no
external notification channel.

### 12. Audit and logging [reviewed]

- Profile actions may identify profile names and outcomes.
- Recursive redaction removes values under credential-like keys from nested
  diagnostic objects.
- Secrets, secret lengths, and secret fragments are never logged.

### 13. Solution variabilities [reviewed]

- Runtime precedence is fixed: explicit flag, saved selection, environment.
- Secret input is hidden prompt or explicit stdin.
- Metadata location supports an environment override for isolated tests while
  defaulting to an application-owned per-user directory.
- Keyring backend selection belongs to `keyring`; OrbitRelay rejects unavailable
  or insecure fallback backends rather than selecting plaintext storage.

### 14. Quality attributes *NFR* [reviewed]

- Profile validation and repository tests complete without network or native
  keychain access.
- Metadata writes are atomic and deterministic.
- Existing environment-only invocation remains backward compatible.
- The package builds and runs from an isolated wheel.

### 15. Security and compliance *NFR* [reviewed]

- No secret is accepted in command arguments or stored in metadata.
- Profile names are constrained before use as keyring usernames or state keys.
- Keyring failures fail closed and preserve retry-safe cleanup semantics.
- Unauthenticated local profiles are loopback-only.
- The documented macOS keyring caveat is accepted: credentials created by the
  same Python executable may be accessible without another OS prompt unless the
  user tightens Keychain Access controls.

### 16. UX and accessibility *NFR* [reviewed]

- Errors name the failing profile or boundary without including credentials.
- Listing clearly marks the selected profile.
- Machine-readable secret input uses stdin; human input uses a non-echoing
  prompt.
- Profile commands remain usable from a keyboard-only terminal.

### 17. Acceptance criteria [reviewed]

Scenario: Create, select, and run an API-key profile
Given a writable per-user profile location and an available fake credential store
When the user creates and selects a valid API-key profile and runs a prompt
Then only non-secret metadata is persisted and the existing agent receives a
client configured from that profile

Scenario: Preserve the environment compatibility path
Given no explicit or selected profile and complete `OPENAI_*` values
When the user runs the existing positional command
Then OrbitRelay constructs the same endpoint, model, and API-key client as before

Scenario: Honor deterministic precedence
Given an explicit profile, a different saved selection, and complete environment values
When the user runs with `--profile`
Then the explicit profile is used and neither lower-priority source is resolved

Scenario: Reject invalid configuration before network access
Given corrupt, incomplete, or contradictory profile metadata
When the user attempts to run it
Then OrbitRelay reports validation failure before constructing a provider client

Scenario: Validate all roadmap auth kinds
Given representative profiles for each of the four auth kinds
When OrbitRelay validates them
Then valid contracts pass and kind-specific invalid contracts fail without real credentials

Scenario: Reject unsupported runtime auth kinds
Given a valid non-API-key named profile
When the user attempts to run it in P1
Then OrbitRelay reports that the auth runtime is deferred and constructs no client

Scenario: Fail closed when credential storage is unavailable
Given a secret-backed profile and an unavailable native keyring
When the user creates or resolves the profile
Then OrbitRelay reports the credential-store failure and uses no plaintext fallback

Scenario: Delete a selected profile safely
Given a selected secret-backed profile
When the user deletes it
Then its keyring entry and metadata are removed and the selection is cleared

Scenario: Retry deletion after a partial failure
Given secret deletion succeeded but metadata persistence failed
When the user retries deletion
Then the already-missing secret is tolerated and metadata deletion completes

Scenario: Redact nested credentials
Given nested diagnostics containing credential-like keys
When OrbitRelay formats them for output
Then every credential value is replaced and unrelated values remain visible

### 18. Out of scope [reviewed]

- Operational Codex CLI, local provider, or third-party OAuth auth adapters.
- Project-local profiles, automatic capability probing, profile synchronization,
  export/import, and new platform certification.
- Changes to tool approvals, conversations, streaming, or the agent loop.

### 19. Open questions [reviewed]

Not applicable: profile precedence, secret input, metadata scope, runtime auth
breadth, and keyring adoption were explicitly approved before planning.

### 20. References [reviewed]

- `specs/product/SCOPE_LATEST.yaml`
- `specs/IMPACT_LATEST.md`
- `docs/project-roadmap.md`
- `src/orbitrelay/config.py`
- `src/orbitrelay/cli.py`
- https://keyring.readthedocs.io/en/latest/
- https://pypi.org/project/keyring/

## Prior Art

| Candidate | Source | Verdict | Notes |
|---|---|---|---|
| Existing `load_api_config` | `src/orbitrelay/config.py` | extend | Preserve it as the migration-compatible environment resolver. |
| Python `keyring` 25.7.x | official docs and PyPI | adopt `[OK]` | Production/stable, Python >=3.9, native macOS/Secret Service/KWallet/Windows backends; `get_password` returns `None` when absent and `delete_password` raises when absent. |
| Standard-library JSON and atomic replace | Python runtime | compose | Sufficient for small per-user metadata without a database or serialization framework. |
| Provider-specific OAuth | provider roadmap evidence | defer | No approved third-party contract belongs in P1. |

**Reason for Depth — ProfileRepository:** one narrow interface hides validation,
versioned serialization, atomic persistence, selection, and cleanup invariants.

**Reason for Depth — CredentialStore:** a three-operation boundary isolates native
keyring failures and keeps tests independent from real credentials.

## Implementation steps

1. Add public profile contracts and kind-specific validation through behavior tests → verify: `uv run python -m unittest tests.test_profiles -v`
2. Add per-user atomic profile persistence and selected-profile behavior → verify: `uv run python -m unittest tests.test_profiles -v`
3. Add the keyring-backed credential boundary and retry-safe secret lifecycle → verify: `uv run python -m unittest tests.test_credentials -v`
4. Add profile management commands with safe prompt/stdin secret entry → verify: `uv run python -m unittest tests.test_profile_cli -v`
5. Add explicit/saved/environment resolution at the existing client-construction seam → verify: `uv run python -m unittest tests.test_cli -v`
6. Add recursive redaction, documentation, lockfile changes, and regression coverage → verify: `./scripts/check.sh`

## Verification script

1. Run `./scripts/check.sh` and confirm all offline tests, builds, and wheel checks pass.
2. Run CLI help and confirm existing run syntax plus profile management syntax.
3. Use an isolated config directory and fake backend tests to create, inspect,
   select, resolve, and delete a profile.
4. Inspect the generated metadata and captured output for the test secret; it
   must not occur.
