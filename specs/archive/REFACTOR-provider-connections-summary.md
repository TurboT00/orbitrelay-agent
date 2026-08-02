## Provider Connection Refactor

**Status:** complete.

OrbitRelay now has one stored provider-connection workflow:

```text
provider list
provider connect <provider> --method <method>
provider import-env --provider <provider>
provider status [provider]
provider disconnect <provider>
```

### Delivered

- One provider catalog owns endpoint defaults, models, execution routes, and
  available authentication methods.
- Agent runs resolve the selected stored connection, or a one-run `--provider`
  override. They do not read provider environment variables or `.env` files.
- API-key connections support OpenAI, Gemini, Grok, and DeepSeek.
- Codex uses a credential-free connection that delegates sign-in and execution
  to the official installed Codex CLI.
- Legacy environment values can be imported explicitly for one provider.
- Version-1 metadata migrates atomically while retaining its credential-key
  namespace. Legacy subscription tokens are never used as API keys.
- Secrets remain in the native credential store; connection metadata is
  secret-free.

### Deferred

- Gemini OAuth requires its documented integration probe before implementation.
- Grok and DeepSeek remain API-key-only until a supported third-party
  subscription contract exists.

### Verification

`./scripts/check.sh` passes, including project tests, calculator tests,
distribution builds, and isolated wheel CLI verification.

The original problem analysis and implementation plan are preserved at
`specs/archive/REFACTOR-2026-07-provider-connections.md`.
