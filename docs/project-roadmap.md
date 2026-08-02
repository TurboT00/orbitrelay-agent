# OrbitRelay Product Status and Roadmap

**Last reviewed:** 2026-08-02
**Latest tagged release:** 0.5.0
**Development status:** post-0.5.0 sustain work; no next release selected

## Current baseline

OrbitRelay is a general-purpose, text-first personal assistant for macOS and
Linux.

Its current interface is a CLI with stored hosted-provider connections,
workspace-confined tools, explicit approval controls, streaming output, and
resumable local sessions.

The project is on `main`. Releases 0.3.0 through 0.5.0 are complete. The source
tree contains post-release provider-connection and maintenance work but still
declares package version 0.5.0 until a new release is approved.

Use the [architecture guide](architecture.md) for implementation boundaries and
the [README](../README.md) for installation and operation.

An internal readiness review found no confirmed critical issue but identified
major concerns that still block P5. Remediation planning and required manual
evidence remain under private review and are not approved for execution.

## Completed capabilities

| Release | Capability | Status |
| --- | --- | --- |
| 0.3.0 | Workspace tool approvals | Complete |
| 0.4.0 | Hosted provider access and Codex CLI bridge | Complete |
| 0.5.0 | Events, streaming, sessions, and context budgeting | Complete |

### Provider connections

One selected stored connection supplies each agent run. Offline-tested API-key
routes are implemented for OpenAI, Gemini, Grok, and DeepSeek. Live conformance
remains subject to private manual evidence.

Codex delegates subscription sign-in and execution to the installed official
Codex CLI.

Environment values and `.env` files are import-only migration inputs. Secrets
stay in the native credential store; connection metadata is secret-free.

## Product direction

OrbitRelay is intended to grow beyond terminal-only interaction toward a
Siri-like personal assistant.

Long-term candidates include conversational voice input and output,
user-authorized device actions, and integrations with personal services.

None of those capabilities is present today. Each requires explicit privacy,
consent, authentication, data-retention, failure, and platform boundaries before
implementation or support claims.

### Tool safety

Workspace reads are allowed. Writes and process execution require explicit
approval unless a restrictive or exact allowlist policy is selected. Approval
records are run-local and verbose events omit secrets.

### Conversation continuity

Runs may stream model and tool progress, create or resume local sessions, and
budget history without separating a tool call from its result. Session files are
per-user data and use restrictive filesystem permissions.

## Next: qualified local models

P5 evaluates a limited local-model path, beginning with Ollama on loopback.
Work begins only after a supported model and tool-calling contract are selected.

The qualification must demonstrate reliable tool calling, assistant-message
replay, approval compatibility, bounded context behavior, and offline tests.
No local provider is currently supported or advertised.

## Later candidates

### Tool extensions

P6 may introduce a constrained extension model after local execution and
approval semantics are proven stable. Extensions must retain workspace and
approval boundaries by default.

### Windows support

P7 may add a native Windows development and verification path. Until then,
macOS and Linux are the supported platforms; Windows users may use WSL or Git
Bash for the current Bash verification script.

### Personal interaction and integrations

Future planning may explore voice interaction, device-level actions, and
personal-service connectors. These capabilities must be independently scoped
and must preserve fail-closed authorization for consequential actions.

## Deferred decisions

- Gemini OAuth remains unavailable until its documented integration probe
  succeeds.
- Grok and DeepSeek remain API-key-only until supported third-party subscription
  contracts exist.
- Session encryption and automatic retention are not planned in the current
  baseline.
- Publishing, remote pushes, and new product scope require explicit direction.

## Planning a new capability

Start with `survey-context`, then define scope before implementation. The active
machine-readable project state is `specs/state.yaml`; completed plans and
release evidence are retained under `specs/archive/`.
