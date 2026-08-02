# Impact Assessment — e02 Tool Approval Policies

## Target

P2 introduces a consent boundary across these existing shared modules and
symbols:

- `src/orbitrelay/agent.py::run_agent`
- `src/orbitrelay/tools/__init__.py::execute_tool`
- `src/orbitrelay/tools/write_file.py::write_file`
- `src/orbitrelay/tools/run_python_file.py::run_python_file`
- `src/orbitrelay/cli.py::{parse_args,_invoke_agent,main}`

## Zoom-out mandate

### Agent loop

- **Purpose:** orchestrate at most eight model responses, validate tool-call
  batches, execute tools, correlate results by call ID, and return final text.
- **Callers:** `_invoke_agent` in `cli.py` plus direct offline tests in
  `tests/test_agent.py`.
- **Contracts:** validate every call in a response before executing any call;
  preserve assistant reasoning content; execute validated calls in order;
  append exactly one correlated tool result per call; never execute calls after
  the response limit.

### Tool dispatcher

- **Purpose:** map the four fixed tool names to handlers, decode object-shaped
  JSON arguments, inject the trusted workspace, and convert handler failures to
  tool-result strings.
- **Callers:** `run_agent` plus direct tests in `tests/test_tools.py`.
- **Contracts:** models cannot override the workspace; unknown tools and invalid
  arguments return structured error strings; the dispatcher catches handler
  exceptions; existing read/write/execute schemas remain stable.

### Consequential handlers

- **Purpose:** `write_file` performs a confined file mutation;
  `run_python_file` validates and launches one workspace-confined Python file.
- **Callers:** the dispatcher registry plus direct sandbox tests.
- **Contracts:** path and symlink confinement is always enforced; writes reject
  directories and create parents only inside the workspace; execution accepts
  only regular `.py` files, uses the selected workspace as `cwd`, captures
  output, and retains the 30-second process timeout.

### CLI boundary

- **Purpose:** parse one run, resolve workspace and provider configuration,
  construct the provider client, and invoke the agent.
- **Callers:** console entry points, `python -m orbitrelay`, and CLI/profile tests.
- **Contracts:** existing positional syntax and provider-profile precedence stay
  compatible; dependency injection keeps tests offline; environment and dotenv
  trust boundaries remain unchanged.

## Dependents

- `src/orbitrelay/cli.py` calls `run_agent`.
- `src/orbitrelay/agent.py` calls `execute_tool` for every validated tool call.
- `src/orbitrelay/tools/__init__.py` owns all four built-in handler registrations.
- `src/orbitrelay/__main__.py` calls `cli.main`.
- `tests/test_agent.py` directly exercises batching, ordering, correlation,
  prevalidation, response limits, and final responses.
- `tests/test_tools.py` directly exercises dispatch, trusted-workspace injection,
  malformed arguments, and handler errors.
- `tests/test_sandbox.py` directly exercises write and execution confinement.
- `tests/test_cli.py` directly exercises CLI wiring and provider resolution.
- Profile, configuration, redaction, and package-smoke tests call `main` or import
  the same package boundary and are regression dependents.

## Affected stories

- **e02s01:** modifies write dispatch and agent feedback.
- **e02s02:** modifies execution dispatch and agent feedback.
- **e02s03:** adds run-scoped policy state shared across tool rounds.
- **e02s04:** adds read-only and unavailable-input behavior at CLI and dispatch.
- **e02s05:** adds explicit pre-approved behavior without bypassing validation.
- **e02s06:** adds secret-free decision records across every disposition.
- **e01s01:** provider-profile CLI wiring must remain unchanged.

## Existing test coverage

- `tests/test_agent.py::test_executes_multiple_calls_and_correlates_results`
  covers ordered multi-call execution and result IDs.
- `tests/test_agent.py::test_prevalidates_all_calls_before_executing_any` covers
  all-or-nothing structural validation before side effects.
- `tests/test_tools.py` covers fixed tool definitions, object-shaped arguments,
  trusted workspace injection, and dispatcher error conversion.
- `tests/test_sandbox.py` covers path/symlink confinement and direct write/process
  behavior.
- `tests/test_cli.py` covers run wiring, workspace selection, and provider-profile
  precedence.
- `tests/test_redaction.py` covers recursive credential-like key redaction.

## Coverage gaps to close

- No approval request or decision contract exists.
- No test proves that denied write or execution requests produce zero side
  effects.
- No policy exists for a mixed batch containing reads and consequential calls.
- No EOF, timeout, malformed-input, or noninteractive approval behavior exists.
- No run-scoped disabled-tool state exists across response rounds.
- Verbose dispatch currently prints raw non-workspace arguments, including file
  content or process arguments; P2 audit output must not inherit that exposure.
- No decision record is correlated with tool-call ID and disposition.

## Risk: High

This change introduces a security boundary into the shared execution path for
every tool call. Incorrect ordering can execute a side effect before consent,
break multi-call correlation, leak arguments, or deadlock unattended runs.

## Planning constraints

1. Parse and structurally validate a complete model tool-call batch before any
   approval prompt or execution.
2. Keep workspace/path/argument validation mandatory under every policy mode.
3. Inject one run-scoped approval dependency through CLI → agent → dispatcher;
   models cannot construct or change it.
4. Preserve exactly one correlated result per validated call, including denials.
5. Test side effects through fake handlers/processes and temporary workspaces.
6. Add no external package. Existing `openai`, `keyring`, and `python-dotenv`
   dependencies are `[OK]` and unaffected; P2 uses standard-library boundaries.

## Candidate depth

- **Approval session — Reason for Depth:** one narrow decision interface hides
  policy mode, trusted input, run-scoped disables, fail-closed outcomes, and
  secret-free decision recording without coupling the agent loop to terminal I/O.
- **Validated tool request — Reason for Depth:** one immutable request value
  normalizes the call ID, tool category, parsed arguments, trusted workspace, and
  safe preview so approval and execution consume the same validated action.

## Recommended action

Resolve the mixed-batch, timeout, pre-approval, and audit-visibility decisions;
then proceed with `plan-work`. Add approval-specific unit and integration tests
before changing production dispatch behavior.

## Resolved planning decisions

- Validate and authorize the complete tool-call batch before executing any call;
  afterward, execute approved calls in original order and return one result for
  every approved or denied call.
- Interactive confirmation defaults to a configurable 60-second timeout and
  denies on expiry.
- Pre-approved automation uses an explicit per-tool allowlist rather than a
  blanket all-tools switch.
- Secret-free decision events remain run-local and are emitted to stderr only
  when `--verbose` is selected.
