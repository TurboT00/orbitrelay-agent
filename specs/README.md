# Project Records

`specs/` contains only the active machine-readable project state:

- `state.yaml` records the current release baseline, decisions, and next
  planning entry point.

Completed plans, handoffs, release evidence, generated reports, and verification
artifacts are preserved under `specs/archive/`. They are historical context, not
current implementation instructions.

Human-facing documentation lives outside this directory:

- [README](../README.md): installation and operation;
- [Product status and roadmap](../docs/project-roadmap.md): completed scope and
  future direction; and
- [Architecture](../docs/architecture.md): durable system boundaries.
