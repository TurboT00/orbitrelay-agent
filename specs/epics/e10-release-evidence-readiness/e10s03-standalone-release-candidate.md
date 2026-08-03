STORY KEY: e10s03
TITLE:     Produce a reproducible standalone release candidate
TYPE:      Story
PARENT:    e10
STATUS:    Planned
AUTHOR:    OrbitRelay team           DATE: 2026-08-03
MATURITY:  3
SIZE:      M
type:      feat
context:   infra
risk:      P0

### 1. Business narrative [reviewed]

The stabilization work must ship as one reproducible post-0.5.0 candidate before P5 rather than remain an unversioned main-branch state.

### 2. Value statement [reviewed]

Maintainers receive an audited artifact whose identity, contents, documentation, platform claims, and installed behavior all agree.

### 3. Actors and permissions [reviewed]

Maintainers build and inspect the candidate; release/publish/push remains separately authorized.

### 4. Trigger and preconditions [reviewed]

e10s02 verdict is ready, source revision is unchanged, and all required gates/evidence pass.

### 5. Main flow and business logic [reviewed]

Align all release surfaces, build from a clean checkout, run complete gates/matrix, inspect package contents, and retain secret-free artifact evidence.

### 6. Alternative flows and exceptions [reviewed]

Dirty checkout, identity drift, failed gate, changed revision, private-file inclusion, or evidence mismatch blocks candidate acceptance.

### 7. Interface elements [reviewed]

Both installed entry points, `--version`, README first run, provider/session commands, and wheel metadata are smoke-tested.

### 8. Domain model [reviewed]

A candidate record contains version, revision, artifact filename/hash, matrix/gate results, audit verdict, and content inspection outcome.

### 9. Integrations and boundaries [reviewed]

Touches package/docs/state/release plan, Hatchling build, wheel inspection, `scripts/check.sh`, matrix script, and evidence records.

### 10. Background processes [reviewed]

None.

### 11. Notifications [reviewed]

Candidate acceptance is distinct from publish/release authorization.

### 12. Audit and logging [reviewed]

Artifact evidence contains no credentials, provider payloads, private review files, workspace content, or untracked records.

### 13. Solution variabilities [reviewed]

Hatchling [OK] and `uv` [OK] remain the build/lock tools; no publishing tool is invoked.

### 14. Architecture decisions [reviewed]

Extend the existing official check and matrix rather than add a release framework. Reason for Depth: none; deterministic scripts and explicit evidence are sufficient.

### 15. Test strategy [reviewed]

Run identity/evidence contracts, complete offline release check, all-minor matrix, isolated-wheel smoke, and package-content allowlist.

### 16. Observability [reviewed]

The candidate summary reports identity, hash, revision, gate/matrix verdicts, and residual risks.

### 17. Acceptance criteria [reviewed]

#### ADDED: Standalone stabilization candidate

One clean, audited, post-0.5.0 artifact is reproducible and contains only intended public package material.

```gherkin
Feature: Standalone stabilization candidate
  Scenario: Clean candidate succeeds
    Given the audited immutable revision
    When release and matrix gates build the wheel
    Then identity, installed behavior, docs, state, and artifact hash agree

  Scenario: Private material would be packaged
    When package contents are inspected
    Then acceptance fails if untracked review/evidence or credential-bearing material is present

  Scenario: Publish authority is absent
    When candidate production completes
    Then no tag, push, publication, or hosted release occurs
```

### 18. Dependencies and sequencing [reviewed]

Final story; depends on e10s02 and every earlier release gate.

### 19. Out of scope [reviewed]

Tagging, pushing, publishing, hosted release creation, P5, or live provider use beyond separately accepted evidence.

### 20. Definition of done [reviewed]

Clean release/matrix gates, package inspection, identity/evidence tests, audit verdict, and security review all pass.

## Implementation Steps

1. Align identity, operator docs, architecture, roadmap, and active state with the audited candidate → verify: `uv run python -m unittest tests.test_release_identity tests.test_release_evidence -v`
2. Run complete release and Python matrix gates from a clean checkout → verify: `./scripts/check.sh && ./scripts/check-python-matrix.sh`
3. Prove installed identity and package-content privacy → verify: `uv run python -m unittest tests.test_release_identity tests.test_release_evidence -v && ./scripts/check.sh`

## Verification Script (Step-by-Step)

1. Confirm clean checkout and exact e10s02-audited revision.
2. Run both complete gates and build the wheel.
3. Inspect metadata, installed commands, package file list, and artifact hash.
4. Confirm no tag, push, publish, release, live probe, or P5 work occurred.

