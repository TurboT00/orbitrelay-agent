# OrbitRelay Post-0.5.0 Stabilization Implementation Plan

**Planned:** 2026-08-03  
**Baseline:** `main` at `ad2e556`  
**Scope:** `specs/product/SCOPE_LATEST.yaml`  
**Impact:** `specs/IMPACT_LATEST.md` — High  
**Stories:** 24  
**Tasks:** 72  
**BCP:** 151  
**Implementation status:** Wave 0 complete; e06s01/s02/s05 and e07s01 complete; 21 tasks passing and 51 tasks failing;
release identity 0.6.0 applied; next-story approval required before later work

## Purpose

This is the entry point for implementing the standalone stabilization release.
Detailed countable story specifications and failing task ledgers live in the
e05 through e10 epic capsules. Implement one story at a time with RED → GREEN →
REFACTOR, run the task's exact `verify:` command, and change a task from
`failing` to `passing` only after that command exits zero.

Do not begin P5/local-model work, publish, push, create a release, use live
credentials, or run a live provider probe unless the user separately authorizes
that operation.

## Pre-implementation gates

1. Preserve and approve the planning artifacts; do not reset unrelated or
   uncommitted user work.
2. Read `AGENTS.md`, README, architecture, roadmap, active state, scope, impact,
   this plan, and the selected story spec/task file.
3. Confirm the plan-consistency check has no CRITICAL or HIGH finding.
4. Start from a clean feature branch/worktree via `kickoff-branch`.
5. Implement only the selected story; stop at its human checkpoint.
6. Keep automated tests offline with injected clients, stores, clocks, runners,
   streams, processes, and temp directories.

## Zoom-out map

| Module/boundary | Purpose | Principal callers | Contracts to preserve |
| --- | --- | --- | --- |
| `cli.py` | Parse/dispatch every command and run | Both entry points and all command modules | Final answer on stdout; diagnostics/progress on stderr; lazy credentials; nonzero expected failures. |
| `agent.py` | Bounded model/tool loop | Top-level CLI | Validate full batches before effects; decide before ordered execution; preserve extension fields and correlated results. |
| `approvals.py` / tool preparation | Classify and authorize tool effects | Agent, CLI, terminal authorizer, tools | Reads automatic only when ordinary; writes/execution fail closed; preapproval never bypasses validation. |
| workspace tools/path safety | Confined filesystem and Python operations | Tool registry/agent | Workspace injection, traversal/symlink rejection, side-effect-free preparation, no privacy bypass. |
| provider/profile/credential services | Catalog, resolution, and secret-free metadata | Provider CLI and normal runs | One catalog; keyring-only secrets; stable profile names; atomic locked metadata; absent ≠ unavailable. |
| Codex bridge | Delegate to official CLI | Codex/provider CLI | Official CLI solely owns credentials; safe argv; bounded subprocess; no raw account output. |
| sessions/context | Persist and replay local conversation groups | CLI/session CLI/agent callbacks | Restrictive permissions; complete tool groups; extension fields; redaction; backward compatibility; one owner. |
| events/streaming/summaries | Observe live and persisted execution | Agent, CLI, sessions | Stable event/reason values; truthful phases; metadata not content; correct stream placement. |
| package/release checks | Identify, build, and qualify artifacts | Maintainers/release process | One identity; one lock; terminal gates; isolated wheel; evidence bound to revision. |

## Shared design contracts

Plan these once and reuse them across stories:

- **Privacy classification:** one content-free result for ordinary, sensitive,
  and absolute-deny paths, shared by direct reads and discovery.
- **CLI result presentation:** one expected-failure boundary with safe message,
  stable category, nonzero exit, and stdout/stderr contract.
- **Provider readiness:** independent facts plus only `local-ready`,
  `not-ready`, or `unknown`; historical verification is never current status.
- **Session transaction:** one kernel-backed lease and one versioned atomic
  checkpoint containing complete replay-safe messages/events/metadata.
