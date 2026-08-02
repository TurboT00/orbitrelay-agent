STORY KEY: e02s06
TITLE:     Audit approval decisions without secret leakage
TYPE:      Story
PARENT:    e02
STATUS:    Refined
AUTHOR:    OrbitRelay team           DATE: 2026-07-23
MATURITY:  4
SIZE:      S
type:      feat
context:   domain
risk:      P1

### 1. Business narrative [reviewed]

Once multiple policies and outcomes exist, users need to understand what was
approved or denied during a run. Raw tool arguments and results are unsafe audit
material, so P2 closes with a bounded, secret-free decision trail.

### 2. Value statement [reviewed]

Verbose users can verify the consent decisions OrbitRelay made without exposing
provider credentials, file content, process arguments, or tool results.

### 3. Actors and permissions [reviewed]

- The local user may enable verbose decision output.
- OrbitRelay records only policy metadata needed to explain a decision.
- Models receive correlated tool outcomes but never the internal audit collection.

### 4. Trigger and preconditions [reviewed]

- An approval session evaluates read, approved, denied, disabled, unavailable,
  or pre-approved calls.
- CLI may enable `--verbose`.

### 5. Main flow and business logic [reviewed]

1. Every prepared call receives one disposition and stable reason.
2. The session appends one immutable record with call ID, canonical tool,
   category, disposition, safe target, argument count, and reason.
3. It never copies write content, raw process arguments, provider data, or handler
   output into the record.
4. Under verbose mode, OrbitRelay emits a sanitized, control-escaped event to
   stderr in call order.
5. Normal final text and tool-result content retain their existing channels.

### 6. Alternative flows and exceptions [reviewed]

- Invalid/unprepared calls retain existing tool errors and do not invent an
  approval record unless policy evaluation occurred.
- Automatic read approval, user approval, deny-once, disable, automatic disabled
  denial, timeout, noninteractive denial, and pre-approval have distinct reasons.
- Redaction handles nested credential-like keys in any diagnostic mapping.
- Audit formatting failure cannot authorize or execute a call.

### 7. Interface elements [reviewed]

- No new flag beyond existing `--verbose`.
- Events go to stderr, one line per decision, with trusted labels and escaped
  bounded values.
- Normal nonverbose runs emit no audit lines.

### 8. Domain model [reviewed]

- **ApprovalRecord:** immutable call ID, tool, category, disposition, reason,
  safe target, argument count, and sequence number.
- **Disposition:** allowed, denied, or disabled; reason supplies exact origin.

Requirement deltas:

#### ADDED: Run-local approval decision trail
Every evaluated call has a secret-free, correlated record available for the
duration of one run.

#### MODIFIED: Verbose tool diagnostics
**Before:** Verbose dispatch prints raw non-workspace arguments to stdout and can
include write content or process argument values.
**After:** Decision events use sanitized metadata on stderr; raw write content,
raw process arguments, provider secrets, and tool results are never logged.

#### ADDED: Stable decision reasons
Approval outcomes expose stable reason codes for user approval, policy denial,
timeout, unavailable input, run disable, automatic disabled denial, explicit
pre-approval, and missing pre-approval.

### 9. Integrations and boundaries [reviewed]

- Approval session owns records and sequence.
- CLI supplies the verbose stderr sink.
- Existing recursive redaction protects diagnostic mappings.
- Agent tool results remain separate from audit events.

### 10. Background processes [reviewed]

Not applicable: records and output are synchronous and run-local.

### 11. Notifications [reviewed]

Verbose stderr events are the only audit notification; P2 adds no file, network,
or external telemetry sink.

### 12. Audit and logging [reviewed]

- Record allowlisted metadata only; do not redact after copying forbidden data.
- Escape control characters and bound every model-controlled display field.
- Preserve event order and call ID correlation.

### 13. Solution variabilities [reviewed]

- Output is verbose-only stderr as explicitly selected by the user.
- Records are run-local and are not serialized or retained.
- No metrics/telemetry package is added.

### 14. Quality attributes *NFR* [reviewed]

- Formatting is deterministic and independently unit tested.
- Audit collection adds bounded memory proportional to the existing maximum tool
  calls in the eight-response loop.
- Nonverbose performance and output remain compatible.

### 15. Security and compliance *NFR* [reviewed]

- Provider credentials and environment mappings are never available to records.
- Write content, raw process arguments, stdout, stderr, and tool results are
  categorically excluded.
- Hostile terminal controls and oversized values cannot escape trusted framing.
- Audit failure never changes an approval disposition.

### 16. UX and accessibility *NFR* [reviewed]

- Events use concise stable labels suitable for screen readers and log capture.
- stderr separation preserves machine-readable/final stdout.
- Reason codes are paired with understandable text.

### 17. Acceptance criteria [reviewed]

Scenario: Inspect verbose decisions
Given a run with approved, denied, disabled, and read calls
When verbose mode is enabled
Then stderr contains ordered sanitized events with matching call IDs and reasons

Scenario: Preserve normal output
Given the same run without verbose mode
When OrbitRelay completes
Then no audit event is printed and final stdout remains unchanged

Scenario: Exclude secrets and tool data
Given credential-like fixtures in write content, process arguments, diagnostics, and tool results
When decisions are recorded and formatted
Then none of those values or fragments appears in records or stderr

Scenario: Escape hostile metadata
Given paths containing control characters and oversized segments
When verbose events are emitted
Then control characters are escaped, output is bounded, and trusted framing remains intact

### 18. Out of scope [reviewed]

- Persistent audit files, conversation history, external telemetry, metrics
  dashboards, remote audit APIs, and replay of approval decisions.

### 19. Open questions [reviewed]

None. The user selected run-local records and verbose-only stderr output.

### 20. References [reviewed]

- `specs/security/epics/e02/THREAT_MODEL.md`
- `src/orbitrelay/redaction.py`
- `src/orbitrelay/tools/__init__.py`
- `src/orbitrelay/agent.py`

## Prior Art

| Candidate | Source | Verdict | Notes |
|---|---|---|---|
| Existing recursive redaction | `orbitrelay.redaction` | extend `[OK]` | Keep defensive diagnostic handling, but avoid collecting forbidden values first. |
| Python logging/telemetry package | external | reject | P2 needs no persistence or dependency. |

**Reason for Depth — ApprovalRecord:** one allowlisted immutable record makes
forbidden fields structurally unavailable to every formatter and future caller.

## Implementation steps

1. Add allowlisted approval record and stable reason tests across every policy outcome → verify: `uv run python -m unittest tests.test_approvals -v`
2. Remove raw verbose argument printing and add bounded control-safe decision formatting → verify: `uv run python -m unittest tests.test_tools tests.test_redaction -v`
3. Emit ordered verbose events to stderr without changing nonverbose stdout or tool results → verify: `uv run python -m unittest tests.test_cli tests.test_agent -v`
4. Add adversarial secret, control-character, oversized-value, and correlation fixtures → verify: `uv run python -m unittest tests.test_approvals tests.test_redaction tests.test_agent -v`
5. Run the full gate and confirm no new security findings in affected paths → verify: `./scripts/check.sh && printf '%s\n' 'no new security findings in affected paths'`

## Verification script

1. Run `./scripts/check.sh`.
2. Run approval fixtures once with verbose disabled and once enabled.
3. Confirm stdout and tool-result payloads are unchanged between modes.
4. Confirm verbose stderr contains ordered call IDs/reasons but none of the seeded
   credentials, write content, process arguments, controls, or tool results.
