#!/usr/bin/env bash

set -Eeuo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

if ! command -v uv >/dev/null 2>&1; then
    printf 'error: uv is required (https://docs.astral.sh/uv/)\n' >&2
    exit 1
fi

artifact_directory="$(mktemp -d "${TMPDIR:-/tmp}/orbitrelay-check.XXXXXX")"
trap 'rm -rf "$artifact_directory"' EXIT

export PYTHONDONTWRITEBYTECODE=1

section() {
    printf '\n==> %s\n' "$1"
}

section "Checking lockfile"
uv lock --check

section "Synchronizing locked environment"
uv sync --locked

section "Running Ruff"
uv run ruff check .

section "Running mypy"
uv run mypy src/orbitrelay

section "Running risk-based quality policy"
# Coverage stage executes the project unit suite under coverage.py and fails
# closed on threshold or test failure. Dependency-audit and Bandit follow.
uv run python scripts/run_quality_policy.py

section "Running calculator example tests"
uv run python examples/calculator/tests.py

section "Checking imports and CLI entry point"
uv run python -c "import orbitrelay; import orbitrelay.cli"
uv run orbitrelay --help >/dev/null
uv run python -m orbitrelay --help >/dev/null

section "Building distributions"
uv build --out-dir "$artifact_directory"

wheel_path="$(find "$artifact_directory" -maxdepth 1 -name '*.whl' -print -quit)"
if [[ -z "$wheel_path" ]]; then
    printf 'error: build did not produce a wheel\n' >&2
    exit 1
fi

section "Checking the isolated wheel command"
uv run --isolated --no-project --with "$wheel_path" orbitrelay --help >/dev/null
uv run --isolated --no-project --with "$wheel_path" orbitrelay --version >/dev/null

printf '\nAll OrbitRelay checks passed.\n'
