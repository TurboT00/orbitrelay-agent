# Security Review — e02s03 Run-Scoped Tool Disable

- Reviewed at: `2026-07-23T21:55:00Z`
- Story baseline: `d17d85f`
- Merge base: `8bcefba610a4fd1c66c47e665247325b04ecfdb2`
- Scope: e02s03 production and test changes on `feat/tool-approval-policies`
- Threat model: `specs/security/epics/e02/THREAT_MODEL.md`

## Gate result

**PASS — no unresolved HIGH or CRITICAL findings with confidence >= 8.**

## Data-flow review

1. Only the trusted terminal authorizer can turn explicit `d`/`disable` input
   into a `user_disabled_tool` decision; model arguments never enter this path.
2. `ApprovalSession` owns a private set of canonical prepared tool names. Its
   public view is an immutable `frozenset` and there is no model-facing reset API.
3. Already-disabled requests are removed before the authorizer is called. New
   disable decisions are applied in original request order so repeated same-tool
   calls in the prepared batch become `tool_disabled_for_run` without another prompt.
4. Agent execution receives the complete normalized decision tuple before any
   handler runs and returns correlated `tool_disabled` results for both the
   initiating and automatic denials.
5. CLI construction creates a new `ApprovalSession` for every invocation, so
   disabled state is never persisted or shared with a later run or profile.

## Vulnerability assessment

| Category | Result | Evidence |
|---|---|---|
| Authorization bypass | PASS | Disabled requests are denied before handler dispatch; models cannot create, clear, or mutate session state. |
| State leakage | PASS | State is instance-local, in-memory, bounded by built-in tool names, and fresh for every CLI run. |
| Decision confusion | PASS | Initiating and automatic reasons are distinct; agent maps both to one correlated `tool_disabled` error code. |
| Batch ordering | PASS | Candidate decisions are indexed to original requests; same-tool normalization cannot shift a later tool's decision. |
| Secrets exposure | PASS | Disabled state stores only canonical tool names and no arguments, results, credentials, paths, or content. |
| Prompt spoofing | PASS | Disable is a fixed trusted choice in the existing bounded approval prompt. |

## False-positive filtering

- A trusted injected test authorizer can return `user_disabled_tool`; dependency
  injection is an intentional trusted boundary and is not model-reachable.
- Repeated disabled calls could consume model turns, but resource-exhaustion and
  model persistence concerns are excluded and no side effect or repeated prompt occurs.

## Non-blocking residual risks

- Persistent policy, category/path patterns, re-enable, and cross-process state
  remain explicitly out of scope.
- Unattended policy, pre-approved automation, and sanitized verbose audit events
  remain planned for e02s04 through e02s06.

## Security test evidence

- `tests.test_approvals`: disable transition, automatic denial, deny-once, and fresh-session reset.
- `tests.test_agent`: cross-round suppression, same-batch suppression, other-tool continuity, and correlated results.
- `tests.test_cli`: independent invocations receive independent approval sessions.
- Affected security suite: 37 tests passed in 0.010 seconds.
- Configured Ty and Ruff diagnostics: zero.
