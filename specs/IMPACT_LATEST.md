# P1 Provider/Auth Profile Impact Assessment

## Target

`src/orbitrelay/config.py`, `src/orbitrelay/cli.py`, and their public
configuration/client-construction contracts. New profile and credential modules
will sit behind those existing entry points.

## Module zoom-out

- **`config.py` purpose:** validate environment configuration and return the
  concrete endpoint, secret, and model required to construct a provider client.
- **Callers:** `orbitrelay.cli.main`; direct contract tests in
  `tests/test_config.py`.
- **Contracts to preserve:** `OPENAI_*` compatibility, validation before client
  creation, immutable `ApiConfig`, and no import-time side effects.
- **`cli.py` purpose:** parse user intent, resolve the workspace and provider
  configuration, construct the OpenAI-compatible client, and invoke the agent.
- **Callers:** the `orbitrelay` entry point, `python -m orbitrelay`, and
  `tests/test_cli.py`.
- **Contracts to preserve:** the existing positional prompt, `--workspace`,
  `--verbose`, workspace validation before network access, and offline-testable
  client construction.

## Dependents (4)

- `src/orbitrelay/cli.py`: sole production caller of `load_api_config`.
- `tests/test_config.py`: covers environment defaults and validation.
- `tests/test_cli.py`: covers client construction, workspace validation, and
  import behavior.
- `src/orbitrelay/__main__.py`: delegates the module entry point to CLI main.

## Affected stories

- `e01s01`: Manage and run secure provider profiles.

## Test coverage

- Existing: environment fallback, missing key rejection, CLI wiring, workspace
  validation, and import side-effect checks.
- Gaps: profile schema, auth-kind rules, capability declarations, metadata
  atomicity, keyring failures, secret deletion, redaction, CLI profile lifecycle,
  selection precedence, and unsupported runtime auth kinds.

## Risk: High

The fan-in is small, but this changes the public CLI and the credential boundary;
a regression can leak secrets or prevent every provider invocation.

## Recommended action

Proceed on a feature branch with boundary-first TDD. Preserve the environment
path in every cycle, use fake credential stores and clients, and run the full
offline package check before handoff.
