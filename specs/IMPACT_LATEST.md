# OrbitRelay Stabilization Impact Assessment

**Assessed:** 2026-08-03  
**Baseline:** `main` at `ad2e556`  
**Scope:** `specs/product/SCOPE_LATEST.yaml`  
**Release index:** `specs/release-plan.yaml`  
**Stories:** e05s01 through e10s03 (24 stories, 151 BCP)  
**Assessment mode:** full dependents, story, coverage, migration, and sequencing analysis

## Executive assessment

The stabilization initiative has a **High** blast radius. It deliberately
changes security, CLI, persistence, provider, package, and release contracts
that are shared across the current product. The scope can proceed to detailed
planning, but implementation must not be treated as six isolated epics: several
stories converge on `cli.py`, `agent.py`, `sessions.py`, `tools/__init__.py`,
profile storage, events, package metadata, and `scripts/check.sh`.

The strongest current coverage is around provider/profile storage and the agent
approval loop. The weakest coverage is exactly where new behavior is proposed:
workspace privacy classification, top-level CLI error translation,
multi-process session ownership, crash-safe checkpoints, verification-history
metadata, quality-gate failure behavior, and Python-minor compatibility.

Proceed to `plan-work`, subject to the sequencing and test-first conditions in
this report. The prior D-01 through D-05 `grill-me` workshop resolves the product
trade-offs; reopen it only if detailed planning changes those decisions.

## Target

The target is the complete standalone post-0.5.0 stabilization change set:

- **e05:** establish a current finding baseline and reproducible release identity;
- **e06:** enforce workspace-read privacy and trustworthy CLI failures;
- **e07:** make API-provider and Codex lifecycle status truthful;
- **e08:** make sessions and local execution transactional, bounded, and diagnosable;
- **e09:** make quality and macOS Python compatibility release gates; and
- **e10:** collect evidence, re-audit, and produce the standalone candidate.

## Dependents (47 current code and test modules, plus packaging and records)

The repository contains 30 production modules and 17 current test modules. Not
every file must change, but every cluster below can be affected directly or by
an observable-contract regression.

### Shared orchestration and CLI

| Target | Current direct dependents | Existing direct coverage | Impact |
| --- | --- | --- | --- |
| `src/orbitrelay/cli.py` | `__main__.py`; provider, Codex, session, and normal-run dispatch | No dedicated direct-import test module; behavior is distributed across connection, session, streaming, and summary tests | New flags, version output, lock lifetime, sensitive-session behavior, and error translation can change every entry path. |
| `src/orbitrelay/agent.py` | `cli.py` | Six test modules | Privacy enforcement and replay checkpoints must preserve complete-batch validation, approval order, provider extension fields, and tool-result correlation. |
| `src/orbitrelay/approvals.py` | terminal authorizer, CLI, agent, tool preparation | Six test modules | Read policy changes must not grant authority through pre-approval or change stable reason strings accidentally. |
| `src/orbitrelay/terminal_authorizer.py` | approvals and CLI | No direct test module | Error/EOF/timeout behavior is security-sensitive and currently covered only indirectly. |
| `src/orbitrelay/events.py` | sessions, summaries, CLI, agent, streaming | Four test modules | New privacy, denial, truncation, and partial-operation states are observable event contracts. |
| `src/orbitrelay/run_summary.py` | CLI | One test module | Failed, denied, truncated, partial, and sensitive outcomes must remain truthful and secret-free. |

### Workspace tools and privacy boundary