- **Tool/process outcome:** typed status/truncation/timeout metadata consumed by
  tool results, events, summaries, and session checkpoints.
- **Release evidence:** revision-bound allowlisted metadata that distinguishes
  automated proof, waivers, independent review, and residual risk.

## D-01 protected-path catalog and precedence

The user approved the conservative catalog and authorized-scope discovery on
2026-08-03. Classification is path-based and occurs before protected file bytes
are loaded.

### Matching semantics

- Resolve and confine first, then convert the workspace-relative path to `/`
  separated components. Symlinks are rejected by the existing boundary before
  catalog evaluation.
- Compare component and basename rules with Unicode `casefold()` so filesystem
  case behavior cannot bypass policy. A directory-component rule applies to the
  directory and every descendant.
- `basename regex` below means a full-string regular-expression match against
  the case-folded final component. `suffix` means `basename.endswith(value)`.
  `component sequence` means exact consecutive case-folded path components.
- Absolute-deny evaluation precedes sensitive evaluation. A path matching both
  receives the absolute-deny classification.

### Absolute deny — no exception can override

| ID | Exact match rule |
| --- | --- |
| AP-01 | basename regex `^id_(rsa|dsa|ecdsa|ed25519)([._-].+)?$` |
| AP-02 | basename suffix in `.key`, `.p12`, `.pfx`, `.jks`, `.keystore`, `.kdbx`, `.keychain`, `.keychain-db` |
| AP-03 | basename exactly `.git-credentials`, `.netrc`, `.npmrc`, or `.pypirc` |
| AP-04 | path ends with component sequence `.aws/credentials`, `.docker/config.json`, `.kube/config`, or `.config/gcloud/application_default_credentials.json` |
| AP-05 | basename regex `^(.*[._-])?service[._-]?account([._-].*)?\.json$` |
| AP-06 | path contains component sequence `.gnupg/private-keys-v1.d` |

### Sensitive by built-in rule — exact one-process exception allowed

| ID | Exact match rule |
| --- | --- |
| SP-01 | basename is `.env` or starts with `.env.` |
| SP-02 | basename regex `(^|[._-])(secret|secrets|token|tokens|password|passwd|credential|credentials|apikey|api_key)($|[._-])` |
| SP-03 | basename suffix `.pem` |
| SP-04 | any component exactly `.git`, `.ssh`, `.gnupg`, `.aws`, `.azure`, `.kube`, `.docker`, or `.terraform` |
| SP-05 | path contains component sequence `.config/gcloud` |
| SP-06 | basename is `terraform.tfstate`, starts with `terraform.tfstate.`, ends with `.tfstate`, or contains `.tfstate.` |
| SP-07 | basename is `terraform.tfvars` or `terraform.tfvars.json`, or ends with `.auto.tfvars` or `.auto.tfvars.json` |
| SP-08 | path is ignored by the effective `.gitignore` rule set or matched by a deny-only `.orbitrelayignore` rule |

Ordinary project dotfiles such as `.gitignore`, `.editorconfig`,
`.python-version`, `.tool-versions`, and `.github/` are not sensitive solely
because they are hidden. Catalog changes are security-contract changes and
require focused tests and review.

### Precedence and authorized discovery

1. Workspace traversal and symlink confinement rejects first.
2. Absolute-deny built-ins always deny and remain omitted.
3. Sensitive built-ins deny unless covered by a pre-run exact-file or subtree
   exception.
4. Full Git ignore semantics, including last-match negation, determine only the
   Git-derived sensitivity layer; Git negation cannot override built-ins or
   `.orbitrelayignore`.
5. `.orbitrelayignore` is deny-only; negation syntax is rejected with a safe
   diagnostic and cannot create allow rules.
6. An authorized exact file becomes readable and discoverable as that one entry
   for the process. An authorized subtree makes non-absolute-deny entries inside
   the exact subtree readable and discoverable for the process. Absolute-deny
   entries remain omitted and unreadable.
