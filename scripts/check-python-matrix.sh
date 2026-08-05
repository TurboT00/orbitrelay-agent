#!/usr/bin/env bash
# Qualify OrbitRelay on macOS for Python 3.12–3.14 (e09s03).
#
# Modes:
#   --candidate-floor 3.12 --automated-only
#       Stage a disposable tree with provisional metadata, leave tracked files
#       unchanged, and run the full automated contract on every minor.
#   --automated-only
#       Run the matrix against the current tracked tree/lock.
#   --apply-floor 3.12
#       Rewrite tracked pyproject requires-python/classifiers/mypy floor only
#       (caller must regenerate the lock and re-run the matrix).
#   --write-evidence PATH --revision REV
#       After a successful matrix, write revision-bound evidence JSON.

set -Eeuo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

if ! command -v uv >/dev/null 2>&1; then
    printf 'error: uv is required (https://docs.astral.sh/uv/)\n' >&2
    exit 1
fi

MINORS=(3.12 3.13 3.14)
candidate_floor=""
automated_only=0
apply_floor=""
evidence_path=""
evidence_revision=""
keep_stage=0

usage() {
    cat <<'EOF'
Usage:
  ./scripts/check-python-matrix.sh --candidate-floor 3.12 --automated-only
  ./scripts/check-python-matrix.sh --automated-only
  ./scripts/check-python-matrix.sh --apply-floor 3.12
  ./scripts/check-python-matrix.sh --automated-only --write-evidence PATH --revision REV
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --candidate-floor)
            candidate_floor="${2:-}"
            shift 2
            ;;
        --automated-only)
            automated_only=1
            shift
            ;;
        --apply-floor)
            apply_floor="${2:-}"
            shift 2
            ;;
        --write-evidence)
            evidence_path="${2:-}"
            shift 2
            ;;
        --revision)
            evidence_revision="${2:-}"
            shift 2
            ;;
        --keep-stage)
            keep_stage=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'error: unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -n "$apply_floor" ]]; then
    rendered="$(uv run python scripts/python_matrix.py render-floor --floor "$apply_floor")"
    printf '%s' "$rendered" > pyproject.toml
    printf 'Applied Python floor %s to pyproject.toml\n' "$apply_floor"
    printf 'Next: uv lock && ./scripts/check-python-matrix.sh --automated-only\n'
    exit 0
fi

if [[ "$automated_only" -ne 1 ]]; then
    printf 'error: this script currently supports --automated-only matrix runs\n' >&2
    usage >&2
    exit 2
fi

section() {
    printf '\n==> %s\n' "$1"
}

require_interpreters() {
    local minor
    for minor in "${MINORS[@]}"; do
        if ! uv python find "$minor" >/dev/null 2>&1; then
            printf 'error: Python %s is not available via uv (uv python install %s)\n' "$minor" "$minor" >&2
            exit 1
        fi
        printf 'interpreter %s -> %s\n' "$minor" "$(uv python find "$minor")"
    done
}

work_root="$repository_root"
stage_dir=""
cleanup() {
    if [[ -n "$stage_dir" && "$keep_stage" -eq 0 && -d "$stage_dir" ]]; then
        rm -rf "$stage_dir"
    fi
}
trap cleanup EXIT

if [[ -n "$candidate_floor" ]]; then
    section "Staging disposable candidate floor ${candidate_floor}"
    # Confirm tracked metadata still has the pre-qualification floor.
    tracked_requires="$(uv run python scripts/python_matrix.py show-tracked | sed -n 's/^requires-python=//p')"
    if [[ "$tracked_requires" != ">=3.14" && "$tracked_requires" != ">=${candidate_floor}" ]]; then
        printf 'error: unexpected tracked requires-python: %s\n' "$tracked_requires" >&2
        exit 1
    fi
    stage_dir="$(mktemp -d "${TMPDIR:-/tmp}/orbitrelay-matrix.XXXXXX")"
    uv run python scripts/python_matrix.py stage-candidate \
        --destination "$stage_dir" \
        --floor "$candidate_floor" >/dev/null
    work_root="$stage_dir"
    section "Relocking disposable candidate for floor ${candidate_floor}"
    (
        cd "$work_root"
        # Candidate lock is disposable; do not copy it back unless apply succeeds later.
        uv lock
    )
fi

section "Checking required interpreters"
require_interpreters

declare -a result_json_parts=()
overall_ok=1

