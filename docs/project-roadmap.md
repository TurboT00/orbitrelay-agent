# OrbitRelay Project Roadmap

**Last reviewed:** 2026-07-22

**Status:** Direction approved; milestones require story-level scoping before implementation.

## Reason for existence

This roadmap gives future agents one dependency-aware path from OrbitRelay's
working CLI foundation to a trustworthy multi-provider coding agent. It records
provider constraints so future work does not invent unsupported OAuth flows,
collect provider passwords, or mistake protocol compatibility for capability
compatibility.

## Product direction

OrbitRelay will become a user-controlled coding agent that can route work to:

1. hosted OpenAI-compatible APIs;
2. the official Codex CLI using Codex-managed ChatGPT sign-in;
3. xAI through user-supplied API keys; and
4. qualified local model servers such as Ollama and vLLM.

OrbitRelay will never collect provider passwords, copy first-party refresh
tokens, parse Codex's `auth.json`, or emulate undocumented provider OAuth flows.

## Current baseline

Version `0.3.0` provides:

- an installable `orbitrelay` CLI and `python -m orbitrelay` entry point;
- configurable OpenAI-compatible base URL, model, and API key;
- named provider profiles with native OS credential storage (P1);
- a bounded eight-response tool loop with call correlation;
- file read/list/write and Python execution tools;
- workspace path and symlink confinement;
- batch-first tool approval for writes and Python execution (P2);
- `confirm`, `read-only`, and exact per-tool `pre-approved` policies;
- run-scoped tool disable and secret-free verbose approval audit events;
- 145 offline project tests and 9 calculator example tests; and
- `scripts/check.sh` for repeatable local verification.

Current limitations:

- only `api_key` profiles are executable; delegated auth adapters remain roadmap work;
- no persistent conversations, streaming, capability probing, or plugins;
- no certified local-model configuration; and
- Bash-only developer verification on macOS/Linux. Windows profile locking remains P7.

## Provider evidence and constraints

