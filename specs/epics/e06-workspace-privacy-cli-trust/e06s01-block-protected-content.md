STORY KEY: e06s01
TITLE:     Block protected workspace content before disclosure
TYPE:      Story
PARENT:    e06
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      M
type:      fix
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Workspace confinement prevents path escape but currently allows sensitive in-workspace content to reach a hosted model without confirmation.

### 2. Value statement [reviewed]

Users can keep ordinary reads automatic while protected content fails closed before bytes are loaded or disclosed.

### 3. Actors and permissions [reviewed]

- Users select a workspace and may declare an exception before a run.
- Models may request reads but cannot authorize them.
- Private keys and credential stores are denied without exception.

### 4. Trigger and preconditions [reviewed]

D-01 is authoritative; existing traversal, symlink, approval, batch-validation, and event contracts remain active.

### 5. Main flow and business logic [reviewed]

Classify the resolved path during side-effect-free preparation, deny protected paths, and only then allow the read implementation to load bytes.

### 6. Alternative flows and exceptions [reviewed]

Unknown classifier errors fail closed; absolute-deny material stays denied under every approval mode and user exception.

### 7. Interface elements [reviewed]

Denied reads return a stable, secret-free tool/CLI error that explains the policy without returning content.

### 8. Domain model [reviewed]

`ordinary`, `sensitive`, and `absolute-deny` classifications carry a stable reason and no file content. The exact conservative seed catalog and precedence live in `specs/IMPLEMENTATION_PLAN_LATEST.md`.

### 9. Integrations and boundaries [reviewed]

Touches tool preparation, `get_file_content`, approvals, agent batches, events, summaries, and sessions.

### 10. Background processes [reviewed]

None.

### 11. Notifications [reviewed]

The user receives a concise denial on stderr; model-visible results reveal neither protected content nor protected names.

### 12. Audit and logging [reviewed]

Record classification metadata and outcome only; never record raw protected content or credential-shaped values.

### 13. Solution variabilities [reviewed]

Classifier reason codes may evolve additively, but catalog changes require security review; their values and approval reasons are observable contracts.

### 14. Architecture decisions [reviewed]

Introduce one shared privacy-classification result used by preparation and discovery. Reason for Depth: five tool, CLI, event, and session callers must apply identical fail-closed semantics without duplicating secret rules.

### 15. Test strategy [reviewed]

Use temp workspaces and injected agent clients to prove bytes never enter tool results, provider requests, persistence, or diagnostics.

### 16. Observability [reviewed]

Emit secret-free denial metadata; redaction is defense in depth, not the access-control mechanism.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Automatic workspace reads

**Before:** Any path confined to the workspace can be read automatically, including sensitive files.

**After:** Ordinary confined reads remain automatic; sensitive paths fail closed before content is loaded, and private-key or credential-store material is never overridable.

```gherkin
Feature: Protected workspace reads
  Scenario: Ordinary content remains readable
    Given an ordinary confined file
    When the model requests it
    Then the read succeeds without a new prompt

  Scenario: Sensitive content is denied before disclosure
    Given a protected confined file
    When any approval policy requests it
    Then no protected byte enters a tool result or provider request

  Scenario: Absolute deny cannot be overridden
    Given private-key or credential-store material
    When a user exception names it
    Then preparation still denies the read
```

### 18. Dependencies and sequencing [reviewed]

Depends on e05s01 and the early e09s01 gate; precedes e06s02 and e06s03.

### 19. Out of scope [reviewed]

Encryption, content inspection after loading, persistent exceptions, or changing write/execute approval policy.

### 20. Definition of done [reviewed]

Focused privacy, agent, event, summary, session, and security checks pass.

## Implementation Steps

1. Add table-driven direct-read regressions for every conservative sensitive and absolute-deny catalog family → verify: `uv run python -m unittest tests.test_workspace_privacy -v`
2. Enforce classification before bytes enter results or requests under every policy → verify: `uv run python -m unittest tests.test_workspace_privacy tests.test_agent tests.test_approvals -v`
3. Prove denied values never enter events, summaries, errors, or sessions → verify: `uv run python -m unittest tests.test_workspace_privacy tests.test_events tests.test_run_summary tests.test_sessions -v`

## Verification Script (Step-by-Step)

1. Create ordinary, sensitive, private-key, and credential-store fixtures in a temp workspace.
2. Run every approval mode and inspect fake-provider requests.
3. Scan tool results, events, summaries, errors, and session files for sentinel content.
