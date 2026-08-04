# AGENTS.md

This file is the working guide for agents changing OrbitRelay. It summarizes
the current codebase, but source and tests remain authoritative.

## Start here

1. Inspect `git status --short` before editing. Preserve unrelated user changes
   and do not clean or reset them.
2. Read `README.md`, `docs/architecture.md`, `docs/project-roadmap.md`, and
   `specs/state.yaml` before changing product behavior.
3. For security, provider, persistence, or roadmap work, also read any local
   review and remediation records present under `docs/`. These files are
   intentionally untracked and may not exist in a public checkout.
4. Treat `specs/state.yaml` as the active machine-readable project state.
   Material under `specs/archive/` is historical evidence, not current
   implementation instructions.

## Project at a glance

OrbitRelay is currently a Python 3.14+ general-purpose, text-first personal
assistant for hosted, OpenAI-compatible providers. Python 3.12 through 3.14 is
the approved stabilization target, but package metadata must not change until
the macOS matrix passes. macOS is qualified; Linux is preview/unverified and
Windows remains deferred. Its current interface is a CLI with optional workspace
file and Python tools. Coding is one supported use case, not the product boundary.

OrbitRelay also exposes a separate bridge to the official Codex CLI. The
package is under `src/orbitrelay`, uses a `src` layout, is built with Hatchling,
and is managed with `uv` plus the committed `uv.lock`.

The latest tagged and declared release is 0.5.0. `main` contains post-release
provider-connection and maintenance work, but no next release is selected.

P5/local-model work is not approved. D-01 through D-05 are approved as the
stabilization decision baseline. `specs/product/SCOPE_LATEST.yaml` is the active
standalone stabilization boundary. `specs/release-plan.yaml` and the e05 through
e10 capsules contain 24 sliced stories. `specs/IMPACT_LATEST.md` records a High
cross-epic blast radius. `specs/IMPLEMENTATION_PLAN_LATEST.md` contains 24
detailed story plans and 72 task-ledger entries. e05s01 is complete; automated
verification and explicit approval of each next story remain prerequisites to
broad implementation.

The long-term direction is a Siri-like personal assistant with possible voice,
device-action, and personal-service integrations. None is implemented today.

Do not add or advertise those capabilities without explicit scope, privacy,
consent, authentication, retention, and platform decisions.

## Runtime map

- `src/orbitrelay/__main__.py` and the `orbitrelay` script both enter
  `orbitrelay.cli:main`.
- `cli.py` dispatches `provider`, `codex`, and `session` subcommands; otherwise
  it resolves a connection and starts an agent run.
- `providers.py` is the single provider catalog: identifiers, endpoint/model
  defaults, execution routes, and auth availability.
- `connection_service.py` is the resolution boundary between stored profile
  metadata, the credential store, and an executable provider connection.
- `profiles.py`, `profile_store.py`, and `credentials.py` define and persist
  secret-free profile metadata while API keys remain in the native keyring.
- `agent.py` owns the bounded model/tool loop. It validates complete tool-call
  batches, prepares every call, obtains approval, executes approved calls in
  order, and appends correlated tool results.
- `tools/` contains the four model tools and the workspace path boundary:
  `get_files_info`, `get_file_content`, `run_python_file`, and `write_file`.
- `approvals.py` contains policy and audit state; `terminal_authorizer.py`
  handles interactive confirmation.
- `events.py` is the shared event model. `streaming.py`, `run_summary.py`, and
  session event persistence consume it.
- `sessions.py` stores resumable local history; `context_budget.py` trims only
  outbound history while preserving assistant tool-call/result groups.
- `codex_bridge.py` is a separate execution boundary around the installed
  official `codex` binary. It must not inspect or reuse Codex credentials.

Typical hosted-provider flow:

```text
CLI -> ConnectionService -> OpenAI client -> agent loop
    -> prepare/validate full tool batch -> ApprovalSession
    -> execute allowed workspace tools -> tool results -> next model response
```

Codex subscription execution does not enter that loop:

```text
CLI -> CodexBridge -> official `codex` CLI
```

## Non-negotiable boundaries

- Never write provider secrets to `profiles.json`, sessions, events, summaries,
  logs, exceptions, fixtures, screenshots, or documentation.
- Normal agent runs resolve exactly one stored connection. They do not read API
  keys, endpoints, or models from the process environment or `.env`. API keys
  enter only through the hidden `provider connect` prompt and go directly to
  the native credential store.
- Codex authentication belongs entirely to the official CLI. OrbitRelay stores
  only credential-free connection metadata and delegates login/logout/exec.
- Tool paths are fixed to the selected workspace. Reject absolute escapes,
  traversal, and symlink escapes; the model must never supply or override the
  injected workspace.
