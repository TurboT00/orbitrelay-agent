# Security Review — e02s01 Workspace Write Approval

- Reviewed at: `2026-07-23T19:49:07Z`
- Merge base: `8bcefba610a4fd1c66c47e665247325b04ecfdb2`
- Scope: production and test changes for e02s01 against `origin/main`
- Threat model: `specs/security/epics/e02/THREAT_MODEL.md`

## Gate result

**PASS — no unresolved HIGH or CRITICAL findings with confidence >= 8.**

## Data-flow review

1. Model tool-call IDs, names, and JSON arguments enter through
   `agent._validate_tool_calls`; the complete response batch is structurally
   validated before preparation.
2. `prepare_tool` resolves only fixed built-in handlers, overwrites any
   model-supplied workspace, binds handler arguments, validates write argument
   types, and rejects unsafe targets without invoking a handler.
3. `PreparedToolCall` excludes its handler arguments from `repr`; its approval
   request contains only call ID, fixed tool name, category, target, and content
   length. File content remains available only to the eventual approved handler.
4. `ApprovalSession.authorize` receives the complete tuple of valid requests and
   validates that one decision exists per request before execution begins.
5. Denied writes produce correlated JSON errors with fixed fields and never call
   `execute_prepared_tool`.
6. Approved writes execute in original order. `write_file` repeats path and
   symlink confinement at the side-effect boundary.
7. Terminal and verbose previews share bounded `ascii`-escaped formatting and do
   not include write content.

## Vulnerability assessment

| Category | Result | Evidence |
|---|---|---|
| Authorization bypass | PASS | Consequential calls default deny without an injected trusted authorizer; CLI injects the terminal session. |
| Path traversal | PASS | Preparation and execution both use `resolve_path_within`; escape and symlink regressions pass. |
| Secrets exposure | PASS | Approval requests and verbose output exclude raw content; adversarial secret fixture passes. |
| Unsafe deserialization | PASS | Untrusted arguments use `json.loads`; only object values with bound fixed handlers proceed. |
| Command injection | PASS | e02s01 adds no shell construction; Python execution remains a fixed argument-list handler and is not approved by this story. |
| Prompt spoofing | PASS | Fixed labels plus bounded `ascii` formatting prevent raw terminal controls from reaching trusted framing. |

## Gap closed during verification

Non-string write content originally reached `len()` during preparation and could
crash the run before a correlated tool result. Verification reopened e02s01 task
5, added a failing agent-level regression, and now rejects the argument before
approval or side effects.

## Non-blocking residual risks

- Interactive timeout, TTY detection, malformed-input retry limits, and explicit
  unattended policy selection belong to e02s04 and remain fail-closed defaults
  or planned hardening rather than e02s01 release claims.
- Rich Python execution previews belong to e02s02. The current safe default
  denies execution unless an explicit authorizer decides otherwise.
- Filesystem namespace changes between validation and open are mitigated by
  revalidation at execution; power-loss and hostile local-user filesystem races
  are outside the documented trusted-user boundary.

## Security test evidence

- `tests.test_agent`: complete-batch authorization, denial correlation, invalid
  write rejection, and zero side effects.
- `tests.test_tools`: preparation/execution split, unsafe target rejection, and
  secret-free verbose previews.
- `tests.test_sandbox`: symlink and workspace confinement.
- `tests.test_approvals`: immutable safe request and explicit decisions.
- Affected security suite: 35 tests passed.
- Full project suite: 115 project tests and 9 example tests passed.
