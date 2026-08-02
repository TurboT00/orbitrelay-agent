## Implementation Status

**Status:** implemented, with Gemini OAuth intentionally deferred.

The provider catalog, stored connection service, `provider` CLI, import-only
environment migration, v1 metadata migration, Codex external-CLI boundary, and
documentation/test migration are complete. Gemini OAuth requires the documented
integration probe; Grok and DeepSeek remain API-key-only.

The problem statement and implementation plan below are retained as the
decision record for this completed refactor.

## Problem Statement

OrbitRelay currently has three competing ways to establish a model connection:

1. `config.py` discovers provider-specific API keys from the process or `.env` and
   chooses the first matching provider in a hard-coded precedence order.
2. `profile` commands persist endpoint/model/auth metadata and store a secret in
   the native credential store.
3. `auth supergrok` has a separate xAI-specific device OAuth client which creates
   and refreshes a special `supergrok` profile.

These paths leak provider knowledge into multiple modules and make the effective
configuration difficult to predict. The current working change adds OpenAI to
the environment precedence list, increasing that duplication rather than
solving it. There are also concrete inconsistencies: the runtime accepts
`OPENAI_URL` while documentation describes `OPENAI_BASE_URL`; the URL variables
are collected in `cli.py` but ignored by `load_api_config`; and the README still
documents an OpenAI key pointed at DeepSeek.

The desired product is one consistent provider sign-in flow. It must offer the
supported providers—OpenAI/Codex, Grok (xAI), Gemini, and DeepSeek—then offer
only the authentication methods officially usable by OrbitRelay for that
provider. A normal run must resolve one selected connection, rather than
merging profile, environment, and hard-coded configuration sources.

### Current behavior to preserve

* Secrets remain outside JSON configuration and command-line arguments, in the
  approved native keyring or an external provider-owned credential store.
* Existing selected API-key profiles continue to work after migration without
  exposing, deleting, or sending their credential to a different endpoint.
* A one-off selection overrides the saved default.
* Codex remains an external official-CLI boundary: OrbitRelay must never read,
  copy, or mint `CODEX_HOME` credentials.
* Profile-store permission and validation safeguards, capabilities, agent
  execution, approvals, sessions, and streaming behavior remain intact.

## Decisions Made

* Use an **official-only** subscription policy. OpenAI/Codex and Gemini may
  offer subscription/OAuth only through their documented interfaces. Grok and
  DeepSeek are API-key-only until an official third-party authorization contract
  exists.
* Make environment variables **import-only**. They are a migration/automation
  input to `provider connect --from-env`, never a second runtime credential
  resolver.
* Use a **provider default** UX: `provider connect <provider>` creates or
  updates that provider's default connection and selects it. `--provider` is a
  one-run override. Multiple named connections are explicitly out of scope for
  this cleanup.
* Do not preserve the undocumented SuperGrok OAuth implementation merely behind
  a generic command. Retire it after an explicit migration/reauthentication
  notice.

## Solution

Create a provider catalog and a single connection service. The catalog is the
only place that owns provider identifier, display name, OpenAI-compatible
endpoint, default model, required capabilities, supported auth methods, legacy
environment variable mapping, and execution route. The connection service is
the only place that creates, selects, resolves, imports, validates, disconnects,
and reports a connection.

### Target command surface

```text
orbitrelay provider list
orbitrelay provider connect openai --method api-key
orbitrelay provider connect codex --method subscription
orbitrelay provider connect gemini --method api-key|subscription
orbitrelay provider connect grok --method api-key
orbitrelay provider connect deepseek --method api-key
orbitrelay provider import-env [--provider PROVIDER]
orbitrelay provider status [PROVIDER]
orbitrelay provider disconnect PROVIDER
orbitrelay "task" [--provider PROVIDER]
```

`provider list` must show the available methods and whether a connection is
selected; it must never show secrets. `connect` prompts for an API key without
echoing it, or delegates to the adapter's documented subscription flow. A
successful connection atomically replaces that provider's configuration and
selects it. `--provider` resolves that provider's one stored connection; without
it, the selected connection resolves. There is no fallback to `.env` or process
variables at run time.

### Provider and method matrix