| Target | Current direct dependents | Existing direct coverage | Impact |
| --- | --- | --- | --- |
| `tools/__init__.py` | Agent tool preparation/execution boundary | Covered through agent/tools behavior, but no direct import identified by the file-level scan | D-01 must be enforced during preparation without introducing side effects or weakening full-batch validation. |
| `tools/get_file_content.py` | Tool registry | Sandbox tests | Direct reads become policy-aware and can fail before filesystem content is loaded. |
| `tools/get_files_info.py` | Tool registry | Sandbox tests | Directory results must hide protected names and sizes while preserving ordinary discovery. |
| `tools/path_safety.py` | All four workspace tools | No direct test module | Four source callers share this small module; privacy and ignore rules must not weaken traversal or symlink confinement. |
| `tools/write_file.py` | Tool registry | Sandbox tests | e08 adds crash safety and closes the validation-to-use race while preserving approval behavior. |
| `tools/run_python_file.py` | Tool registry | Sandbox tests | Output bounds and timeout behavior can change tool results, events, and summaries. |

### Provider, profile, credential, and Codex boundary

| Target | Fan-in / direct tests | Impact |
| --- | --- | --- |
| `connection_service.py` | 2 source callers / 6 test modules | Shared resolution boundary; readiness inspection must not alter normal execution or initialize credentials unnecessarily. |
| `credentials.py` | 3 source callers / 7 test modules | Three-state availability must distinguish absent from unavailable without exposing values or weakening failure cleanup. |
| `profile_store.py` | 4 source callers / 8 test modules | Verification history changes secret-free metadata and must preserve atomic locking, ownership checks, names, and credential-key namespaces. |
| `profiles.py` | 3 source callers / 3 test modules | Any schema extension requires backward-compatible validation and migration. |
| `providers.py` | 2 source callers / 7 test modules | Status and verification must continue to derive capabilities from one catalog. |
| `provider_cli.py` | CLI / 1 direct test module | Existing output says “Connected”; structured status and verification are observable CLI changes. |
| `codex_cli.py` | CLI and provider CLI / 1 direct test module | New normalized status and `logout --disconnect` affect argument parsing, exit codes, and partial-result reporting. |
| `codex_bridge.py` | Codex CLI / 1 direct test module | Output capture, status normalization, and limits must preserve the official credential boundary and existing safe argv rules. |

### Sessions, replay, and local state

| Target | Fan-in / direct tests | Impact |
| --- | --- | --- |
| `sessions.py` | session CLI and top-level CLI / 1 test module | Exclusive ownership, schema markers, atomic checkpoints, corruption visibility, deletion, history bounds, and sensitive-session state converge here. |
| `session_cli.py` | top-level CLI / session tests | Active/corrupt status and locked deletion change user-visible lifecycle behavior and exit codes. |
| `context_budget.py` | agent / 1 test module | Storage/history bounds must preserve assistant tool-call/result groups and provider extension fields. |
| `streaming.py` | agent / 1 test module | Privacy and bounded-output changes must not regress extension-field replay or stdout/stderr separation. |
| `redaction.py` | sessions, events, summaries / 2 test modules | New metadata and diagnostics increase the number of values requiring recursive redaction, but redaction must not be mistaken for the D-01 access-control boundary. |

### Packaging, quality, and records

- `pyproject.toml`, `uv.lock`, `src/orbitrelay/__init__.py`, both entry points,
  `scripts/check.sh`, and the planned Python-matrix script must agree on version,
  dependencies, Python floor, and installed behavior.
- README, architecture, roadmap, `AGENTS.md`, `specs/state.yaml`, release plan,
  epic capsules, local manual evidence, and the release audit must describe the
  same shipped contract.
- The official check currently runs tests, examples, import/CLI smoke, build, and
  isolated-wheel smoke. Ruff, mypy, coverage, dependency audit, and security scan
  are not yet reproducible project gates.

## Affected stories

### e05 — Baseline and Release Identity — Risk: High

- **e05s01** owns the evidence oracle used by every later acceptance decision.
  It depends on current source, tests, lock data, local review evidence, and the
  official check. A false “fixed” disposition can invalidate the whole release.
- **e05s02** affects package metadata, entry points, installed-wheel behavior,
  roadmap/state records, and e09/e10 release checks.
- **Cross-epic impact:** e05s01 gates planning detail for all stories; e05s02 is
  consumed by e09s03, e09s04, and e10s03.

