# Threat Model — e03 Supported Hosted Access

**Status:** planning draft  
**Date:** 2026-07-24  
**Scope:** Codex CLI bridge, xAI BYOK, SuperGrok/X Premium OAuth

## Assets

- Native OS keyring secrets (API keys, OAuth access/refresh tokens)
- Provider profile metadata under `ORBITRELAY_HOME` / `~/.orbitrelay`
- Local workspace files (via OrbitRelay tools)
- User terminal output (must stay secret-free)
- Foreign CLI auth stores (`CODEX_HOME/auth.json`, `~/.grok/auth.json`) — **not OrbitRelay assets**; must not be read

## Trust boundaries

1. User terminal ↔ OrbitRelay process
2. OrbitRelay ↔ official `codex` subprocess (stdin/stdout/stderr only)
3. OrbitRelay ↔ xAI HTTPS (`api.x.ai`, `auth.x.ai`, optional `cli-chat-proxy.grok.com`)
4. OrbitRelay ↔ OS keyring backend
5. Model tool requests ↔ approval session ↔ workspace sandbox

## High risks

| ID | Threat | Mitigation |
|---|---|---|
| T1 | OrbitRelay reads foreign auth.json / cookies | Hard forbid; Codex is process-boundary only; SuperGrok tokens only via OrbitRelay keyring |
| T2 | OAuth tokens or API keys leak in logs/profiles | Redaction + secret-free profile metadata + keyring-only secret fields |
| T3 | Unbound OAuth code/state acceptance | PKCE S256 and/or device-code polling with origin checks; reject raw unbound codes |
| T4 | Model self-approves tools under hosted paths | P2 approval session remains mandatory for OrbitRelay tools |
| T5 | Codex exec side effects misattributed as OrbitRelay sandbox | Docs + runtime messaging: Codex owns its sandbox; OrbitRelay does not claim confinement for Codex-side tools |
| T6 | Shared Grok CLI client_id / session proxy breakage or ToS mismatch | Pin endpoints; fail closed; document consumer-session compatibility; BYOK fallback |
| T7 | HTTP 403 entitlement confusion after “successful” login | Explicit entitlement error path; guide to BYOK or tier upgrade; no silent retry loops |
| T8 | Subprocess injection via unsanitized Codex args | Fixed argv arrays; workspace path validated; no shell=True |

## Residual risks accepted for P3

- Using the publicly observed Grok CLI OAuth client_id (if chosen) is consumer-session compatibility, not OrbitRelay-owned app registration.
- Codex subscription/licensing enforcement remains owned by OpenAI/Codex CLI.
- Some SuperGrok tiers may be entitlement-gated despite successful browser login.

## Non-goals

Password collection, browser cookie scraping, plaintext token files, Windows keyring certification (P7).
