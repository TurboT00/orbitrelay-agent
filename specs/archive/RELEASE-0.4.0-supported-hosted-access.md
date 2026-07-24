# OrbitRelay 0.4.0 — Supported Hosted Access

- Branch: `feat/e03-supported-hosted-access`
- Base: `8415e082e6aa12d45a1e66f2aa8ca33b626053ca` (`main` after P3 planning commit)
- Package version: `0.4.0`
- Push: not requested (local release handoff only)

## Summary

0.4.0 adds supported hosted-provider access without inventing password collection
or reading foreign auth files. Users can run xAI via API key (BYOK), SuperGrok /
X Premium via device-code OAuth stored in the OS keyring, and Codex via the
official CLI process boundary (`login` / `logout` / `exec`).

## Highlights

- **xAI BYOK:** `XAI_API_KEY` with defaults `https://api.x.ai/v1` + `grok-4.5`,
  plus `orbitrelay profile create … --preset xai`.
- **SuperGrok OAuth:** `orbitrelay auth supergrok login|status|logout` using
  device-code flow against `auth.x.ai`; tokens only in the native keyring;
  refresh quarantine on `invalid_grant`; HTTP 401/403 guidance including BYOK
  fallback for entitlement gating.
- **Codex CLI bridge:** `orbitrelay codex status|login|logout|exec` delegates to
  documented commands only; never reads `CODEX_HOME/auth.json`; `exec` uses
  `--json` + `--cd` and never defaults to sandbox/approval bypass flags.
- **Approvals preserved:** OrbitRelay local tool approvals still gate the Chat
  Completions agent loop under `api_key` and SuperGrok profiles. Codex exec is
  an alternate runtime that owns its own sandbox.
- **Auth kinds:** `subscription_oauth` added; executable kinds are `api_key` and
  `subscription_oauth` (plus Codex process path outside profiles).

## Stories

| Story | Title | Status |
|---|---|---|
| e03s01 | Run OrbitRelay with an xAI BYOK profile | done |
| e03s02 | Sign in and out of SuperGrok subscription OAuth | done |
| e03s03 | Run the agent loop on a SuperGrok OAuth session | done |
| e03s04 | Detect Codex CLI availability and version | done |
| e03s05 | Delegate Codex login and logout to the official CLI | done |
| e03s06 | Run a Codex exec alternate runtime path | done |
| e03s07 | Document and verify hosted-access offline | done |

## Verification

- `./scripts/check.sh` green on the release branch.
- Offline unit/integration coverage for BYOK, SuperGrok OAuth (fake HTTP), and
  Codex bridge (fake PATH/subprocess).
- Calculator example tests still pass.
- Package artifacts: `orbitrelay_agent-0.4.0` sdist + wheel + isolated CLI smoke
  after version bump.
- Scope/threat model: `specs/product/SCOPE_LATEST.yaml`,
  `specs/security/epics/e03/THREAT_MODEL.md`.

## CLI additions

```text
# xAI BYOK
XAI_API_KEY / XAI_BASE_URL / XAI_MODEL
orbitrelay profile create NAME --preset xai ...

# SuperGrok OAuth
orbitrelay auth supergrok login
orbitrelay auth supergrok status
orbitrelay auth supergrok logout
orbitrelay --profile supergrok "..."

# Codex process bridge
orbitrelay codex status
orbitrelay codex login [--device-auth]
orbitrelay codex logout
orbitrelay codex exec "prompt" [--workspace PATH]
```

## Out of scope (intentionally deferred)

- Reading `~/.grok/auth.json`, Hermes auth files, or Codex `auth.json`
- Browser+PKCE SuperGrok path (device-code first shipped; PKCE optional later)
- Responses/cli-chat-proxy SuperGrok transport (Chat Completions bearer first)
- Conversation persistence / streaming (P4)
- Local models (P5), plugins (P6), Windows certification (P7)
- Bundling or auto-installing the Codex binary

## Release decision

Prepare a PR from `feat/e03-supported-hosted-access` into `main` when push is
explicitly requested. Do not force-push. Semantic version bump is **minor**
(`0.3.0` → `0.4.0`). Package metadata on this branch is set to `0.4.0`.
