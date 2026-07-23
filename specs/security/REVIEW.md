# Security Review — e02s04 Read-Only and Unattended Safety

- Reviewed at: `2026-07-23T22:15:00Z`
- Story baseline: `86488c5`
- Merge base: `8bcefba610a4fd1c66c47e665247325b04ecfdb2`
- Scope: e02s04 production and test changes on `feat/tool-approval-policies`
- Threat model: `specs/security/epics/e02/THREAT_MODEL.md`

## Gate result

**PASS — no unresolved HIGH or CRITICAL findings with confidence >= 8.**

## Data-flow review

1. CLI accepts approval policy and timeout exclusively from explicit arguments;
   timeout is parsed and bounded before `OpenAI` construction.
2. `ApprovalMode.READ_ONLY` replaces the authorizer with a policy that permits
   only read-category requests and returns `read_only_policy` without prompting.
3. Confirm mode treats TTY absence, EOF, expired selector readiness, malformed
   input exhaustion, and a fake `TimeoutError` source as specific denials.
4. `TerminalAuthorizer` uses selectors only for the real `sys.stdin` path. Test
   streams are injected trusted sources; no test waits for wall-clock timeout.
5. The existing agent turns every denial into a correlated tool result before
   executing a handler. Existing workspace/symlink validation remains active for reads.

## Vulnerability assessment

| Category | Result | Evidence |
|---|---|---|
| Authorization bypass | PASS | Read-only denies write/execute without calling injected authorizers; confirm paths fail closed before dispatch. |
| Unattended execution | PASS | Real non-TTY stdin produces `approval_noninteractive`; EOF, timeout, and malformed input cannot approve. |
| Input validation | PASS | Timeout rejects nonnumeric, non-finite, zero, negative, and values above 300 before provider client construction. |
| Prompt spoofing | PASS | Retry count is bounded to three and entered text is neither logged nor reflected. |
| Path traversal | PASS | Policy changes no handler path logic; existing tool and sandbox confinement suite remains green. |
| Secrets exposure | PASS | Policy state and denial reasons contain no provider credentials, arguments, output, or file content. |

## False-positive filtering

- The selector has a platform-specific terminal readiness role only; its timeout
  is bounded and no shell/process construction is added.
- `pre-approved` parses safely but remains fail-closed (`pre_approval_unavailable`)
  until e02s05 supplies an explicit per-tool allowlist.

## Non-blocking residual risks

- Windows terminal certification, remote approvers, persisted policies, and CI
  service integration remain outside P2.
- Pre-approved tool allowlists and sanitized decision audit events remain e02s05/e02s06.

## Security test evidence

- `tests.test_approvals`: read-only, timeout, EOF, malformed retry, and non-TTY policies.
- `tests.test_cli`: policy injection and invalid timeout rejection before client creation.
- `tests.test_agent`: policy denial and timeout denial before write side effects.
- `tests.test_tools` and `tests.test_sandbox`: workspace and symlink confinement unchanged.
- Affected security suite: 64 tests passed in 0.366 seconds.
- Configured Ty and Ruff diagnostics: zero.
