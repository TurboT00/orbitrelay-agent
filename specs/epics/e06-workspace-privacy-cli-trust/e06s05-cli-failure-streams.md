STORY KEY: e06s05
TITLE:     Receive expected CLI failures without traceback leakage
TYPE:      Story
PARENT:    e06
STATUS:    Complete
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      M
type:      fix
context:   infra
risk:      P0

### 1. Business narrative [reviewed]

Expected configuration, credential, provider, privacy, and session failures must not escape as tracebacks or contaminate final-answer stdout.

### 2. Value statement [reviewed]

CLI users and scripts receive concise, secret-free diagnostics, stable nonzero exits, and final-answer-only stdout.

### 3. Actors and permissions [reviewed]

Users invoke commands; providers, keyrings, sessions, and tools supply typed expected failures; programming defects remain debuggable without being mislabeled.

### 4. Trigger and preconditions [reviewed]

Existing stdout/stderr behavior and redaction contracts are preserved and expanded.

### 5. Main flow and business logic [reviewed]

Translate expected domain/boundary errors once at top-level dispatch, print one diagnostic to stderr, and return a documented nonzero status.

### 6. Alternative flows and exceptions [reviewed]

Unexpected defects are not silently converted to success; interrupt semantics remain conventional and secret-safe.

### 7. Interface elements [reviewed]

Applies to normal, streamed, provider, Codex, and session command paths.

### 8. Domain model [reviewed]

An expected CLI failure contains a stable category, safe message, exit status, and optional recovery hint.

### 9. Integrations and boundaries [reviewed]

Touches `cli.py`, command modules, redaction, streaming, events, and summaries.

### 10. Background processes [reviewed]

None.

### 11. Notifications [reviewed]

Diagnostics go to stderr; successful final answers alone go to stdout.

### 12. Audit and logging [reviewed]

Exception chains, credentials, provider bodies, raw tool arguments, and protected paths are not printed.

### 13. Solution variabilities [reviewed]

Exit categories may share status 1 initially; parse/usage errors retain argparse conventions.

### 14. Architecture decisions [reviewed]

Use one top-level presentation boundary over existing typed exceptions. Reason for Depth: every command path must share stream and redaction rules without duplicating catch/print logic.

### 15. Test strategy [reviewed]

Use subprocess/process-level tests for exit status and exact streams plus injected offline boundary failures.

### 16. Observability [reviewed]

Verbose mode may add safe event summaries on stderr but cannot move diagnostics or final output.

### 17. Acceptance criteria [reviewed]

#### MODIFIED: Expected CLI failure presentation

**Before:** Some expected failures can expose traceback/exception detail or violate final-answer-only stdout.

**After:** Every expected failure produces concise secret-free stderr, no traceback, empty final-answer stdout, and a nonzero exit.

```gherkin
Feature: Trustworthy CLI failures
  Scenario: Expected boundary failure
    Given missing config, unavailable credentials, provider failure, denied read, or invalid session input
    When the command runs
    Then stderr contains one safe diagnostic, stdout contains no diagnostic, and exit is nonzero

  Scenario: Streaming tool failure
    Given a streamed run with a failed tool call
    When the run terminates
    Then progress and diagnostics remain on stderr and no traceback is printed

  Scenario: Secret-bearing exception detail
    Given an injected exception containing a sentinel secret
    When it is translated
    Then the sentinel is absent from both streams
```

### 18. Dependencies and sequencing [reviewed]

Depends on e06s01 and defines the top-level expected-failure vocabulary; e07/e08 CLI stories consume it, while e08s06 later adds tool-specific outcomes beneath it.

### 19. Out of scope [reviewed]

Machine-readable JSON output, telemetry, swallowing programming errors, or changing argparse usage behavior.

### 20. Definition of done [reviewed]

The process-level error matrix, redaction, streaming, agent, and security checks pass.

## Implementation Steps

1. Add process-level contracts for expected configuration, credential, provider, privacy, and session failures → verify: `uv run python -m unittest tests.test_cli_errors -v`
2. Translate expected failures to concise nonzero results without traceback or secret detail → verify: `uv run python -m unittest tests.test_cli_errors tests.test_redaction -v`
3. Preserve final-answer stdout and diagnostic stderr in every run mode → verify: `uv run python -m unittest tests.test_cli_errors tests.test_streaming tests.test_agent -v`

## Verification Script (Step-by-Step)

1. Run each injected failure through both entry points.
2. Assert exit codes and capture stdout/stderr separately.
3. Repeat streamed and tool-call paths and scan for traceback and sentinel secrets.