7. Outside authorized scope, listings omit protected names and sizes and expose
   only an aggregate omitted count.

## Persistence and compatibility rules

- Keep profile names and credential-key namespaces stable. Extend secret-free
  profile metadata through the existing atomic, locked migration path.
- Read complete legacy sessions compatibly and upgrade only after a successful
  replay-safe checkpoint. Reject incomplete/unsafe forms before provider access.
- Keep full durable conversation/event history until explicit user deletion;
  use bounded segments and bounded complete-group replay memory rather than
  destructive automatic compaction or retention expiry.
- Separate durable conversation from system instructions and always inject the
  current version's safety instructions on resume.
- Never migrate or trim one member of an assistant tool-call/result group.
- Keep unknown provider assistant fields in retained and migrated history.
- Store sensitive history only after separate consent; mark it secret-free and
  require renewed exact authority before loading it on every resume.
- Make CLI output, exit codes, approval reasons, event values, and persisted
  schema changes explicit in tests and documentation.

## External package slopcheck

| Package | Tag | Planned use | Rationale |
| --- | --- | --- | --- |
| `pathspec` | `[OK]` | Git-compatible `.gitignore` matching for e06s02 | Mature, narrowly scoped implementation avoids an incomplete custom parser. |
| Ruff | `[OK]` | Lint gate | Mature, fast Python linter already used in project health checks. |
| mypy | `[OK]` | Static typing gate | Mature, scoped type checker with explicit project configuration. |
| coverage.py | `[OK]` | Branch coverage policy | Standard Python coverage implementation. |
| pip-audit | `[OK]` | Locked dependency vulnerability audit | PyPA-maintained, purpose-specific auditor. |
| Bandit | `[OK]` | Python source-security scan | Mature scoped scanner; findings remain reviewable rather than auto-fixed. |
| `uv` / Hatchling | `[OK]` | Existing lock, matrix, and build path | Existing project-standard tools; no replacement is proposed. |

No `[SUS]` or `[SLOP]` package is proposed. Session locking, durable replacement,
bounded subprocess handling, and atomic writes use the Python/macOS standard
library unless implementation evidence requires a new approved decision.

## Execution order

WSJF sets release priority, while this dependency order prevents shared-module
conflicts and circular migrations.

### Wave 0 — Establish the oracle and early gate

1. [e05s01 — Current finding disposition](epics/e05-baseline-release-identity/e05s01-current-finding-disposition.md)
2. [e09s01 — Terminal lint/type gates](epics/e09-quality-platform-qualification/e09s01-lint-type-gates.md)
3. [e05s02 — Reproducible release identity](epics/e05-baseline-release-identity/e05s02-release-identity.md)

**Pre-implementation evidence checkpoint:** review the rebaselined finding
dispositions and automated regression coverage. Automated checks are the release
gate; user-run side testing is optional, non-blocking, and not retained as release
evidence. Review the selected version rationale and early gate at the same
checkpoint.

### Wave 1 — Establish shared security, provider, and session foundations

4. [e06s01 — Block protected content](epics/e06-workspace-privacy-cli-trust/e06s01-block-protected-content.md)
5. [e06s02 — Private workspace discovery](epics/e06-workspace-privacy-cli-trust/e06s02-private-workspace-discovery.md)
6. [e06s05 — CLI failure streams](epics/e06-workspace-privacy-cli-trust/e06s05-cli-failure-streams.md)
7. [e07s01 — Offline provider readiness](epics/e07-provider-codex-lifecycle/e07s01-offline-provider-readiness.md)
8. [e07s03 — Delegated Codex readiness](epics/e07-provider-codex-lifecycle/e07s03-codex-readiness.md)
9. [e08s01 — Exclusive session owner](epics/e08-session-execution-integrity/e08s01-exclusive-session-owner.md)
10. [e08s02 — Replay-safe checkpoints](epics/e08-session-execution-integrity/e08s02-replay-safe-checkpoints.md)

