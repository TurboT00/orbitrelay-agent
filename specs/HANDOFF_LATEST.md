# Agent Handoff — Start P3 Supported Hosted Access

**Audience:** a fresh coding agent with no prior conversation memory  
**Date:** 2026-07-23  
**Repo root:** working copy of `TurboT00/orbitrelay-agent` on branch `main`  
**Baseline:** `v0.3.0` released; HEAD should be at or after `1456e4e`

---

## 1. What you are continuing

OrbitRelay is a local coding-agent CLI that talks to OpenAI-compatible model
endpoints and runs workspace-confined tools.

### Shipped

| Release | Tag / PR | What it delivered |
|---|---|---|
| P1 Provider & auth profiles | PR #1 → `8bcefba` | Named profiles, native OS keyring credentials, env/dotenv isolation |
| P2 Tool approval policies | PR #2 → `3d1cc4f`, tag `v0.3.0` | Batch-first consent for writes/Python execution; read-only & pre-approved policies; run disable; secret-free audit |

### Your mission

Start **P3 — Supported hosted access**:

1. **Codex CLI bridge** — use the official `codex` executable as a process boundary
2. **xAI/Grok BYOK** — first-class API-key profile path for xAI without inventing OAuth

Do **not** start P4–P7 unless the user redirects you.

---

## 2. Cold-start checklist (do this first)

1. Confirm git:
   ```bash
   git status -sb
   git log -3 --oneline
   git describe --tags --always
   ```
   Expect clean `main`, recent commits including the 0.3.0 release, tag `v0.3.0`.
2. Read, in order:
   - `specs/HANDOFF_LATEST.md` (this file)
   - `specs/state.yaml`
   - `docs/project-roadmap.md` (P3 section + deferred decisions)
   - `specs/archive/RELEASE-0.3.0-tool-approval-policies.md`
   - `README.md` (profiles + approval flags)
3. Run baseline verification before changing code:
   ```bash
   ./scripts/check.sh
   ```
   Expect 145 project tests + 9 example tests and a green package smoke.
4. Begin planning with bigpowers discover flow, not coding:
   - `survey-context`
   - `scope-work` → write `specs/product/SCOPE_LATEST.yaml` for P3
   - then research / elaborate / plan-release / slice-tasks / plan-work
5. Ask the user before resolving open product decisions (section 6).

---

## 3. Product baseline the next agent inherits

### Runtime shape

- Package: `orbitrelay-agent` **0.3.0**
- Entry points: `orbitrelay`, `python -m orbitrelay`
- Agent loop: max 8 model responses; correlated tool results
- Tools: `get_files_info`, `get_file_content`, `write_file`, `run_python_file`
- Workspace confinement + symlink rejection are mandatory
- Approval session authorizes **full validated batches** before any side effect

### Auth / profiles (P1)

- Profile metadata: per-user only (`~/.orbitrelay` / `ORBITRELAY_HOME`)
- Secrets: native OS keyring only — **never** plaintext fallback
- Auth kinds modeled: `api_key`, `external_first_party_cli`, `local_none`, `local_service_bearer`
- **Only `api_key` is executable today** (`cli.py` rejects other kinds at runtime)
- Env vs dotenv: one source wins; no mixing partial process + dotenv settings

### Approvals (P2)

- Default policy: `confirm`
- Flags: `--approval-policy`, `--approval-timeout`, `--approve-tool`, `--verbose`
- Fail closed on noninteractive/EOF/timeout/invalid confirmation input
- Pre-approved requires exact consequential tool names (`write_file`, `run_python_file`)
- Verbose audit lines go to stderr and must stay secret-free

### Verification culture

- Offline tests with fakes/temp workspaces
- `scripts/check.sh` is the mechanical gate
- Prefer RED/GREEN commits and story tags
- Do not push without an explicit user request (unless the user already ordered a release push)

---

## 4. P3 objectives (from roadmap)

### 4.1 Codex CLI bridge

Must:

- Detect a separately installed official `codex` executable
- Delegate interactive login/logout to documented Codex commands
- Invoke documented noninteractive `codex exec` boundary
- **Never** read/copy `CODEX_HOME/auth.json` or reproduce OAuth
- Report Codex availability/version separately from model API profiles
- Confirm product/licensing expectations before promising subscription automation at scale

### 4.2 xAI / Grok BYOK

Must:

- Add an xAI profile preset via `XAI_API_KEY` or secure credential entry
- Keep generic OpenAI-compatible configuration available
- Monitor official docs for third-party OAuth; do **not** invent it
- Do not block API-key use while OAuth is unavailable

