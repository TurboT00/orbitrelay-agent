# OrbitRelay 0.5.0 — Conversations and Streaming

- Branch: `feat/e04-conversations-and-streaming`
- Package version: `0.5.0` (bump on release prep commit)
- Push: not requested until explicitly approved

## Summary

0.5.0 adds a shared run event model, opt-in streaming, local resumable sessions,
pair-preserving context budgeting, and structured run summaries—without weakening
approvals, workspace confinement, or secret-free logging.

## Highlights

- **Event model:** ordered `run.*` / model / tool / approval / usage events via `EventCollector`.
- **Streaming:** `--stream` emits model deltas and tool progress on stderr; final answer stays on stdout.
- **Sessions:** `$ORBITRELAY_HOME/sessions` (default `~/.orbitrelay/sessions`) with `0700`/`0600`, keep-until-delete, `--session` / `--new-session`, and `orbitrelay session list|show|delete|delete-all`.
- **No app-level session encryption** (documented residual risk); secrets never stored in session files.
- **Context budget:** never splits tool-call/result pairs; fails closed on oversized newest segment.
- **Run summaries:** secret-free summary on stderr with `--verbose`.

## Stories

| Story | Title | Status |
|---|---|---|
| e04s01 | Emit a correlated run event model | done |
| e04s02 | Stream model tokens and tool progress | done |
| e04s03 | Persist and resume local sessions | done |
| e04s04 | List show and delete sessions | done |
| e04s05 | Budget context without splitting tool pairs | done |
| e04s06 | Emit structured run summaries | done |
| e04s07 | Document and verify conversations offline | done |

## Verification

- `./scripts/check.sh` green on the feature branch.
- Offline tests cover events, streaming, sessions, context budget, and summaries.
- Threat model: `specs/security/epics/e04/THREAT_MODEL.md`.

## CLI additions

```text
--stream
--session ID
--new-session
orbitrelay session list|show|delete|delete-all --confirm
```

## Out of scope

- App-level encryption of session payloads
- Auto-expiry / TTL purge
- Cloud/multi-device session sync
- Codex event-loop coupling

## Release decision

Prepare a PR from `feat/e04-conversations-and-streaming` into `main` after version bump to 0.5.0 and explicit push approval.