| Provider ID | API-key route | Subscription route | Execution route |
| --- | --- | --- | --- |
| `openai` | OpenAI API key | none in OrbitRelay's chat transport | OpenAI-compatible client |
| `codex` | not offered as a duplicate OpenAI connection | official installed Codex CLI login/logout/exec only | existing Codex bridge |
| `gemini` | Gemini API key via documented compatibility endpoint | official Google/Gemini OAuth only after an integration probe verifies supported scopes, token audience, refresh/storage, and tool-call compatibility | OpenAI-compatible client |
| `grok` | xAI API key | unavailable; show reason and documentation URL | OpenAI-compatible client |
| `deepseek` | DeepSeek API key | unavailable; show reason and documentation URL | OpenAI-compatible client |

The catalog must be able to say `unavailable` without a special-case command.
It must never represent an undocumented xAI browser/device flow as a supported
subscription option. Gemini subscription support is gated by the documented
integration probe; if the probe fails, the released catalog reports it as
unavailable rather than shipping a speculative OAuth client.

### Data and module design

* Add `providers.py` containing `ProviderId`, `AuthMethod`, immutable
  `ProviderDefinition`, the four provider definitions, lookup/validation, and
  endpoint/model defaults. Move the current OpenAI, DeepSeek, Gemini, and xAI
  constants out of `config.py`; eliminate provider lists from `cli.py`.
* Replace the provider-neutral `ProviderProfile` runtime concept with a
  versioned `ProviderConnection`: `provider_id`, `auth_method`, route,
  endpoint/model snapshot where applicable, capabilities, and non-secret
  metadata. Preserve repository locking, secure-path checks, and keyring keys.
* Add `connection_service.py` to own all resolving and credential access. It
  returns either an OpenAI-client `ApiConfig` or a Codex execution descriptor;
  the main CLI should not import keyring, OAuth, or provider-specific modules.
* Add small adapter interfaces (`ApiKeyAdapter`, `ExternalCliSubscriptionAdapter`,
  and a future documented OAuth adapter). The adapters own method-specific
  validation and refresh—not the CLI. Codex delegates to documented Codex
  commands and owns its own credentials. A documented Gemini OAuth adapter may
  be added only after the gate above passes; tokens belong in the existing
  native credential store under the connection key.
* Keep `config.py` only for transport-neutral structures and remove
  `load_api_config`. Remove `auth_cli.py` and `supergrok_oauth.py` once the
  migration has retired SuperGrok. Rename/replace `profile_cli.py` with
  `provider_cli.py`; do not leave two public command families.

## Implementation Plan

Each commit is intentionally buildable and testable on its own.

1. **Document the behavioral contract and freeze regressions.**
   * Add focused characterization tests for current selected-profile precedence,
     keyring secret isolation, `--profile` override, and Codex bridge credential
     ownership.
   * Record the migration invariant above in a code-level migration test
     fixture: API-key profiles for each known endpoint and a custom endpoint
     retain their own secret and endpoint.
   * Do not change runtime behavior in this commit.

2. **Introduce the provider catalog with no CLI behavior change.**
   * Implement `src/orbitrelay/providers.py` with the four required provider
     definitions, capability defaults, method availability/reasons,
     documentation links, legacy environment names, and explicit execution
     routes.
   * Move all endpoint/model defaults from `config.py` and SuperGrok into this
     catalog. Make existing config/profile preset code consume the catalog.
   * Add table-driven catalog tests: unique IDs, valid HTTPS endpoints, model
     defaults, advertised method matrix, and no Grok/DeepSeek subscription
     method.

3. **Add the connection schema and a non-destructive repository migration.**
   * Version the profile-store JSON schema and migrate legacy profiles under the
     existing lock. Map known endpoint/auth pairs to `openai`, `gemini`, `grok`,
     or `deepseek`; preserve unknown API-key profiles as an explicit legacy
     custom OpenAI-compatible connection so no working setup is discarded.
   * Map legacy `supergrok`/`subscription_oauth` records to a disconnected Grok
     migration record with a clear reauthentication notice; never reinterpret
     its refresh token as an API key.
   * Retain native-keyring identifiers for migrated API-key secrets; remove a
     credential only after a successful, verified replacement.
   * Test idempotent migration, rollback on malformed input, selected-default
     migration, custom endpoint preservation, profile-store permissions, and
     the SuperGrok no-token-reuse case.