### e06 — Workspace Privacy and CLI Trust — Risk: High

- **e06s01** affects tool preparation, direct reads, agent batches, approvals,
  events, summaries, and session persistence.
- **e06s02** affects both read tools and the shared path boundary. Ignore-rule
  parsing must have deterministic precedence and must not create filesystem side
  effects during full-batch preparation.
- **e06s03** affects top-level parsing, authorization injection, tool validation,
  and session-update callbacks. Process lifetime must be explicit in tests.
- **e06s04** affects session metadata/messages, resume gating, context replay,
  and redaction. It depends on e08s01 and e08s02 transaction semantics.
- **e06s05** affects every top-level error route and both output streams.
- **Cross-epic impact:** e06 shares `cli.py`, `agent.py`, `sessions.py`, events,
  summaries, and context replay with e08; those contracts must be planned once.

### e07 — Provider and Codex Lifecycle — Risk: High

- **e07s01** changes provider CLI output and credential-store access timing while
  depending on the provider catalog, profile repository, and connection service.
- **e07s02** extends profile metadata with historical verification evidence and
  adds an explicitly network-capable command that must remain fakeable offline.
- **e07s03** changes Codex status from raw CLI-oriented behavior to normalized
  provider readiness without exposing account output.
- **e07s04** spans two ownership domains that cannot be fully transactional;
  tests must cover every partial outcome and selection state.
- **Cross-epic impact:** profile schema/version handling must be established
  before e07s02; e07 CLI errors must use the e06s05 presentation contract.

### e08 — Session and Execution Integrity — Risk: High

- **e08s01** changes the lifetime of session ownership around connection-ready
  agent runs. The current CLI prepares/loads the session before client creation,
  then persists through callbacks; the lock must cover the entire run without
  being lost between those steps.
- **e08s02** changes `messages.jsonl`, `events.jsonl`, and metadata update
  durability. Checkpoints must never persist an incomplete tool group.
- **e08s03** changes list/show/delete behavior and makes previously hidden
  corruption visible. Delete-all gains partial-failure semantics.
- **e08s04** changes stored/replayed history and may require an explicit session
  schema migration or deterministic rejection path.
- **e08s05** changes tool/Codex result shape, event metadata, and summary behavior
  for truncation and timeout.
- **e08s06** changes write durability and observable tool phases/status.
- **Cross-epic impact:** e08s01/e08s02 precede e06s04; event/result changes must
  be shared with e06s05 and the e09 coverage policy.

### e09 — Quality and Platform Qualification — Risk: High

- **e09s01** modifies the official gate and lockfile; it should land early enough
  to protect subsequent implementation rather than only at release end.
- **e09s02** can make previously passing work fail on coverage, audit, or security
  policy. Thresholds and waiver rules are observable release contracts.
- **e09s03** changes `requires-python`, classifiers, lock resolution, build
  behavior, and every dependency/tool invocation across three interpreters.
- **e09s04** changes support claims and installation guidance; it must not lead
  the actual matrix evidence.
- **Cross-epic impact:** every earlier epic supplies coverage targets and must
  pass the final gate; e05 supplies the selected release identity.

### e10 — Release Evidence and Readiness — Risk: Medium to High

- **e10s01** affects local private evidence and manual procedures. The primary
  risk is credential/workspace leakage rather than runtime regression.
- **e10s02** consumes every earlier automated/manual result and can block release.
- **e10s03** affects package contents, docs, active state, build artifacts, and
  the final installed command. It must not package local internal review files.
- **Cross-epic impact:** e10 is blocked by accepted completion evidence from
  e05 through e09 and must run against one immutable candidate revision.

## Cross-epic dependency and sequencing map

1. **e05s01 first:** rebaseline findings before detailed implementation tasks
   are accepted. Do not plan stale fixes as if they remain open.
