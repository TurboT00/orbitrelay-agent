STORY KEY: e03s06
TITLE:     Run a Codex exec alternate runtime path
TYPE:      Story
PARENT:    e03
STATUS:    Done
AUTHOR:    OrbitRelay team           DATE: 2026-07-24
MATURITY:  3
SIZE:      L
type:      feat
context:   domain
risk:      P0

### 1. Business narrative [reviewed]

Chat Completions tool-loop compatibility is not Codex. Users need a deliberate
alternate path that runs `codex exec` noninteractively against a workspace and
returns machine-readable results without OrbitRelay claiming Codex’s sandbox as
its own.

### 2. Value statement [reviewed]

For a logged-in Codex user, OrbitRelay can run one noninteractive coding task
via `codex exec --json` in a chosen workspace and surface the final message.

### 3. Actors and permissions [reviewed]

- User supplies prompt/workspace and accepts Codex-owned tool side effects.
- Codex CLI performs model/tools under its policies.
- OrbitRelay only orchestrates subprocess I/O.

### 4. Trigger and preconditions [reviewed]

- Codex available (e03s04) and authenticated per `codex login status` (e03s05).
- Workspace path validated as a directory OrbitRelay is willing to pass through.

### 5. Main flow and business logic [reviewed]

1. Verify codex present (+ optional status check).
2. Invoke `codex exec --json --cd <workspace> [ -o <final> ] <prompt>` with fixed argv.
3. Stream/parse JSONL events enough to detect success/failure and capture final message.
4. Return exit code and user-visible summary without pretending it was the Chat Completions loop.

### 6. Alternative flows and exceptions [reviewed]

- Not logged in → instruct `codex login` via OrbitRelay delegation.
- Non-zero exec → fail with sanitized stderr/event error.
- Never pass `--dangerously-bypass-approvals-and-sandbox` by default.
- Version warning only; do not hard-block unknown versions.

### 7. Interface elements [reviewed]

- Explicit Codex run entry (flag or subcommand) distinct from default agent loop.

### 8. Domain model [reviewed]

#### ADDED: CodexExecResult
exit_code, final_message, events_summary, version_warning.

### 9. Integrations and boundaries [reviewed]

Documented noninteractive Codex surface only.

### 10. Background processes [reviewed]

Subprocess lifetime bound to the command.

### 11. Notifications [reviewed]

Terminal progress from Codex JSONL optional; minimum is final message + status.

### 12. Audit and logging [reviewed]

Do not log full event payloads if they may contain secrets; prefer last message + exit.

### 13. Solution variabilities [reviewed]

How much JSONL to parse vs rely on `-o` final message file.

### 14. Architecture decisions [reviewed]

Alternate runtime path — not a provider behind agent.py.

### 15. Test strategy [reviewed]

Fake codex emitting JSONL success/failure; assert argv includes --json and --cd.

### 16. Observability [reviewed]

Exit code + final message.

### 17. Acceptance criteria [reviewed]

```gherkin
Feature: Codex exec alternate runtime
  Scenario: Successful exec returns final message
    Given a fake codex exec that emits JSONL turn.completed and writes -o output
    When the user runs a Codex task against a temp workspace
    Then argv includes exec, --json, and --cd workspace
    And OrbitRelay reports the final message and exit 0

  Scenario: Missing authentication
    Given codex login status exits non-zero
    When the user runs a Codex task
    Then OrbitRelay fails closed with login guidance

  Scenario: Default refuses yolo bypass
    When constructing the default exec argv
    Then it does not include --dangerously-bypass-approvals-and-sandbox
```

### 18. Dependencies and sequencing [reviewed]

Depends on e03s04 and e03s05.

### 19. Out of scope [reviewed]

Interactive Codex TUI session hosting, MCP management, plugin install.

### 20. Definition of done [reviewed]

Offline exec bridge tests green; docs state Codex owns sandbox/approvals.
