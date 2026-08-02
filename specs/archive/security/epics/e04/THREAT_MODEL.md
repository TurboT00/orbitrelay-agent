# Threat Model — e04 Conversations and Streaming

**Status:** planning draft  
**Date:** 2026-07-24  
**Scope:** run event model, streaming, local sessions, context budgeting, summaries

## Assets

- Session transcripts (user prompts, model text, tool args/results, approval metadata)
- Session metadata (ids, timestamps, workspace path labels)
- Live stream output on terminal / injectable sinks
- Existing secrets in OS keyring (must not enter session files)

## Trust boundaries

1. Model provider stream ↔ OrbitRelay event normalizer
2. Event bus ↔ terminal/JSONL sink
3. Event bus ↔ session store under ORBITRELAY_HOME/sessions
4. Session resume ↔ agent message history reconstruction
5. Approval session ↔ tool execution (unchanged P2 boundary)

## High risks

| ID | Threat | Mitigation |
|---|---|---|
| T1 | Secrets written into session files | Redact on serialize; never persist CredentialStore material; tests for key/token absence |
| T2 | World-readable session directory | 0700/0600; reject symlinks and group/world-writable paths (ProfileStore pattern) |
| T3 | Stream sink leaks tool content/secrets | Allowlisted event fields; reuse redaction helpers; verbose ≠ dump raw payloads |
| T4 | Corrupt/partial session resume executes wrong tools | Fail closed on corrupt JSONL; validate schema/version; atomic metadata writes |
| T5 | Context trim orphans tool results → model confusion/injection | Pair-preserving budget algorithm with tests |
| T6 | Session path traversal via session id | Strict session id charset; resolve paths under sessions root only |
| T7 | Resume ignores approval policy | Fresh ApprovalSession per run; persisted history does not imply pre-approval |

## Residual risks accepted for P4

- No app-level encryption: local disk attackers with user privileges can read sessions.
- Streaming increases partial-output moderation difficulty (provider guidance); terminal product accepts this with user-visible progressive text.

## Non-goals

Cloud sync, multi-user session sharing, encrypting sessions with keychain keys, auto-TTL purge.
