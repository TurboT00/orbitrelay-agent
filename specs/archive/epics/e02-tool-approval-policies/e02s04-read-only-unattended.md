STORY KEY: e02s04
TITLE:     Run safely in read-only or unattended contexts
TYPE:      Story
PARENT:    e02
STATUS:    Refined
AUTHOR:    OrbitRelay team           DATE: 2026-07-23
MATURITY:  4
SIZE:      M
type:      feat
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Interactive confirmation is unsafe when no trusted user can answer. Automation
also needs a strict read-only mode that remains useful without hanging or
silently approving consequential calls.

### 2. Value statement [reviewed]

Users can run OrbitRelay for inspection in terminals, scripts, and pipelines
with deterministic proof that writes and processes cannot start.

### 3. Actors and permissions [reviewed]

- The local user selects policy and timeout through explicit CLI values.
- Noninteractive input has no approval authority under confirm policy.
- The model cannot change read-only or timeout settings.

### 4. Trigger and preconditions [reviewed]

- CLI starts with `confirm` or `read-only` policy.
- Confirm policy may receive TTY, EOF, closed input, invalid input, or timeout.

### 5. Main flow and business logic [reviewed]

1. CLI validates policy and a positive approval timeout, defaulting to 60 seconds.
2. Read-only policy automatically allows confined reads and denies write/execute
   calls without prompting.
3. Confirm policy prompts only through an interactive trusted source.
4. EOF, unavailable input, timeout, or exhausted retries produces a fail-closed
   correlated decision before any side effect.
5. The model may continue with reads or final text after a denial.

### 6. Alternative flows and exceptions [reviewed]

- Invalid policy names, non-finite values, zero, negative values, and excessive
  timeout values fail before client construction.
- Malformed approval input is bounded to a small retry count; exhaustion denies.
- A `StringIO` or fake source supplies deterministic decisions in tests without
  claiming to be a terminal.
- Process execution timeout remains 30 seconds and is not changed by approval
  timeout.

### 7. Interface elements [reviewed]

- `--approval-policy confirm|read-only|pre-approved`, default `confirm`.
- `--approval-timeout SECONDS`, default `60`, used only by confirm policy.
- Read-only and unavailable-input denials do not display misleading prompts.

### 8. Domain model [reviewed]

- **ApprovalMode:** confirm, read-only, or pre-approved.
- **ApprovalSource:** trusted decision input with an explicit timeout outcome.
- **Unavailable decision:** stable EOF, timeout, noninteractive, or invalid-input
  reason mapped to fail-closed denial.

Requirement deltas:

#### ADDED: Read-only run policy
Confined read tools are allowed; write and execution tools are denied without
prompts or side effects.

#### MODIFIED: Unattended consequential call
**Before:** A valid write or execution runs immediately even when stdin is not
interactive.
**After:** Confirm policy denies when trusted interactive input is unavailable,
expires, or cannot produce a valid decision.

#### ADDED: Configurable approval timeout
Interactive confirmation defaults to 60 seconds and accepts an explicit bounded
CLI override; expiry is a denial.

### 9. Integrations and boundaries [reviewed]

- CLI parses policy and timeout before provider client construction.
- Terminal approval source is the only component that waits on stdin.
- Agent and dispatcher consume decisions without knowing terminal mechanics.

### 10. Background processes [reviewed]

No helper thread or daemon is required. The macOS/Linux terminal source uses a
bounded standard-library wait; fake sources model outcomes in tests.

### 11. Notifications [reviewed]

Read-only and unavailable-input outcomes return structured tool failures;
verbose mode may additionally emit sanitized stderr events in e02s06.

### 12. Audit and logging [reviewed]

Decision reasons distinguish policy denial, EOF, timeout, noninteractive input,
and invalid input without recording entered text.

### 13. Solution variabilities [reviewed]

- Timeout defaults to 60 seconds and is explicitly configurable.
- P2 supports macOS/Linux terminal waiting; Windows certification remains P7.
- Retry count and upper timeout bound are implementation constants documented in
  CLI help and tests.

### 14. Quality attributes *NFR* [reviewed]

- Timeout tests use fake sources/clocks and never sleep for wall-clock seconds.
- Noninteractive tests require no provider, keyring, or real terminal.
- Existing CLI startup and profile precedence remain compatible.

### 15. Security and compliance *NFR* [reviewed]

- Every unavailable or ambiguous input path defaults to denial.
- Policy and timeout are accepted only from explicit CLI parsing.
- Read-only mode retains all path/symlink validation.
- Invalid policy values fail before network client construction.

### 16. UX and accessibility *NFR* [reviewed]

- CLI help explains each mode and the timeout unit/default.
- Timeout and noninteractive errors explain how to select read-only or explicit
  pre-approved automation.
- Prompts remain keyboard-only.

### 17. Acceptance criteria [reviewed]

Scenario: Inspect under read-only policy
Given a model requests confined reads and consequential tools
When the run uses read-only policy
Then reads execute while writes and execution return structured policy denials without prompts

Scenario: Fail closed without a TTY
Given confirm policy and noninteractive stdin
When a consequential tool is requested
Then no side effect begins and the model receives an approval-unavailable failure

Scenario: Deny on timeout
Given confirm policy with a fake source that expires
When a valid write or execution needs approval
Then the call is denied before its handler runs

Scenario: Reject invalid timeout before network
Given zero, negative, nonnumeric, non-finite, or excessive timeout input
When the CLI parses the run
Then it exits with an actionable error before constructing the provider client

### 18. Out of scope [reviewed]

- CI service integration, remote approvers, Windows terminal certification,
  persisted policies, and arbitrary shell commands.

### 19. Open questions [reviewed]

None. The user approved configurable 60-second timeout semantics.

### 20. References [reviewed]

- `docs/project-roadmap.md#p2--tool-approval-policies`
- `specs/security/epics/e02/THREAT_MODEL.md`
- `src/orbitrelay/cli.py`

## Prior Art

| Candidate | Source | Verdict | Notes |
|---|---|---|---|
| Standard-library terminal readiness | Python `selectors` | adopt `[OK]` | Suitable for currently supported macOS/Linux; isolate behind approval source. |
| Threads/signals for prompt timeout | Python standard library | reject | Broader lifecycle and signal constraints are unnecessary when input readiness is injectable. |

**Reason for Depth — ApprovalSource:** one timeout-aware input contract isolates
platform-specific terminal readiness and makes EOF/timeout behavior deterministic
without teaching policy logic about file descriptors.

## Implementation steps

1. Add read-only and unavailable-input policy tests, including fake timeout/EOF sources → verify: `uv run python -m unittest tests.test_approvals -v`
2. Add CLI policy and bounded timeout parsing with pre-network validation → verify: `uv run python -m unittest tests.test_cli -v`
3. Apply read-only and fail-closed outcomes across agent batches without prompting or side effects → verify: `uv run python -m unittest tests.test_agent tests.test_tools -v`
4. Preserve confined reads and sandbox failures under every unattended path → verify: `uv run python -m unittest tests.test_tools tests.test_sandbox -v`
5. Run affected security tests and confirm no new findings in input paths → verify: `uv run python -m unittest tests.test_cli tests.test_agent tests.test_tools tests.test_approvals -v && printf '%s\n' 'no new security findings in affected paths'`

## Verification script

1. Run `uv run python -m unittest tests.test_approvals tests.test_cli -v`.
2. Confirm read-only fixtures execute reads and deny writes/execution without a prompt.
3. Confirm EOF, fake timeout, malformed input, and noninteractive fixtures produce
   no write/process side effects.
4. Confirm invalid timeout values fail before the fake OpenAI client is created.
