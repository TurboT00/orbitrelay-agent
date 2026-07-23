# Traceability — e01 Provider/Auth Profiles

## Gate result

**PASS** — one of one stories covered, all acceptance criteria mapped, all
verification evidence present, and no heuristic links required.

The repository does not contain `scripts/trace-stories.sh`,
`scripts/check-blind-spots.sh`, or `scripts/lib/completeness-critic.sh`. This
gate therefore used the same deterministic rules manually and records its
machine-readable inputs in `specs/traceability-matrix.json` and
`specs/blind-spots.json`.

## Story coverage

| Story | Title | Source files | Test files | Verify artifacts | Status |
|---|---|---:|---:|---:|---|
| e01s01 | Manage and run secure provider profiles | 6 | 5 | 5 | Covered |

Every listed source and test file contains the explicit tag
`# story: e01s01`; the heuristic link ratio is therefore 0.0.

## Acceptance coverage

| Acceptance criterion | Primary executable evidence |
|---|---|
| Create, select, and run an API-key profile | `tests/test_profile_cli.py`, `tests/test_cli.py` |
| Preserve environment compatibility | `test_main_wires_environment_cli_and_agent_without_network` |
| Honor deterministic precedence | `test_explicit_profile_overrides_selection_and_environment` |
| Reject invalid configuration before network access | `tests/test_profiles.py`, client-construction rejection tests |
| Validate all four auth kinds | `test_accepts_each_declared_auth_kind_without_a_secret_value` |
| Reject unsupported runtime auth kinds | `test_rejects_deferred_auth_kind_before_client_creation` |
| Fail closed without native credential storage | `test_rejects_an_unavailable_backend` |
| Delete selected profiles safely | `test_list_show_select_and_delete_never_output_secret` |
| Retry partial deletion | `test_deletion_is_retry_safe_after_metadata_failure` |
| Redact nested credentials | `test_recursively_redacts_credential_like_fields` |

## Adversarial refutation

Attempted refutation: implementation and tests originally had no explicit story
tags, which would make this P0 story appear dark and would block release under
R3. The gap was real and was filled across all six implementation and five test
files. Re-running the check found no dark story, missing verify artifact,
heuristic-only link, or uncovered acceptance criterion.

## Rule evaluation

- R1: no undone stories.
- R2: the done story has verification evidence.
- R3: the P0 story has 100% trace coverage.
- R4: overall trace coverage is 100%.
- R6: no `e01-TEST_PLAN_LATEST.md` exists, so the scenario-tag rule is not
  applicable.
- R5: overall coverage is at least 80%, no critical gaps exist, and all verify
  artifacts are present — PASS.
- Oracle downgrade: none; heuristic ratio is 0.0.
- Drift: no `specs/drift-report.json` exists.
- Completeness critic: **FILLED**, with the missing explicit-link gap corrected.