2. **e09s01 early:** establish reproducible lint/type checks before broad source
   edits; keep the full coverage/audit gate incremental until policies are set.
3. **Define shared contracts before parallel work:** privacy classification and
   tool results (e06/e08), CLI error/result presentation (e06/e07/e08), session
   transaction ownership (e06/e08), and profile metadata versioning (e07).
4. **e08s01 then e08s02 before e06s04:** sensitive-session persistence cannot be
   safely planned on top of the current unlocked rewrite behavior.
5. **e06s01/e06s02 before e06s03/e06s04:** authorization must extend one stable
   fail-closed classifier rather than bypass multiple ad-hoc checks.
6. **e07s01/e07s03 before e07s02/e07s04:** normalized status states are the
   observable vocabulary for verification and partial lifecycle outcomes.
7. **e08 resource and result stories after transaction contracts:** avoid
   introducing output/history formats that the checkpoint design later replaces.
8. **e09s02/e09s03 after focused regressions exist:** set gates from accepted
   risk evidence, then prove the full Python matrix.
9. **e10 last:** manual evidence, re-audit, and candidate production use one
   exact revision after all automated gates pass.

## Persistent data and migration impact

### Profiles

- `profiles.json` already has migration behavior and a credential key derived
  from stable profile naming. Verification history must remain secret-free and
  must not rename profiles or alter credential namespaces.
- Profile writes are atomic and cross-process locked. New status/verification
  fields must use the same transaction and preserve version-1 migration tests.
- Credential-backend `unavailable` is not equivalent to `absent`; no migration
  or cleanup may run based only on an unavailable check.

### Sessions

- Existing sessions use metadata plus `messages.jsonl` and `events.jsonl` with
  restrictive permissions. D-01 sensitive markers, lock state, checkpoint
  generation, and history bounds require an explicit schema/version policy.
- Existing tool-call/result pairs and provider extension fields must survive any
  migration. Rewriting or truncating only one member is forbidden.
- Sensitive content is plaintext local user data when explicit persistence is
  chosen. Resume must require renewed authority before loading/sending it.
- Lock files and temporary files inherit ownership, symlink, mode, deletion, and
  crash-cleanup requirements; they must not cause corrupt sessions to disappear.

### CLI and evidence metadata

- Provider verification history and release identity are durable metadata with
  backward-compatibility and redaction implications.
- Stable approval reasons, event types, status values, stdout/stderr placement,
  and exit codes are observable contracts. Rename/remove only with an explicit
  delta and regression tests.

## Test coverage

The current suite has 175 project tests across 17 modules plus 9 calculator
example tests. Existing tests provide a strong regression base, but not proof of
the new outcomes.

| Area | Existing coverage | Material gaps that plan-work must preserve |
| --- | --- | --- |
| Agent/approvals | Batch validation, write/execute authorization, read-only, preapproval, correlation, extension replay | No sensitive-read classifier, exact exception, hidden discovery, or sensitive-session consent tests. |
| Workspace tools | Argument validation, execution, confinement, symlink escapes | No direct `path_safety` tests; no ignore precedence, absolute-deny, TOCTOU privacy, omitted-name, or crash-safe write tests. |
| Top-level CLI | Connection dispatch, session behavior, streaming streams through scattered modules | No dedicated CLI error/exit matrix or version/identity contract; `cli.py` and terminal authorizer have no direct test module in the import scan. |
| Providers/profiles | Strong connection, credential failure, migration, concurrency, and catalog coverage | Only five provider CLI tests; no structured readiness, three-state credential output, explicit verification, sanitized history, or partial Codex transaction matrix. |
| Codex | Detection, argv, login/logout/status, exec, auth boundary | No normalized account-safe status, bounded output, metadata-only disconnect, or logout-plus-disconnect partial failure tests. |
| Sessions/context | Permissions, basic corruption, resume, CLI lifecycle, tool-pair budgeting | Only eight session tests; no process-level lock tests, atomic interruption matrix, active deletion, sensitivity marker, migration, or storage growth bounds. |
| Events/summaries | Ordering, correlation, redaction, plain-text tool error | No truncation, partial external operation, privacy denial, crash-safe write, or full denied-phase truth matrix. |
| Quality/release | `scripts/check.sh` passes tests/build/wheel smoke | No test for the gate itself, no locked mypy/audit/coverage/security tools, no Python 3.12/3.13 evidence, and no package/docs identity consistency test. |
| Manual evidence | MT-01 and MT-02 contain recorded passes | Remaining authorized macOS evidence is incomplete and not tied to the future candidate revision. |

