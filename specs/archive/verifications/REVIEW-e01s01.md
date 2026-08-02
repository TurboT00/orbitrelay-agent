# Independent Review — e01s01 Provider/Auth Profiles

**Final verdict: PASS — dual-reviewer AND-gate satisfied**

- Reviewed implementation: through `4858685`
- Post-pass non-behavioral focus refactor: `6699209`
- Merge base: `f423629862f78c772338a6acbefd6dacbe7b7fab`
- Review method: two independent fresh-context reviewers, no report sharing
  between reviewers; five-round maximum reached with a dual pass in round 5.
- Tooling note: reviewer sandboxes could not mount the worktree. Both reviewers
  received the same self-contained production-source bundle, test inventory,
  exact change summaries, and terminal verification evidence.

## Scores and AND-gate

| Round | Reviewer A | Reviewer B | Gate |
|---|---:|---:|---|
| 1/5 | 79, must-fix | 82, must-fix | FAIL |
| 2/5 | 94, no must-fix | 91, must-fix | FAIL |
| 3/5 | 90, must-fix | 97, no must-fix | FAIL |
| 4/5 | 90, must-fix | 92, must-fix | FAIL |
| 5/5 | **97, zero must-fix** | **98, zero must-fix** | **PASS** |

## Applied must-fix findings

1. Rejected query/fragment-bearing base URLs so credentials cannot be persisted
   or printed inside URLs.
2. Required HTTPS or loopback for every authenticated auth contract, including
   the future external-first-party CLI contract.
3. Added process-safe POSIX transaction locking across metadata and keyring
   mutation, with thread and subprocess concurrency coverage.
4. Namespaced keyring identifiers by canonical profile-store path.
5. Rejected symlinked, foreign-owned, and group/world-writable profile storage
   at the P1 application-directory boundary.
6. Replaced backend blacklisting with a native macOS/Linux keyring allowlist;
   chained, custom, alternate-file, fail, and Windows backends fail closed.
7. Verified deletion after `PasswordDeleteError` instead of assuming absence.
8. Preserved both metadata and cleanup failures in `CredentialRollbackError`.
9. Validated malformed URL authorities/ports and rejected whitespace/control
   characters.
10. Rejected `--secret-stdin` for non-secret auth kinds and made empty explicit
    profile names fail rather than fall through to the saved selection.
11. Scoped P1 profile persistence explicitly to macOS/Linux; Windows remains P7.
12. Prevented project dotenv from redirecting profile storage or mixing its
    endpoint/model with inherited process credentials.
13. Removed broad dotenv mutation; only the three supported provider fields are
    parsed into a separate mapping, so project proxy/CA settings cannot affect
    keyring or environment credentials.
14. Disabled dotenv interpolation and rejected unresolved `${...}` values so
    arbitrary inherited process secrets cannot enter provider fields.

## Applied should-fix findings

- Added adversarial tests for unsafe URLs, actual deletion failure, chained and
  unsupported backends, rollback failure, alternate profile homes, symlinks,
  unsafe permissions, same/different-name thread concurrency, subprocess file
  locking, coherent environment sources, proxy/CA isolation, and interpolation.
- Documented path-bound credential identifiers, trusted custom-path ancestry,
  explicit native-backend selection, platform scope, and limited crash
  durability.

## Consider findings resolved by user decision

- **Directory fsync:** deferred. P1 guarantees atomic replacement but does not
  claim power-loss atomicity across metadata and keyring.
- **Full custom-path ancestry traversal:** deferred. A custom
  `ORBITRELAY_HOME` and its ancestors are an explicit trusted-user boundary;
  immediate storage directory/file integrity is enforced.
- **Stable repository UUID:** deferred. Credential identifiers are path-bound in
  P1; moving the profile store requires credential re-entry.

## Final evidence

- `./scripts/check.sh`: PASS
- 92 project tests and 9 example tests
- Source distribution and wheel: PASS
- Isolated-wheel CLI smoke: PASS
- Ty diagnostics: zero
- Ruff diagnostics: zero
- Reviewer A: 97/100, zero must-fix
- Reviewer B: 98/100, zero must-fix