- Validate and prepare an entire tool-call batch before any side effect. Obtain
  decisions for the batch before executing approved calls in original order.
- Reads are currently allowed automatically. Writes and local Python execution
  must fail closed unless interactively confirmed or exactly pre-approved.
  Timeout, EOF, invalid input, and noninteractive confirmation deny authority.
- Pre-approval never bypasses argument, path, workspace, or symlink validation.
- Keep assistant tool calls paired with all of their tool results in replay,
  persistence, and context trimming. Do not orphan or reorder correlated IDs.
- Provider assistant messages may contain required extension fields. Preserve
  unknown fields across a tool round instead of rebuilding a narrow message.
- Per-user state must reject symlinks, wrong ownership, and group/world-writable
  paths. Profile metadata writes are atomic and cross-process locked; do not
  weaken these properties when changing storage.
- Final answers are intended for stdout; prompts, progress, usage, summaries,
  and errors belong on stderr. Regression tests cover both normal and tool-call
  CLI flows; continue testing the actual streams when touching presentation.

## Editing guide

- Add or change a provider in `providers.py`, then cover the catalog,
  connection resolution, provider CLI, and top-level CLI behavior. Do not add
  provider-specific lists or credential logic in command handlers.
- Keep profile names stable during metadata migrations because the credential
  key derives from the profile path namespace and name.
- Adding a tool requires coordinated updates to `FUNCTIONS`, `TOOL_CATEGORIES`,
  `TOOL_DEFINITIONS`, preparation/approval mapping, path validation, and tests.
  Tool preparation must remain side-effect-free.
- Event changes can affect live streaming, persisted `events.jsonl`, summaries,
  and redaction. Emit metadata rather than raw tool content or arguments.
- Session changes must consider file modes, symlinks, corrupt JSONL, concurrent
  processes, redaction, backward compatibility, and tool-pair integrity.
- Approval reason strings and event type values are observable contracts. Change
  them deliberately and update tests and documentation together.
- Use injected clients, credential stores, clocks, runners, streams, and temp
  directories in tests. Automated tests must remain offline and must never use
  a real provider, keyring entry, home directory, or Codex login.
- Keep operator behavior in `README.md`, durable boundaries in
  `docs/architecture.md`, roadmap status in `docs/project-roadmap.md`, and only
  active machine state in `specs/state.yaml`.

## Verification

Use the narrowest useful test while iterating:

```bash
uv run python -m unittest tests.test_agent -v
uv run python -m unittest tests.test_connection_service -v
```

Run the complete offline project suite before handoff:

```bash
uv run python -m unittest discover -s tests -v
uv run python examples/calculator/tests.py
```

The release-oriented local check is:

```bash
./scripts/check.sh
```

It checks the lockfile, runs `uv sync --locked`, executes both test suites,
smoke-tests imports and both CLI entry points, builds distributions, and runs
the command from an isolated wheel. It requires Bash and `uv` and may need
network/cache access on a clean machine.

`scripts/check.sh` is not currently a complete quality gate: it does not run
Ruff, mypy, coverage, dependency auditing, or security scanning. Do not describe
it as proving those checks. The current project suite contains 188 tests and the
calculator example contains 9 tests.

## Known baseline and scope controls

The local July 2026 project review originally recorded eight major concerns:
sensitive workspace reads can reach hosted models without confirmation;
streaming loses provider-required assistant fields; stdout is contaminated;
expected CLI errors can escape as tracebacks; metadata-only/Codex operations
eagerly require keyring; failed Codex login can leave selected metadata; the
provider refactor lacks a clean release baseline; and the official check omits
failing quality gates. It is a dated baseline, not a current verdict.

The 2026-08-02 health pass added regression-tested fixes for streamed provider
field replay, CLI stdout separation, lazy keyring initialization, failed Codex
login mutation, and plain-text tool-error status. It also made streamed tool
argument assembly linear, reduced session-load peak memory, cleared the
recorded Ruff/mypy findings, and updated the vulnerable `idna` lock. Re-run the
checks rather than assuming every finding in the earlier review is still open.
The provider refactor is now committed on `main`, but a post-0.5.0 release
baseline has not been tagged.

The local stabilization remediation plan contains the user-approved D-01
through D-05 planning baseline. It is not blanket implementation authority. Do
not silently implement it, begin P5, broaden provider/auth/platform claims, or
run unapproved live operations. e05s01 is complete; preserve the plan, impact
report, scope, and decisions, and request explicit direction before changing
their trade-offs or beginning another story.

Do not push, publish, create releases, use live credentials, or run paid/live
provider tests unless the user explicitly asks. Automated tests are the release
gate. User-run side testing is optional and must not block implementation or be
treated as retained release evidence.
