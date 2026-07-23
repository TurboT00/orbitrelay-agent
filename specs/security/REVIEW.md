# Security Review — e01s01 Provider/Auth Profiles

- Merge base: `f423629862f78c772338a6acbefd6dacbe7b7fab`
- Reviewed head: `fce725bf8e955bc8c7ab2f41931c6196f1c9421f`
- Scope: feature diff against `main`, with emphasis on CLI input, profile
  deserialization, metadata paths, keyring operations, secret transport,
  deletion, and output redaction.

## Gate result

**PASS — no unresolved HIGH or CRITICAL findings with confidence >= 8.**

## Data-flow review

1. Profile names and endpoint metadata enter through argparse or versioned JSON.
2. `ProviderProfile` constrains names, rejects unknown fields and URL-embedded
   credentials, requires explicit capabilities, limits unauthenticated profiles
   to loopback, and requires HTTPS or loopback for secret-backed profiles.
3. `ProfileRepository` writes only `ProviderProfile.to_dict()` data through an
   atomic same-directory replacement with mode `0600`.
4. API keys enter through a hidden prompt or stdin, flow directly to the
   credential-store adapter, and are retrieved into memory only when resolving
   an executable `api_key` profile.
5. `KeyringCredentialStore` rejects unavailable and known alternate-file
   backends and wraps backend exceptions without including secret values.
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

- Metadata and native keyring writes cannot form one operating-system
  transaction. The chosen ordering and tests make ordinary failures retry-safe,
  but concurrent profile mutations by two OrbitRelay processes are not serialized
  in P1.
- Backend security ultimately depends on the active native keyring. OrbitRelay
  rejects no-backend and `keyrings.alt` modules, while platform certification and
  backend-specific policy remain P7 work.
- macOS may allow the same Python executable to read a keyring item without a new
  prompt; this documented upstream behavior is disclosed in the README.
