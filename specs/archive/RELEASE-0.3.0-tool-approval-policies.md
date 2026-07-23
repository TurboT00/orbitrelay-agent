# OrbitRelay 0.3.0 — Tool Approval Policies

- Branch: `feat/tool-approval-policies`
- Base: `8bcefba610a4fd1c66c47e665247325b04ecfdb2` (`main` after P1)
- Package version: `0.3.0`
- Push: not requested (local release handoff only)

## Summary

0.3.0 makes user consent the default boundary for consequential tools. Reads stay
workspace-confined. Writes and local Python execution require an explicit policy
decision before any handler side effect.

## Highlights

- Batch-first authorization: validate and authorize complete tool-call batches
  before executing approved calls in original order.
- Interactive confirmations with safe previews, run-scoped disable (`d`), and
  fail-closed timeout/EOF/noninteractive/invalid-input handling.
- `--approval-policy read-only` for unattended inspection without prompts.
- `--approval-policy pre-approved --approve-tool TOOL` for exact allowlists.
- Secret-free verbose approval audit events on stderr.
- Existing path/symlink/argument confinement preserved under every policy.

## Stories

| Story | Title | Status |
|---|---|---|
| e02s01 | Approve or deny a workspace file write | done |
| e02s02 | Approve or deny local Python execution | done |
| e02s03 | Disable a tool for the current run | done |
| e02s04 | Run safely in read-only or unattended contexts | done |
| e02s05 | Run with explicit pre-approved automation | done |
| e02s06 | Audit approval decisions without secret leakage | done |

## Verification

- `./scripts/check.sh` green on the release branch.
- Project tests: 145 offline unit/integration tests.
- Example tests: 9 calculator tests.
- Package artifacts: `orbitrelay_agent-0.3.0` sdist + wheel + isolated CLI smoke.
- Final check sha256: `3fe858ca9ebb194c15c841018f233bca66651525ed61ff207fa8c488cf3226b6`
- Evidence: `specs/verifications/e02s0{1..6}-verify.yaml` and matching audits.
- Security reviews recorded under `specs/security/REVIEW.md` per story cycle.

## CLI additions

```text
--approval-policy {confirm,read-only,pre-approved}
--approval-timeout SECONDS
--approve-tool TOOL   # repeatable; write_file | run_python_file
--verbose             # also emits approval audit lines on stderr
```

## Out of scope (intentionally deferred)

- Remote approval, persistent policy state, plugins
- Blanket all-tools approval
- Persistent audit files / external telemetry
- Windows certification (P7)
- Codex bridge, conversations, local models (later roadmap)

## Release decision

Prepare a PR from `feat/tool-approval-policies` into `main` when push is
explicitly requested. Do not force-push. Semantic version bump is **minor**
(`0.1.0` package baseline on main → `0.3.0` coherent P1+P2 product target;
package metadata is set to `0.3.0` on this branch).
