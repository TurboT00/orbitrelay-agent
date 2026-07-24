# PR draft — feat/e03-supported-hosted-access → main

**Do not open until push is explicitly requested.**

## Title

`feat(hosted): ship supported hosted access (0.4.0)`

## Body

```markdown
## Summary
- Add xAI BYOK (`XAI_API_KEY`, profile `--preset xai`, grok-4.5 defaults).
- Add SuperGrok/X Premium device-code OAuth with keyring-only tokens and fail-closed refresh/403 handling.
- Add Codex CLI bridge (`status` / `login` / `logout` / `exec`) without reading auth.json.
- Keep P2 tool approvals for OrbitRelay local tools on Chat Completions paths.
- Bump package version to **0.4.0** and document hosted-access setup in README.

## Stories
- e03s01 xAI BYOK profile
- e03s02 SuperGrok OAuth login lifecycle
- e03s03 SuperGrok-backed agent loop
- e03s04 Codex detect/version
- e03s05 Codex login/logout delegation
- e03s06 Codex exec alternate runtime
- e03s07 docs + offline verification

## Test plan
- [x] `./scripts/check.sh` (offline project + example tests, sdist/wheel smoke)
- [x] SuperGrok OAuth fake-server tests (login/status/logout/refresh quarantine)
- [x] Codex bridge fake PATH/subprocess tests (detect/login/exec/no yolo)
- [x] Existing approval/profile/sandbox regressions still green

## Security notes
- Never reads `CODEX_HOME/auth.json` or `~/.grok/auth.json`
- OAuth tokens only in OS keyring; profile metadata remains secret-free
- Codex exec does not default to approval/sandbox bypass flags
- Threat model: `specs/security/epics/e03/THREAT_MODEL.md`

## Notes
- Release notes: `specs/archive/RELEASE-0.4.0-supported-hosted-access.md`
- No remote push was performed during implementation.
```

## Suggested commands (only after explicit push approval)

```bash
git push -u origin feat/e03-supported-hosted-access
gh pr create --base main --head feat/e03-supported-hosted-access \
  --title "feat(hosted): ship supported hosted access (0.4.0)" \
  --body-file specs/archive/PR-0.4.0-supported-hosted-access.md
```
