# OrbitRelay Architecture

OrbitRelay is a single-process, text-first personal assistant. Its current CLI
coordinates provider selection, model execution, optional workspace tools,
approvals, events, and session persistence.

Workspace tools support many local-information tasks, including project and
coding work, but they do not define the product boundary.

Future interaction surfaces may add voice, device actions, and user-authorized
service integrations without weakening the provider, approval, or local-state
boundaries below.

## Command boundary

`orbitrelay` runs a prompt in a workspace. It accepts one-run controls for the
provider, streaming, session, and approval policy. `orbitrelay provider` owns
connection lifecycle, while `orbitrelay session` owns local session lifecycle.

The public command surface is intentionally small. Use `--help` for exact
arguments rather than treating documentation examples as a compatibility API.

## Provider connections

`providers.py` is the provider catalog. It defines identifiers, endpoint and
model defaults, execution routes, and supported authentication methods.

`ConnectionService` resolves only the selected stored connection, or a one-run
`--provider` override. Runtime configuration never falls back to provider
environment variables or `.env` files.

API-key providers use the OpenAI-compatible execution route. Their secrets are
stored by the native credential service; `profiles.json` contains metadata only.
The hidden `provider connect` prompt is the only API-key entry path.

Codex is a separate route. OrbitRelay stores credential-free connection metadata
and calls the installed official Codex CLI. It never reads, writes, or reuses
Codex credentials.

## Agent execution

The agent loop converts model tool calls into constrained local operations. It
preserves assistant and tool messages as a consistent conversation history.

It emits correlated run events for model output, tool activity, approvals, usage,
errors, and completion.

Streaming and run summaries are presentation layers over that event stream. The
final answer remains on standard output; progress and structured diagnostics use
standard error.

## Workspace and approval boundary

Tools operate inside the selected workspace. The approval service evaluates all
consequential calls before execution, then runs approved calls in their original
order. Timeout, invalid input, EOF, and noninteractive cases deny by default.

Policies are `confirm`, `read-only`, and `pre-approved`. The last policy still
requires an exact tool allowlist. No policy infers blanket permission for writes
or execution.

## Local state

`ORBITRELAY_HOME` selects the per-user application directory. It contains
provider metadata and local session files; the native credential store contains
secrets. The directory must be user-owned and not group- or world-writable.

Sessions are local, resumable conversation records. They retain user data until
deleted and use restrictive permissions. They do not contain provider secrets.

## Documentation and records

The README is the operator guide. `docs/project-roadmap.md` is the current
product status and forward-looking roadmap. This file records durable design
boundaries.

`specs/state.yaml` is the active machine-readable project state. Completed plans,
release evidence, generated reports, and prior handoffs are historical records
under `specs/archive/`.

Local review, remediation, and manual-test records may also exist under `docs/`.
Those records are intentionally untracked and are not part of the public
documentation contract.
