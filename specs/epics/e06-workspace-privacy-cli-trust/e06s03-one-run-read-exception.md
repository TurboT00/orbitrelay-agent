STORY KEY: e06s03
TITLE:     Authorize an exact sensitive read for one run
TYPE:      Story
PARENT:    e06
STATUS:    Complete
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      L
type:      feat
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Some legitimate tasks require a sensitive file, but model-triggered or persistent exceptions would defeat the privacy boundary.

### 2. Value statement [reviewed]

A user can authorize one exact file or explicit subtree before a run without granting broader or future access.

### 3. Actors and permissions [reviewed]

Only the invoking user declares exceptions; the model and approval prompts cannot create or widen them.

### 4. Trigger and preconditions [reviewed]

e06s01/e06s02 classification is stable; absolute denies remain non-overridable.

### 5. Main flow and business logic [reviewed]

Parse and validate user-declared paths, inject an immutable run-scoped authorization set, and make only the exact file or explicit subtree readable/discoverable while absolute denies remain omitted.

### 6. Alternative flows and exceptions [reviewed]

Invalid, escaped, missing, symlinked, model-supplied, or absolute-deny requests fail before provider access.

### 7. Interface elements [reviewed]

The top-level CLI accepts repeatable exact-path and explicit-subtree declarations with clear help and validation errors.

### 8. Domain model [reviewed]

A run exception records normalized workspace-relative path, scope (`file` or `subtree`), process lifetime, and authorized discovery semantics only.

### 9. Integrations and boundaries [reviewed]

Touches CLI parsing, tool preparation, approval policy, agent setup, and ephemeral session callbacks.

### 10. Background processes [reviewed]

None; exception state dies with the process.

### 11. Notifications [reviewed]

CLI diagnostics identify an invalid declaration without echoing protected content.

### 12. Audit and logging [reviewed]

Persist no exception set; events may record that user authority existed, not raw sensitive content.

### 13. Solution variabilities [reviewed]

Exact flag spelling is fixed during RED tests and documented once; no interactive model-time override is permitted.

### 14. Architecture decisions [reviewed]

Represent authority as immutable run input to the shared classifier. Reason for Depth: authority must be distinguishable from model tool arguments and ordinary approval decisions.

### 15. Test strategy [reviewed]

Process-level CLI tests cover exact/subtree boundaries, invalid paths, absolute denies, later processes, and resumed sessions.

### 16. Observability [reviewed]

Diagnostics state scope and expiry; secret values remain absent.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Sensitive-read authorization

**Before:** Sensitive reads are either automatic under confinement or, after e06s01, denied with no explicit user exception.

**After:** A pre-run user declaration can make one exact sensitive file or subtree readable and discoverable for that process only, while absolute-deny material remains omitted and unreadable.

```gherkin
Feature: One-run sensitive read exception
  Scenario: Exact file is authorized
    Given a valid user-declared sensitive file
    When that file is requested in the same process
    Then it is readable and sibling paths remain denied

  Scenario: Subtree is bounded
    Given an explicit authorized subtree
    When a path outside it or through a symlink is requested
    Then the request is denied

  Scenario: Authorized discovery is scoped
    Given an exact-file or subtree declaration
    When the parent or subtree is listed
    Then only authorized non-absolute-deny protected entries become visible

  Scenario: Authority expires
    Given a prior authorized run
    When a later process or ordinary resume requests the path
    Then no exception is present
```

### 18. Dependencies and sequencing [reviewed]

Depends on e06s01/e06s02; precedes e06s04.

### 19. Out of scope [reviewed]

Persistent allowlists, model-triggered prompts, credential-material override, or implicit authorization from session history.

### 20. Definition of done [reviewed]

CLI, classifier, agent, approval, and session regressions pass with no widened authority.

## Implementation Steps

1. Add CLI contracts for exact file, subtree, invalid path, and absolute-deny declarations → verify: `uv run python -m unittest tests.test_workspace_privacy tests.test_cli_connections -v`
2. Apply immutable process-scoped user authority without model-triggered widening → verify: `uv run python -m unittest tests.test_workspace_privacy tests.test_agent tests.test_approvals -v`
3. Keep authorized sensitive turns ephemeral and prove authority expires → verify: `uv run python -m unittest tests.test_workspace_privacy tests.test_sessions -v`

## Verification Script (Step-by-Step)

1. Invoke the CLI against one exact file and one subtree in a temp workspace.
2. Attempt sibling, traversal, symlink, and absolute-deny reads.
3. Start a second process and resume an ordinary session; confirm the exception is absent.