| Candidate | Primary evidence | Verdict | Roadmap rule |
|---|---|---|---|
| Codex CLI | [Authentication](https://developers.openai.com/codex/auth/), [noninteractive use](https://developers.openai.com/codex/noninteractive/) | Adopt official CLI boundary | Codex owns login, refresh, storage, and logout. OrbitRelay may invoke documented commands only. |
| OpenAI/Codex SDK | [Codex SDK](https://developers.openai.com/codex/sdk/), [API authentication](https://platform.openai.com/docs/api-reference/authentication) | API key only | Do not describe SDK API-key access as ChatGPT OAuth. |
| xAI/Grok | [xAI API authentication](https://docs.x.ai/docs/api-reference#authentication) | BYOK; monitor | No public third-party Grok OAuth contract is documented. Never reuse browser sessions or cookies. |
| Ollama | [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility), [authentication](https://docs.ollama.com/api/authentication), [tool calling](https://docs.ollama.com/capabilities/tool-calling) | Compose after capability checks | Local loopback is unauthenticated. Placeholder API keys provide no security. |
| vLLM | [OpenAI-compatible server](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html), [tool calling](https://docs.vllm.ai/en/latest/features/tool_calling.html) | Compose after capability checks | Tool behavior depends on model, template, parser, and server flags. A static API key is not OAuth. |

**Research verdict:** adopt documented provider clients and process boundaries;
build only OrbitRelay-specific profiles, capability checks, policies, and user
experience.

## Delivery order

| Priority | Target | Outcome | Depends on |
|---|---|---|---|
| P0 | Foundation handoff | Repeatable local checks and durable project state | Complete |
| P1 | Provider and auth profiles | Explicit endpoint/auth contracts without secret leakage | P0 |
| P2 | Tool approval policies | Users control writes and process execution | Complete |
| P3 | Codex CLI bridge and xAI BYOK | Supported account/API paths without invented OAuth | P1, P2 |
| P4 | Conversations and streaming | Resumable sessions and observable progress | P2 |
| P5 | Qualified local models | Ollama loopback, then configured vLLM | P1, P2, P4 |
| P6 | Tool extension model | Safe third-party tool registration and policy enforcement | P2, P4 |
| P7 | Cross-platform support | macOS, Arch, Ubuntu, and Windows 11 | Stable P1-P6 interfaces |

## P1 — Provider and auth profiles

**Objective:** replace implicit environment-only configuration with named,
testable connection profiles while preserving current environment variables.

Required contracts:

- Auth kinds: `api_key`, `external_first_party_cli`, `local_none`, and
  `local_service_bearer`.
- OAuth may be added only when a provider publishes client registration,
  scopes, redirects, refresh, and revocation contracts for third parties.
- Secrets never live in repository configuration or command arguments.
- Profile output and logs redact credentials recursively.
- Existing `OPENAI_*` variables remain a migration-compatible default profile.
- Providers declare capabilities instead of inheriting them from a `/v1` URL.

Acceptance criteria:

- users can list, inspect, select, and delete named profiles;
- configuration validation fails before network access;
- tests cover every auth kind without real credentials;
- profile serialization contains no secret values; and
- credential-store choice is approved before implementation.

Non-goals: ChatGPT/Grok password collection, undocumented OAuth, and automatic
LAN exposure of local servers.

## P2 — Tool approval policies

**Status:** complete in `0.3.0`.

**Objective:** make user consent the default boundary for consequential tools.

Delivered policy:

- reads: allow within the selected workspace;
- writes: prompt by default and display the target path and content length;
- execution: prompt by default with interpreter, workspace, target, and escaped args;
- deny/disable: deny-once or disable a tool for the rest of the run;
- automation: `--approval-policy read-only|confirm|pre-approved` with exact
  `--approve-tool` allowlists; and
- audit: verbose stderr events with allowlisted metadata only.

Acceptance criteria met:

- denied calls return structured tool failures to the model;
- no write or process starts before approval;
- noninteractive, EOF, timeout, and invalid input fail closed;
- approvals are auditable without logging tool-result secrets; and
- offline tests cover approve, deny, disable, EOF, timeout, read-only,
  pre-approved, and confinement behavior.

## P3 — Supported hosted access

### Codex CLI bridge

- Detect a separately installed official `codex` executable.
- Delegate interactive login and logout to documented Codex commands.
- Invoke the documented noninteractive `codex exec` boundary.
- Never read or copy `CODEX_HOME/auth.json`.
- Report Codex availability and version separately from model API profiles.
- Confirm OpenAI product/licensing expectations before promising
  subscription-backed automation at scale.

### xAI/Grok BYOK

- Add an xAI profile preset using `XAI_API_KEY` or a secure credential entry.
- Keep generic OpenAI-compatible configuration available.
- Monitor official xAI documentation for a real third-party OAuth program.
- Do not block xAI API-key use while OAuth remains unavailable.

## P4 — Conversations and streaming

Implement one event model before adding both features. It must represent model
output, tool requests, approval decisions, tool results, usage, errors, and run
completion.

Then add:

- token and tool-progress streaming;
- local resumable sessions with explicit retention and deletion;
- context-window budgeting that preserves complete tool-call/result pairs; and
- structured run summaries suitable for terminal output and later telemetry.

Session content is user data. Storage location, encryption expectations, and
retention defaults require approval before implementation.

## P5 — Qualified local models

Start with **Ollama on loopback only**. Require a capability probe and a
documented tool-capable model. A dummy OpenAI client key must be labeled as
ignored by Ollama, not presented as authentication.

Add vLLM only after profiles can capture:

- server version and model identifier;
- chat template and tool-call parser;
- automatic, named, required, and parallel tool support; and
- bearer-key and TLS/gateway expectations.

LAN or remote local-model access is out of scope until authenticated TLS proxy
guidance and tests exist.

## P6 — Tool extension model

Define a typed tool contract, schema validation, policy category, timeout,
result-size limit, and redaction behavior before loading external tools.
Plugins must not receive provider credentials or bypass the workspace and
approval policies.

## P7 — Cross-platform support

Certify platforms only when the complete check passes natively:

- macOS;
- Arch Linux;
- Ubuntu LTS; and
- Windows 11 PowerShell.

Add `scripts/check.ps1` before declaring native Windows support. Add CI when
multiple development machines or contributors make independent clean-run
verification valuable; GitHub Actions is not a prerequisite for earlier work.

## Deferred decisions

The implementing agent must ask before deciding:

1. OS keychain versus another credential-store contract.
2. Codex CLI bridge packaging, minimum version, and subscription-use terms.
3. Session storage format, encryption, and retention defaults.
4. Certified Ollama model list and minimum Ollama version.
5. Whether vLLM support is loopback/private-network only or includes remote
   deployments.
6. Plugin discovery and trust model.
7. Supported Python versions beyond the current Python 3.14 requirement.

## Next implementation step

Scope P1 as a vertical slice before writing code:

1. define one hosted API-key profile and one `local_none` profile;
2. preserve the current environment-based path;
3. design credential references without choosing storage implicitly;
4. define a provider capability manifest; and
5. verify with offline contract tests.

**Verify this roadmap:**

```bash
grep -q "^## P1 — Provider and auth profiles" docs/project-roadmap.md
grep -q "Never read or copy.*auth.json" docs/project-roadmap.md
./scripts/check.sh
```
