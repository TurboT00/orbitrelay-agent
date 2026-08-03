# Project Records

`specs/` contains the active machine-readable project state and planning records:

- `state.yaml` records the current release baseline, decisions, and next
  planning entry point;
- `product/SCOPE_LATEST.yaml` defines the approved stabilization boundary;
- `release-plan.yaml` indexes the active e05 through e10 epics in WSJF order;
- `execution-status.yaml` records flat epic and story status;
- `IMPACT_LATEST.md` records the current cross-epic blast radius, test gaps, and
  sequencing constraints;
- `IMPLEMENTATION_PLAN_LATEST.md` is the implementation-session entry point and
  links the 24 detailed story plans in dependency order; and
- `epics/` contains the active epic manifests and sliced story task files.

Story specification Markdown files are added by `plan-work`. Their absence after
`slice-tasks` is intentional.

Completed plans, handoffs, release evidence, generated reports, and verification
artifacts are preserved under `specs/archive/`. They are historical context, not
current implementation instructions.

Human-facing documentation lives outside this directory:

- [README](../README.md): installation and operation;
- [Product status and roadmap](../docs/project-roadmap.md): completed scope and
  future direction; and
- [Architecture](../docs/architecture.md): durable system boundaries.