### Suggested success shape (for scoping, not final design)

- Users can create/select an xAI API-key profile and run the existing agent loop against xAI’s OpenAI-compatible endpoint
- Users can install/login Codex separately, and OrbitRelay can detect/use the CLI boundary without touching auth files
- Tool approval policies still apply to local tools regardless of provider
- All new behavior is covered by offline tests (fake subprocess for Codex; fake HTTP/config for xAI)

---

## 5. Important code map

| Area | Path |
|---|---|
| CLI / runtime wiring | `src/orbitrelay/cli.py` |
| Agent loop | `src/orbitrelay/agent.py` |
| Profiles & auth kinds | `src/orbitrelay/profiles.py` |
| Profile CLI | `src/orbitrelay/profile_cli.py` |
| Profile persistence | `src/orbitrelay/profile_store.py` |
| Credentials / keyring | `src/orbitrelay/credentials.py` |
| Env config | `src/orbitrelay/config.py` |
| Approvals | `src/orbitrelay/approvals.py`, `terminal_authorizer.py`, `approval_format.py` |
| Tools | `src/orbitrelay/tools/` |
| Redaction | `src/orbitrelay/redaction.py` |
| Checks | `scripts/check.sh` |
| Tests | `tests/` |

P1 already reserved `AuthKind.EXTERNAL_FIRST_PARTY_CLI` for Codex-like bridges.
P3 should connect that contract carefully rather than inventing a parallel auth system.

---

## 6. Decisions already locked

Do **not** reopen without user direction:

- Native OS credential store only; no plaintext secret files
- Profile metadata is per-user, not in-repo
- Codex auth = official CLI process boundary only
- Grok/xAI = BYOK until real third-party OAuth exists
- Approvals stay batch-first, fail-closed, run-local
- Pre-approved automation is exact per-tool allowlisting
- Local models wait until after hosted-access + conversations foundations

---

## 7. Open decisions (ask the user)

Before implementing, surface and resolve:

1. **Codex minimum version** and how subscription-backed automation may be described
2. Whether P3 ships **both** Codex bridge and xAI BYOK in one release, or slices them
3. Exact xAI base URL/model defaults and env var names (`XAI_API_KEY` vs profile-only)
4. How Codex runs relate to the existing OpenAI Chat Completions agent loop
   (bridge beside current loop vs alternate runtime path)
5. Packaging expectations: require preinstalled `codex` vs document install only

Still deferred (not P3 unless user expands scope):

- Session storage/encryption/retention (P4)
- Certified Ollama models (P5)
- Plugin trust model (P6)
- Windows certification (P7)
- CI setup (optional until multi-machine need is clear)

---

## 8. Recommended first skills / sequence

Use the project’s bigpowers lifecycle; do not jump to code:

1. `survey-context`
2. `scope-work` → replace `specs/product/SCOPE_LATEST.yaml` with P3 scope  
   (P2 scope archived at `specs/product/archive/SCOPE-P2-tool-approval-policies.yaml`)
3. `research-first` against official Codex + xAI docs (cite URLs)
4. `elaborate-spec` / `grill-me` for unresolved assumptions
5. `plan-release` / `slice-tasks` / `plan-work`
6. Only then `kickoff-branch` + `develop-tdd`

Suggested release target after planning: **0.4.0** (minor), codename roughly
“Supported hosted access”.

---

## 9. Explicit non-goals for the next session

- Do not weaken tool approvals or workspace confinement
- Do not read Codex `auth.json`, browser cookies, or undocumented auth state
- Do not implement conversation persistence or streaming (P4)
- Do not claim local-model support (P5)
- Do not add plugins (P6)
- Do not force Windows support (P7)
- Do not push/publish without explicit user request

---

## 10. Useful links

- Repo: https://github.com/TurboT00/orbitrelay-agent
- P2 PR: https://github.com/TurboT00/orbitrelay-agent/pull/2
- Release: https://github.com/TurboT00/orbitrelay-agent/releases/tag/v0.3.0
- Roadmap evidence table in `docs/project-roadmap.md` (Codex / xAI / Ollama / vLLM)

Official docs to re-fetch during research (do not rely on memory alone):

- Codex auth / noninteractive docs on developers.openai.com
- xAI API authentication docs on docs.x.ai

---

## 11. One-sentence charge

**Plan and implement P3 so OrbitRelay can use Codex through the official CLI boundary and xAI through BYOK profiles, without inventing OAuth, without touching foreign auth files, and without regressing P1 credentials or P2 approvals.**
