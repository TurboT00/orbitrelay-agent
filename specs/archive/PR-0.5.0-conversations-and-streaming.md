# PR draft — feat/e04-conversations-and-streaming → main

**Do not open until push is explicitly requested.**

## Title

`feat(conversations): ship streaming and local sessions (0.5.0)`

## Body

```markdown
## Summary
- Add shared run event model for model/tool/approval/usage/completion.
- Add opt-in `--stream` (deltas/progress on stderr; final answer on stdout).
- Add local resumable sessions under ORBITRELAY_HOME/sessions (0700/0600, keep-until-delete).
- Add session list/show/delete lifecycle commands.
- Add pair-preserving context budgeting and verbose run summaries.
- Document security posture (no app-level session encryption; secrets stay in keyring).
- Bump package version to **0.5.0**.

## Stories
- e04s01–e04s07 (events, stream, sessions, budget, summary, docs)

## Test plan
- [x] `./scripts/check.sh`
- [x] Offline unit/integration tests for events/streaming/sessions/budget/summary
- [x] Existing approval/profile/auth/codex regressions green

## Notes
- Release notes: `specs/archive/RELEASE-0.5.0-conversations-and-streaming.md`
- Threat model: `specs/security/epics/e04/THREAT_MODEL.md`
```