Planned new modules named in sliced task files—workspace privacy, CLI errors,
session concurrency/transactions, provider verification, release baseline,
release identity/evidence, and quality-gate tests—are necessary coverage, not
optional suggestions.

## Observable compatibility impact

The following behavior changes are intentional and should be called out in
release notes and migration guidance:

- some previously automatic reads will be denied, and protected directory names
  will disappear from model-visible listings;
- authorized sensitive turns will not persist unless separately requested;
- provider output will stop using ambiguous “connected” claims;
- provider verification becomes an explicit potentially live operation;
- Codex disconnect and logout semantics become more explicit;
- a second process using one session will fail or wait instead of racing;
- corrupt sessions become visible and delete-all may return partial failure;
- large tool/process output may be truncated with metadata;
- the official check becomes stricter and may take longer or require cached
  audit databases/dependencies; and
- macOS becomes the qualified platform while Linux is described as preview.

## Risk: High

The change crosses shared APIs and security boundaries, changes two persisted
data domains, affects all command routes, and introduces behavior with no current
direct tests. Recent post-0.5.0 churn is concentrated in `cli.py`, `agent.py`,
provider orchestration, package metadata, and the lockfile—the same areas this
initiative changes again. Existing test coverage reduces regression risk but
does not lower the overall classification below High.

## Recommended action

**Proceed to `plan-work` with conditions:**

1. Plan e05s01 first and use its evidence to remove or rewrite stale tasks before
   any implementation plan is approved.
2. Write explicit before/after requirements for every `MODIFIED` story and keep
   CLI output, reason strings, event values, and persistence formats observable.
3. Treat privacy classification, session transactions, provider status data,
   CLI error presentation, and tool-result status as shared interfaces; do not
   create competing per-story variants.
4. Add failing focused tests before changing each shared module. Include real
   multi-process session tests and interruption/fault-injection tests.
5. Define profile and session migration/rollback behavior before the first write
   to either current format.
6. Land the reproducible lint/type gate early, then phase in coverage/audit
   thresholds from measured accepted baselines.
7. Keep live-provider, credential-bearing, release, publish, and push work behind
   separate explicit authorization and disposable evidence rules.
8. Require an independent plan audit before implementation because the aggregate
   scope is 151 BCP and several stories share the same modules.

No additional product-decision grilling is required if plan-work preserves
D-01 through D-05. Any proposal to persist sensitive reads by default, weaken
absolute credential-material denial, merge concurrent sessions, make status
implicitly live, retain Python 3.14-only without reassessment, or couple Codex
disconnect to automatic logout must return to `grill-me`.

## References

- `specs/product/SCOPE_LATEST.yaml`
- `specs/release-plan.yaml`
- `specs/execution-status.yaml`
- `specs/epics/e05-baseline-release-identity/`
- `specs/epics/e06-workspace-privacy-cli-trust/`
- `specs/epics/e07-provider-codex-lifecycle/`
- `specs/epics/e08-session-execution-integrity/`
- `specs/epics/e09-quality-platform-qualification/`
- `specs/epics/e10-release-evidence-readiness/`
- `docs/architecture.md`
- `docs/project-roadmap.md`
- `docs/project-review-2026-07-29.md` (local internal evidence)
- `docs/remediation-plan-2026-07-29.md` (local internal decision record)
