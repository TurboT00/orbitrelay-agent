# Security Review — e01s01 Provider/Auth Profiles

- Merge base: `f423629862f78c772338a6acbefd6dacbe7b7fab`
- Reviewed head: `f591c66ff3dbb4d43f85b0696704e84b6821cfb6`
- Scope: feature diff against `main`, with emphasis on CLI input, profile
  deserialization, metadata paths, keyring operations, secret transport,
  deletion, and output redaction.

## Gate result

**PASS — no unresolved HIGH or CRITICAL findings with confidence >= 8.**

## Data-flow review

1. Profile names and endpoint metadata enter through argparse or versioned JSON.
2. `ProviderProfile` constrains names, rejects unknown fields and URL-embedded
   credentials, requires explicit capabilities, limits unauthenticated profiles
   to loopback, rejects query/fragment-bearing URLs, and requires HTTPS or
   loopback for authenticated profiles.
3. `ProfileRepository` writes only `ProviderProfile.to_dict()` data through an
   atomic same-directory replacement with mode `0600`.
4. API keys enter through a hidden prompt or stdin, flow directly to the
   credential-store adapter, and are retrieved into memory only when resolving
   an executable `api_key` profile.
5. `KeyringCredentialStore` allows only approved native macOS/Linux backends and
   wraps backend exceptions without including secret values.
6. Profile inspection passes output through recursive credential redaction.
7. The resolved credential reaches only `openai.OpenAI(api_key=...)`; it is not
   passed to the agent messages, local tools, command arguments, or metadata.

## Resolved during review

- **Credential loss on duplicate creation:** the initial coordinator could
  overwrite an existing keyring entry before metadata rejected the duplicate,
  then delete the replacement and leave the original profile without a secret.
  Fixed by rejecting existing metadata before keyring mutation and covered by
  `test_duplicate_creation_preserves_the_existing_credential`.
- **Plaintext remote credential transport:** named secret-backed profiles
  initially accepted remote `http://` endpoints. Fixed by requiring HTTPS or a
  loopback host and covered for both secret-backed auth kinds.

## Non-blocking hardening notes

- Metadata and native keyring writes cannot form one crash-atomic
  operating-system transaction. Supported macOS/Linux mutations are serialized
  across threads and processes, and compensation failures retain both causes;
  power-loss consistency remains explicitly outside the P1 guarantee.
- Backend security ultimately depends on the active native keyring. OrbitRelay
  rejects unavailable, chained, custom, alternate-file, and Windows backends;
  Windows profile support remains P7 work.
- macOS may allow the same Python executable to read a keyring item without a new
  prompt; this documented upstream behavior is disclosed in the README.

## Independent-review closure

Five dual-review rounds closed additional findings around URL-carried secrets,
cross-process consistency, unsafe storage paths, keyring backend selection,
ambiguous deletion, rollback diagnostics, credential namespaces, coherent
environment sources, transport-variable isolation, and dotenv interpolation.
The final AND-gate passed at Reviewer A 97/100 and Reviewer B 98/100 with zero
must-fix findings. See `specs/verifications/REVIEW-e01s01.md`.

The only production-file changes after the independently reviewed executable
implementation at `6699209` are non-executable `# story: e01s01` trace comments.
The release coverage commit adds tests only.
