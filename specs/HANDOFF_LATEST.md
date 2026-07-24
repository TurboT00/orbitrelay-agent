# Agent Handoff — After P4 0.5.0

**Audience:** a fresh coding agent with no prior conversation memory  
**Date:** 2026-07-24  
**Repo root:** working copy of `TurboT00/orbitrelay-agent` on branch `main`  
**Baseline:** `v0.5.0` released; HEAD should be at or after `a29e5dc`

---

## What just shipped

P4 Conversations and Streaming is complete:

- Merge: `a29e5dc` on `main`
- Tag/Release: https://github.com/TurboT00/orbitrelay-agent/releases/tag/v0.5.0
- Package version: `0.5.0`
- Notes: `specs/archive/RELEASE-0.5.0-conversations-and-streaming.md`

Delivered:

1. Shared run event model
2. Opt-in `--stream` (deltas/progress on stderr)
3. Local sessions under `$ORBITRELAY_HOME/sessions` (0700/0600, keep-until-delete)
4. Session list/show/delete lifecycle
5. Pair-preserving context budgeting
6. Verbose run summaries

## Cold-start checklist

```bash
git status -sb
git log -3 --oneline
git describe --tags --always
./scripts/check.sh
```

Expect clean `main`, tag `v0.5.0`, green checks.

## Next mission

Do **not** start coding immediately. When the user directs:

**P5 — Qualified local models** (Ollama loopback first; see `docs/project-roadmap.md`)

Recommended first skills: `survey-context` → `scope-work`.

## Locked decisions (do not reopen without user direction)

- Native OS credential store only
- Codex = official CLI process boundary only; never read auth.json
- SuperGrok OAuth + xAI BYOK both supported
- Approvals batch-first, fail-closed, run-local
- Sessions per-user under OrbitRelay home; 0700/0600; keep-until-delete; no app-level encryption in P4

## Explicit non-goals until directed

- P5 local models, P6 plugins, P7 Windows
- App-level session encryption / auto-TTL
- Push/publish without explicit user request
