# PR draft — feat/tool-approval-policies → main

**Do not open until push is explicitly requested.**

## Title

`feat(approval): ship tool approval policies (0.3.0)`

## Body

```markdown
## Summary
- Add batch-first tool approval for workspace writes and local Python execution.
- Support `confirm`, `read-only`, and exact per-tool `pre-approved` policies.
- Add run-scoped tool disable and secret-free verbose approval audit events.
- Bump package version to **0.3.0** and document the new safety boundary.

## Stories
- e02s01 write approval
- e02s02 Python execution approval
- e02s03 run-scoped disable
- e02s04 read-only / unattended fail-closed
- e02s05 exact pre-approved allowlists
- e02s06 secret-free decision auditing

## Test plan
- [x] `./scripts/check.sh` (145 project + 9 example tests, sdist/wheel smoke)
- [x] Ty/Ruff clean on touched modules
- [x] Offline policy/confinement/security regressions
- [x] Live UAT for read-only and pre-approved paths during story verify-work

## Notes
- Branch was developed as one coherent P2 release on top of merged P1.
- No remote push was performed during implementation.
- Release notes: `specs/archive/RELEASE-0.3.0-tool-approval-policies.md`
```

## Suggested commands (only after explicit push approval)

```bash
git push -u origin feat/tool-approval-policies
gh pr create --base main --head feat/tool-approval-policies \
  --title "feat(approval): ship tool approval policies (0.3.0)" \
  --body-file specs/archive/PR-0.3.0-tool-approval-policies.md
```
