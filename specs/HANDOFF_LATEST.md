# Agent Handoff — After P3 0.4.0

**Audience:** a fresh coding agent with no prior conversation memory  
**Date:** 2026-07-24  
**Repo root:** working copy of `TurboT00/orbitrelay-agent` on branch `main`  
**Baseline:** `v0.4.0` released; HEAD should be at or after `a983f94`

---

## What just shipped

P3 Supported Hosted Access is complete:

- PR: https://github.com/TurboT00/orbitrelay-agent/pull/3
- Tag/Release: https://github.com/TurboT00/orbitrelay-agent/releases/tag/v0.4.0
- Package version: `0.4.0`
- Notes: `specs/archive/RELEASE-0.4.0-supported-hosted-access.md`

Delivered:

1. xAI BYOK (`XAI_API_KEY`, `--preset xai`, grok-4.5 defaults)
2. SuperGrok/X Premium device-code OAuth (keyring-only tokens)
3. Codex CLI bridge (`status` / `login` / `logout` / `exec`) without reading auth.json

## Cold-start checklist

```bash
git status -sb
git log -3 --oneline
git describe --tags --always
./scripts/check.sh
```

Expect clean `main`, tag `v0.4.0`, green checks.

## Next mission

Do **not** start coding immediately. When the user directs:

**P4 — Conversations and streaming** (see `docs/project-roadmap.md`)

Recommended first skills: `survey-context` → `scope-work`.

## Locked decisions (do not reopen)

- Native OS credential store only
- Codex = official CLI process boundary only; never read auth.json
- SuperGrok OAuth + xAI BYOK are both supported; API-key billing ≠ subscription
- Approvals stay batch-first, fail-closed, run-local

## Explicit non-goals until directed

- P5 local models, P6 plugins, P7 Windows, CI introduction
- Push/publish without explicit user request