**Checkpoint:** review the shared privacy/readiness/session interfaces and their
migration tests before dependent CLI/session behavior.

### Wave 2 — Complete lifecycle and execution integrity

11. [e06s03 — One-run sensitive-read exception](epics/e06-workspace-privacy-cli-trust/e06s03-one-run-read-exception.md)
12. [e06s04 — Sensitive-session resume](epics/e06-workspace-privacy-cli-trust/e06s04-sensitive-session-resume.md)
13. [e07s02 — Explicit provider verification](epics/e07-provider-codex-lifecycle/e07s02-explicit-provider-verification.md)
14. [e07s04 — Codex disconnect ownership](epics/e07-provider-codex-lifecycle/e07s04-codex-disconnect-ownership.md)
15. [e08s03 — Corrupt session lifecycle](epics/e08-session-execution-integrity/e08s03-corrupt-session-lifecycle.md)
16. [e08s04 — Bounded session history](epics/e08-session-execution-integrity/e08s04-bounded-session-history.md)
17. [e08s05 — Bounded process output](epics/e08-session-execution-integrity/e08s05-bounded-process-output.md)
18. [e08s06 — Crash-safe truthful tool outcomes](epics/e08-session-execution-integrity/e08s06-crash-safe-tool-outcomes.md)

**Checkpoint:** run all focused and full offline tests; review migrations,
partial-result contracts, CLI streams, event values, and affected-path security.

### Wave 3 — Qualify the release contract

19. [e09s02 — Risk-based quality policy](epics/e09-quality-platform-qualification/e09s02-risk-quality-policy.md)
20. [e09s03 — macOS Python 3.12–3.14 matrix](epics/e09-quality-platform-qualification/e09s03-macos-python-matrix.md)
21. [e09s04 — Truthful platform claims](epics/e09-quality-platform-qualification/e09s04-platform-support-claims.md)

**Checkpoint:** every declared minor and terminal quality stage must pass before
support metadata or release claims are accepted.

### Wave 4 — Evidence, audit, and candidate

22. [e10s01 — Automated macOS evidence](epics/e10-release-evidence-readiness/e10s01-automated-macos-evidence.md)
23. [e10s02 — Candidate re-audit](epics/e10-release-evidence-readiness/e10s02-candidate-reaudit.md)
24. [e10s03 — Standalone release candidate](epics/e10-release-evidence-readiness/e10s03-standalone-release-candidate.md)

**Checkpoint:** explicit release-owner approval is still required after the
candidate passes; candidate production is not publish authorization.

## Verification policy

- Run the narrow task `verify:` while iterating.
- Run `uv run python -m unittest discover -s tests -v` and
  `uv run python examples/calculator/tests.py` before each story handoff when
  shared behavior changed.
- Run `./scripts/check.sh` at wave checkpoints and whenever a task names it.
- After e09s03 exists, run `./scripts/check-python-matrix.sh` where required.
- Qualify the lower floor first with
  `./scripts/check-python-matrix.sh --candidate-floor 3.12 --automated-only` in
  its disposable candidate checkout; do not change tracked metadata early.
- Keep release gates fully automated and credential-free. Optional user-run side
  testing does not block stories and is not consumed by the release verdict.
- Candidate re-audit must validate the separate evidence record with
  `--require-review` so independent code/security review is executable evidence,
  not narrative only.
- Keep every task ledger `failing` until its own command succeeds. A passing
  neighboring or full-suite command does not automatically flip it.

## First implementation target

**Wave 0 plus e06s01/s02/s05 and e07s01 are complete.** The disposition oracle
remains at `specs/verifications/current-finding-disposition.json`, records
selected identity **0.6.0**, and marks MAJ-01, MAJ-04, and MED-10 fixed. Do not
proceed to e07s03 or later stories until the next story is explicitly approved.

## Handoff

Next action: hold the next-story checkpoint. Recommended Wave 1 next story is
e07s03 (delegated Codex readiness). Obtain explicit story approval before
beginning e07s03 or any later stabilization work.