4. **Implement one connection service and execution resolver.**
   * Add `connection_service.py` and adapters. Centralize connect, select,
     resolve, status, and disconnect behavior; make it return a typed execution
     target instead of assuming every provider returns `ApiConfig`.
   * Route API-key connections through the native credential store and the
     catalog endpoint/model. Route Codex through the existing Codex bridge,
     checking the official executable and never accessing its auth files.
   * Move subscription token refresh behind a documented adapter interface and
     add a fake adapter for offline tests. Do not add a Gemini live OAuth client
     until the integration probe's acceptance criteria pass.
   * Test every provider/method resolution branch, missing secrets, stale or
     disconnected status, reauth-required behavior, and the guarantee that a
     key is never supplied to an adapter for another provider.

5. **Replace the public CLI with `provider`.**
   * Implement `provider list/connect/import-env/status/disconnect` using the
     connection service. `connect` must reject unsupported method/provider
     pairs before prompting or opening a browser.
   * Add `--provider` to agent execution; select one connection only. Remove
     `_resolved_config`, `_repository_for_run`, direct `ProfileService` calls,
     and provider-specific HTTP-error guidance from `cli.py`.
   * Keep temporary, deprecation-only aliases for `profile` and `auth` that
     print an exact replacement command and perform no separate resolution.
     Remove them in the next declared breaking release.
   * Test help text, prompts, noninteractive failures, one-run override,
     selection, unsupported subscription errors, and no secret leakage to
     stdout/stderr.

6. **Make `.env` an explicit importer, then remove it from runtime.**
   * Implement `provider import-env` against the catalog's legacy variable
     mapping. Reject ambiguous inputs (more than one complete provider set),
     partial credentials, unsupported URL overrides, and interpolation.
   * Permit an API-key import only after the user selects a provider or supplies
     `--provider`; report the detected model/default and ask before overwriting
     an existing connection.
   * Delete `TRANSPORT_ENV_KEYS`, `_environment_source`, `_dotenv_environment`,
     and `load_api_config`; an ordinary agent invocation must be independent of
     the process environment and `.env`.
   * Test environment import for all four providers, process-vs-dotenv
     ambiguity, overwrite confirmation, and that subsequent agent resolution
     ignores changed environment variables.

7. **Retire the SuperGrok special path and complete the Gemini gate.**
   * Remove `supergrok_oauth.py`, `auth_cli.py`, their imports, and their
     provider-specific tests after the migration behavior is covered by the new
     service tests.
   * Run the documented Gemini OAuth integration probe with a dedicated test
     account and no production secrets in fixtures. It must prove consent,
     least scopes, refresh/revocation, token audience, model access, and
     tool-call round-trip. If all pass, implement the adapter and its offline
     contract tests; otherwise leave the catalog method unavailable with a
     concise explanation and tracked follow-up.

8. **Replace stale documentation and validate the clean state.**
   * Rewrite README setup/configuration around `provider connect`; include one
     short API-key example per required provider, the Codex external-login
     boundary, availability matrix, migration/import instructions, and no
     secret-bearing shell arguments.
   * Replace `.env.example` with a clearly labelled import-only migration
     sample, or remove it if import from an existing environment is documented
     sufficiently. Remove `OPENAI_BASE_URL` claims and the misleading
     OpenAI-key-to-DeepSeek default.
   * Update roadmap/state/release artifacts only after implementation is
     approved; this plan itself does not claim the feature is shipped.
   * Run `./scripts/check.sh`, the full `uv run pytest`, and targeted CLI,
     migration, credentials, provider-catalog, Codex, and Gemini-adapter tests.

## Out of Scope

* Supporting undocumented provider OAuth, browser-cookie reuse, or copied CLI
  credentials.
* Multiple named work/personal connections per provider.
* Local Ollama/vLLM onboarding, arbitrary hosted-provider onboarding, or a
  transport/API redesign beyond the typed Codex versus OpenAI-compatible route.
* Adding a live Gemini subscription adapter without passing the documented
  integration gate.
* Removing legacy aliases in the same release as the migration.

## Acceptance Criteria

* A new user can discover and connect each required provider through one
  `provider` command family, with only valid methods shown.
* Normal agent execution resolves exactly one stored connection; it never
  silently reads `.env` or provider environment variables.
* API keys and OAuth bundles never enter profile JSON, command arguments, logs,
  error messages, or tests; Codex credentials remain provider-owned.
* Existing API-key profile users migrate without credential loss or endpoint
  changes; former SuperGrok OAuth users receive an actionable, non-destructive
  reauthentication notice.
* Documentation, examples, CLI help, catalog defaults, and tests describe the
  same provider matrix and configuration vocabulary.