run_minor() {
    local minor="$1"
    # Keep venvs outside the project tree so sdist/build never packs them.
    local venv_dir
    venv_dir="$(mktemp -d "${TMPDIR:-/tmp}/orbitrelay-matrix-venv-${minor}.XXXXXX")"
    section "Matrix Python ${minor}"
    (
        cd "$work_root"
        export UV_PROJECT_ENVIRONMENT="$venv_dir"
        export PYTHONDONTWRITEBYTECODE=1

        printf 'syncing locked environment for %s\n' "$minor"
        uv sync --locked --python "$minor"

        printf 'ruff\n'
        uv run --python "$minor" ruff check .

        printf 'mypy\n'
        uv run --python "$minor" mypy src/orbitrelay

        printf 'unit tests\n'
        uv run --python "$minor" python -m unittest discover -s tests -q

        printf 'calculator example\n'
        uv run --python "$minor" python examples/calculator/tests.py

        printf 'dependency audit\n'
        mkdir -p "$work_root/.cache/pip-audit"
        uv run --python "$minor" pip-audit --progress-spinner off --skip-editable \
            --cache-dir "$work_root/.cache/pip-audit" >/dev/null

        printf 'bandit\n'
        uv run --python "$minor" bandit -q -r src/orbitrelay -ll -ii >/dev/null

        printf 'imports and CLI\n'
        uv run --python "$minor" python -c "import orbitrelay; import orbitrelay.cli"
        uv run --python "$minor" orbitrelay --help >/dev/null
        uv run --python "$minor" python -m orbitrelay --help >/dev/null

        printf 'build + isolated wheel smoke\n'
        local artifacts
        artifacts="$(mktemp -d "${TMPDIR:-/tmp}/orbitrelay-matrix-build.XXXXXX")"
        uv build --out-dir "$artifacts" >/dev/null
        local wheel_path
        wheel_path="$(find "$artifacts" -maxdepth 1 -name '*.whl' -print -quit)"
        if [[ -z "$wheel_path" ]]; then
            printf 'error: build produced no wheel for Python %s\n' "$minor" >&2
            rm -rf "$artifacts"
            exit 1
        fi
        uv run --isolated --no-project --python "$minor" --with "$wheel_path" \
            orbitrelay --help >/dev/null
        uv run --isolated --no-project --python "$minor" --with "$wheel_path" \
            orbitrelay --version >/dev/null
        rm -rf "$artifacts"
    )
    local status=$?
    rm -rf "$venv_dir"
    return "$status"
}

for minor in "${MINORS[@]}"; do
    if run_minor "$minor"; then
        printf 'matrix Python %s: PASS\n' "$minor"
        result_json_parts+=("{\"python\":\"$minor\",\"status\":\"passed\",\"stages\":\"sync,ruff,mypy,tests,example,pip-audit,bandit,import,cli,build,wheel\"}")
    else
        printf 'matrix Python %s: FAIL\n' "$minor" >&2
        result_json_parts+=("{\"python\":\"$minor\",\"status\":\"failed\"}")
        overall_ok=0
        break
    fi
done

if [[ -n "$candidate_floor" ]]; then
    section "Confirming tracked tree unchanged by candidate run"
    if ! git -C "$repository_root" diff --quiet -- pyproject.toml uv.lock; then
        printf 'error: candidate matrix mutated tracked pyproject.toml or uv.lock\n' >&2
        exit 1
    fi
    printf 'tracked pyproject.toml and uv.lock unchanged\n'
fi

if [[ "$overall_ok" -ne 1 ]]; then
    printf '\nPython matrix failed.\n' >&2
    exit 1
fi

if [[ -n "$evidence_path" ]]; then
    if [[ -z "$evidence_revision" ]]; then
        evidence_revision="$(git -C "$repository_root" rev-parse HEAD)"
    fi
    tracked_requires="$(uv run python scripts/python_matrix.py show-tracked | sed -n 's/^requires-python=//p')"
    results_joined="$(IFS=,; printf '%s' "${result_json_parts[*]}")"
    tmp_evidence="$(mktemp)"
    cat >"$tmp_evidence" <<EOF
{
  "kind": "python-matrix-evidence",
  "version": 1,
  "revision": "$evidence_revision",
  "floor": "${candidate_floor:-tracked}",
  "tracked_requires_python": "$tracked_requires",
  "minors": ["3.12", "3.13", "3.14"],
  "results": [${results_joined}]
}
EOF
    mkdir -p "$(dirname "$evidence_path")"
    mv "$tmp_evidence" "$evidence_path"
    uv run python scripts/python_matrix.py validate-evidence "$evidence_path" --revision "$evidence_revision"
    printf 'wrote evidence %s\n' "$evidence_path"
fi

printf '\nAll Python matrix checks passed.\n'
if [[ -n "$candidate_floor" && "$tracked_requires" == ">=3.14" ]]; then
    printf 'Candidate floor %s is qualified. To apply tracked metadata:\n' "$candidate_floor"
    printf '  ./scripts/check-python-matrix.sh --apply-floor %s\n' "$candidate_floor"
    printf '  uv lock\n'
    printf '  ./scripts/check-python-matrix.sh --automated-only\n'
fi
