STORY KEY: e02s05
TITLE:     Run with explicit pre-approved automation
TYPE:      Story
PARENT:    e02
STATUS:    Refined
AUTHOR:    OrbitRelay team           DATE: 2026-07-23
MATURITY:  4
SIZE:      S
type:      feat
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Some trusted automation cannot answer prompts but legitimately needs one
consequential built-in tool. Blanket approval would grant unnecessary authority;
P2 instead requires a visible per-tool allowlist selected by the user.

### 2. Value statement [reviewed]

Automation can perform explicitly named actions without prompts while every
unlisted consequential tool remains fail-closed.

### 3. Actors and permissions [reviewed]

- The local user or invoking automation selects exact built-in tool names.
- The model cannot add tools to the allowlist through arguments or output.
- OrbitRelay may execute only listed tools after normal validation.

### 4. Trigger and preconditions [reviewed]

- CLI selects `pre-approved` policy.
- At least one canonical consequential tool is supplied explicitly.
- Workspace and provider configuration validate normally.

### 5. Main flow and business logic [reviewed]

1. CLI validates each repeated pre-approved tool name against the fixed built-in
   consequential set.
2. It rejects empty, duplicate-ambiguous, read-tool, or unknown entries before
   provider client construction.
3. Listed consequential calls require no prompt and receive an approved decision.
4. Unlisted write/execute calls receive structured `not_preapproved` failures.
5. Every prepared call still passes workspace, symlink, handler-signature, and
   argument validation before execution.

### 6. Alternative flows and exceptions [reviewed]

- Pre-approved mode without any tool names is rejected as unsafe ambiguity.
- Listing `write_file` does not approve `run_python_file`, and vice versa.
- Read tools remain allowed under their ordinary confined-read policy and need
  not appear in the allowlist.
- Approval timeout is invalid/ignored for this no-prompt policy according to
  explicit CLI validation, never silently accepted with ambiguous meaning.

### 7. Interface elements [reviewed]

- `--approval-policy pre-approved` selects deterministic automation.
- Repeatable `--approve-tool write_file|run_python_file` grants exact authority.
- CLI help warns that listed tools may cause side effects without prompting.

### 8. Domain model [reviewed]

- **Pre-approved tool set:** immutable per-run set of canonical consequential
  names supplied by CLI.
- **Decision reason:** `explicit_preapproval` for listed tools and
  `tool_not_preapproved` for unlisted consequential tools.

Requirement deltas:

#### ADDED: Per-tool pre-approved policy
An explicit run policy can allow named built-in consequential tools without
prompts while denying every unlisted consequential tool.

#### MODIFIED: Automation authority
**Before:** Consequential tools execute without a policy boundary.
**After:** Unattended consequential execution requires an exact CLI allowlist;
no environment, workspace, or model value can expand it.

#### MODIFIED: Sandbox enforcement under automation
**Before:** Existing sandbox validation protects direct dispatch.
**After:** The identical validation remains mandatory before every pre-approved
handler execution and is tested against path/symlink escape attempts.

### 9. Integrations and boundaries [reviewed]

- CLI is the only authority for the allowlist.
- Approval session stores the immutable set.
- Dispatcher still prepares every call before policy evaluation and execution.

### 10. Background processes [reviewed]

No background process is added; an approved Python process remains synchronous.

### 11. Notifications [reviewed]

No prompts occur. Verbose mode emits sanitized pre-approval decisions in e02s06.

### 12. Audit and logging [reviewed]

Records identify `explicit_preapproval` and the canonical tool, but do not store
write content or raw process arguments.

### 13. Solution variabilities [reviewed]

Authority is fixed to per-tool allowlisting. A blanket all-tools flag, path
patterns, command patterns, and environment-selected policy are excluded.

### 14. Quality attributes *NFR* [reviewed]

- Policy evaluation is deterministic and does not inspect terminal state.
- Tests remain offline and use fake handlers and temporary workspaces.

### 15. Security and compliance *NFR* [reviewed]

- Unknown or absent allowlist values fail before network access.
- Pre-approval cannot bypass path, symlink, extension, or argument validation.
- Models cannot mutate the immutable allowlist.
- Unlisted tools produce no side effect.

### 16. UX and accessibility *NFR* [reviewed]

- CLI help lists exact accepted tool names and explains their authority.
- Errors name invalid configuration without echoing model arguments.

### 17. Acceptance criteria [reviewed]

Scenario: Pre-approve one write tool
Given pre-approved policy listing only `write_file`
When the model requests a valid write
Then the write executes without a prompt after normal validation

Scenario: Deny an unlisted execution tool
Given only `write_file` is listed
When the model requests `run_python_file`
Then no process starts and the model receives `tool_not_preapproved`

Scenario: Preserve sandbox validation
Given a listed write or execution tool with an escaping path or symlink
When OrbitRelay prepares the call
Then the existing confinement failure is returned and no handler side effect occurs

Scenario: Reject ambiguous pre-approval
Given pre-approved policy with no tools, unknown tools, or model-supplied policy arguments
When the run begins
Then configuration fails or the model override is ignored before side effects

### 18. Out of scope [reviewed]

- Blanket all-tools approval, persistent allowlists, shell command patterns,
  environment-controlled policy, and remote policy distribution.

### 19. Open questions [reviewed]

None. The user selected per-tool allowlisting over blanket approval.

### 20. References [reviewed]

- `specs/product/SCOPE_LATEST.yaml`
- `specs/security/epics/e02/THREAT_MODEL.md`
- `src/orbitrelay/cli.py`
- `src/orbitrelay/tools/__init__.py`

## Prior Art

| Candidate | Source | Verdict | Notes |
|---|---|---|---|
| Argparse choices/repeatable options | Python standard library | adopt `[OK]` | Exact built-in names need no parser dependency. |
| Blanket bypass flag | common CLI pattern | reject | Violates least privilege selected for P2. |

**Reason for Depth — policy-owned allowlist:** keeping the immutable set inside
the approval session gives one auditable authority and avoids checks scattered
across handlers.

## Implementation steps

1. Add pre-approved allowlist and unlisted-tool decision tests → verify: `uv run python -m unittest tests.test_approvals -v`
2. Add CLI policy/allowlist validation and reject ambiguous combinations before client construction → verify: `uv run python -m unittest tests.test_cli -v`
3. Execute listed tools without prompts and deny unlisted consequential tools with correlated results → verify: `uv run python -m unittest tests.test_agent tests.test_tools -v`
4. Re-run sandbox and symlink escape coverage under pre-approved policy → verify: `uv run python -m unittest tests.test_tools tests.test_sandbox -v`
5. Run affected security tests and confirm no new findings in allowlist paths → verify: `uv run python -m unittest tests.test_cli tests.test_agent tests.test_tools tests.test_sandbox tests.test_approvals -v && printf '%s\n' 'no new security findings in affected paths'`

## Verification script

1. Run `uv run python -m unittest tests.test_approvals tests.test_cli tests.test_sandbox -v`.
2. Confirm a listed write executes with zero prompt calls.
3. Confirm an unlisted execution returns a structured denial with zero process calls.
4. Confirm path/symlink escape fixtures remain denied even when their tool is listed.
