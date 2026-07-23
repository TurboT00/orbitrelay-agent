# Security Review — e02s05 Explicit Pre-Approved Automation

- Reviewed at: `2026-07-23T22:35:00Z`
- Story baseline: `e2b044f`
- Merge base: `8bcefba610a4fd1c66c47e665247325b04ecfdb2`
- Scope: e02s05 production and test changes on `feat/tool-approval-policies`
- Threat model: `specs/security/epics/e02/THREAT_MODEL.md`

## Gate result

**PASS — no unresolved HIGH or CRITICAL findings with confidence >= 8.**

## Data-flow review

1. CLI is the only allowlist authority. `--approve-tool` is validated before
   `OpenAI` construction and only when `--approval-policy pre-approved` is set.
2. Accepted names are restricted to the fixed consequential set
   `{write_file, run_python_file}`; empty, duplicate, read-tool, and unknown
   entries raise configuration errors.
3. `ApprovalSession` stores an immutable `frozenset` of approved tool names and
   returns `explicit_preapproval` only for exact matches.
4. Unlisted consequential tools receive `tool_not_preapproved` and never reach
   handlers. Read tools continue under ordinary confined-read policy.
5. Preparation still runs before authorization, so path/symlink confinement
   failures remain side-effect free even when the tool name is listed.

## Vulnerability assessment

| Category | Result | Evidence |
|---|---|---|
| Authorization bypass | PASS | Listing `write_file` does not approve `run_python_file`; unlisted execution starts no process. |
| Allowlist authority | PASS | Model arguments cannot expand the set; only CLI flags construct `approved_tools`. |
| Ambiguous automation | PASS | Pre-approved mode without tools, tools without pre-approved mode, duplicates, and unknown names fail before client creation. |
| Path traversal | PASS | Pre-approved agent batches with escaping write/exec symlinks still return confinement errors and leave outside files untouched. |
| Secrets exposure | PASS | Decision reasons name tools and policy only; write content and process arguments remain out of approval state. |
| Privilege expansion | PASS | No blanket all-tools flag, environment policy, path patterns, or persistent allowlist was added. |

## False-positive filtering

- Empty `approved_tools` on a directly constructed session remains fail-closed
  (`tool_not_preapproved`); the CLI path rejects that configuration as ambiguous.
- Approval timeout remains validated for all policies for parse simplicity; it is
  unused by the no-prompt pre-approved authorizer and cannot approve tools.

## Non-blocking residual risks

- Windows terminal certification, remote approvers, and CI service integration
  remain outside P2.
- Sanitized verbose decision audit events remain e02s06.

## Security test evidence

- `tests.test_approvals`: listed write approved; unlisted execution denied.
- `tests.test_cli`: allowlist injection and ambiguous configuration rejection before client creation.
- `tests.test_agent`: pre-approved write executes; unlisted execution denied; symlink escapes still confined.
- `tests.test_tools` and `tests.test_sandbox`: preparation and symlink confinement remain green.
- Affected security suite: 76 tests passed in 0.406 seconds.
