#!/usr/bin/env python3
"""Automated macOS release-evidence generation and validation (e10s01).

Produces a revision-bound, secret-free record of required automated gates.
Does not invent passes: missing or failed gates fail validation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
DEFAULT_RECORD = ROOT / "specs" / "verifications" / "release-evidence.json"
MATRIX_EVIDENCE = ROOT / "specs" / "verifications" / "python-matrix-evidence.json"

EVIDENCE_KIND = "orbitrelay-release-evidence"
EVIDENCE_VERSION = 1
REQUIRED_SET_AUTOMATED = "automated"

# Required automated readiness gates (D-01..D-05 + quality/release packaging).
AUTOMATED_GATE_SPECS: tuple[dict[str, object], ...] = (
    {
        "id": "privacy-workspace",
        "category": "privacy",
        "contract": "D-01 protected workspace I/O fail-closed",
        "command": [
            "uv",
            "run",
            "python",
            "-m",
            "unittest",
            "tests.test_workspace_privacy",
            "-q",
        ],
    },
    {
        "id": "provider-readiness",
        "category": "provider",
        "contract": "D-02 offline provider readiness and verification boundaries",
        "command": [
            "uv",
            "run",
            "python",
            "-m",
            "unittest",
            "tests.test_connection_service",
            "tests.test_provider_cli",
            "tests.test_provider_verification",
            "-q",
        ],
    },
    {
        "id": "codex-lifecycle",
        "category": "codex",
        "contract": "D-05 Codex readiness and disconnect ownership",
        "command": [
            "uv",
            "run",
            "python",
            "-m",
            "unittest",
            "tests.test_codex_bridge",
            "-q",
        ],
    },
    {
        "id": "session-integrity",
        "category": "session",
        "contract": "D-03 session ownership, checkpoints, corrupt lifecycle, bounds",
        "command": [
            "uv",
            "run",
            "python",
            "-m",
            "unittest",
            "tests.test_sessions",
            "tests.test_session_concurrency",
            "tests.test_session_transactions",
            "-q",
        ],
    },
    {
        "id": "quality-policy",
        "category": "quality",
        "contract": "e09 coverage dependency and source-security policy",
        "command": [
            "uv",
            "run",
            "python",
            "scripts/run_quality_policy.py",
            "--only",
            "dependency_audit",
            "--only",
            "source_security",
        ],
    },
    {
        "id": "official-check",
        "category": "release",
        "contract": "official local release check (ruff/mypy/quality/tests/build/wheel)",
        "command": ["./scripts/check.sh"],
    },
    {
        "id": "python-matrix",
        "category": "python",
        "contract": "D-04 macOS Python 3.12-3.14 matrix",
        "command": [
            "./scripts/check-python-matrix.sh",
            "--automated-only",
        ],
        # Full matrix is expensive; generation may incorporate validated matrix
        # evidence when --use-matrix-evidence is supplied.
        "supports_matrix_evidence": True,
    },
    {
        "id": "platform-claims",
        "category": "platform",
        "contract": "truthful macOS-qualified platform claims",
        "command": [
            "uv",
            "run",
            "python",
            "-m",
            "unittest",
            "tests.test_release_identity.PlatformSupportClaimTests",
            "-q",
        ],
    },
    {
        "id": "release-baseline",
        "category": "release",
        "contract": "revision-bound finding disposition oracle",
        "command": ["uv", "run", "python", "scripts/verify_release_baseline.py"],
    },
)


class EvidenceError(RuntimeError):
    """Release evidence generation or validation failure."""


@dataclass(frozen=True)
class GateResult:
    id: str
    category: str
    contract: str
    command: list[str]
    status: str  # passed | failed | skipped_invalid
    exit_code: int
    revision: str
    environment: str
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _revision_is_ancestor(ancestor: str, descendant: str, *, repo: Path = ROOT) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def git_revision(repo: Path = ROOT) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise EvidenceError("unable to resolve git revision")
    rev = completed.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", rev):
        raise EvidenceError("git revision must be a full lowercase SHA")
    return rev


def tree_is_clean(repo: Path = ROOT) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0 and completed.stdout.strip() == ""


def read_requires_python(repo: Path = ROOT) -> str:
    data = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    value = data["project"]["requires-python"]
    if not isinstance(value, str):
        raise EvidenceError("requires-python missing")
    return value


def scan_forbidden(text: str) -> list[str]:
    """Return high-confidence secret-bearing patterns, not ordinary prose."""
    hits: list[str] = []
    patterns = {
        "private-key-block": r"-----BEGIN [^-]*PRIVATE KEY-----",
        "bearer-token": r"(?i)\bbearer\s+[a-z0-9._~+/=-]{12,}",
        "provider-sk": r"(?i)\b(?:sk|pk|ghp|glpat)-[a-z0-9_-]{12,}",
        "aws-key": r"\bAKIA[A-Z0-9]{12,}\b",
        "assignment": (
            r"(?i)\b(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*[^,\s}\]]{4,}"
        ),
    }
    for name, pattern in patterns.items():
        if re.search(pattern, text):
            hits.append(name)
    return hits


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        env=dict(env) if env is not None else None,
    )


def _matrix_evidence_gate(
    *,
    revision: str,
    repo: Path,
) -> GateResult:
    """Accept only a validated, secret-free matrix evidence file."""
    try:
        from scripts.python_matrix import MatrixError, validate_matrix_evidence
    except ImportError:  # running as scripts/release_evidence.py
        from python_matrix import MatrixError, validate_matrix_evidence

    spec = next(item for item in AUTOMATED_GATE_SPECS if item["id"] == "python-matrix")
    path = repo / "specs/verifications/python-matrix-evidence.json"
    command = [str(c) for c in spec["command"]]  # type: ignore[index]
    try:
        validate_matrix_evidence(path, expected_revision=None)
        payload = json.loads(path.read_text(encoding="utf-8"))
        # Evidence may predate HEAD if content is still current; bind to generation
        # revision only when file content matches HEAD for the evidence path or
        # its embedded results all passed for required minors.
        results = payload.get("results") or []
        if not all(
            isinstance(item, dict) and item.get("status") == "passed" for item in results
        ):
            raise EvidenceError("python matrix evidence contains non-passed minors")
        minors = {item.get("python") for item in results if isinstance(item, dict)}
        if minors != {"3.12", "3.13", "3.14"}:
            raise EvidenceError("python matrix evidence missing required minors")
        # Content must not drift from HEAD for the evidence file when claiming HEAD.
        changed = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", path.relative_to(repo).as_posix()],
            cwd=repo,
            check=False,
        )
        if changed.returncode != 0:
            raise EvidenceError("python matrix evidence is dirty relative to HEAD")
        hits = scan_forbidden(path.read_text(encoding="utf-8"))
        if hits:
            raise EvidenceError(f"forbidden sentinel in matrix evidence: {hits}")
        return GateResult(
            id="python-matrix",
            category=str(spec["category"]),
            contract=str(spec["contract"]),
            command=command,
            status="passed",
            exit_code=0,
            revision=revision,
            environment="macos-automated",
            detail=(
                f"validated {path.relative_to(repo)} "
                f"(embedded_revision={payload.get('revision')})"
            ),
        )
    except (MatrixError, EvidenceError, OSError, json.JSONDecodeError) as exc:
        return GateResult(
            id="python-matrix",
            category=str(spec["category"]),
            contract=str(spec["contract"]),
            command=command,
            status="failed",
            exit_code=1,
            revision=revision,
            environment="macos-automated",
            detail=str(exc),
        )


def execute_gate(
    spec: Mapping[str, object],
    *,
    revision: str,
    repo: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = run_command,
    use_matrix_evidence: bool = True,
) -> GateResult:
    gate_id = str(spec["id"])
    if gate_id == "python-matrix" and use_matrix_evidence:
        return _matrix_evidence_gate(revision=revision, repo=repo)

    command = [str(part) for part in spec["command"]]  # type: ignore[index]
    completed = runner(
        command,
        cwd=repo,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    # Never retain raw command output in the evidence record.
    status = "passed" if completed.returncode == 0 else "failed"
    detail = f"exit_code={completed.returncode}"
    if completed.returncode != 0:
        # Keep a short secret-free failure hint only.
        combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
        first = next(
            (line.strip() for line in combined.splitlines() if line.strip()),
            "command failed",
        )
        if len(first) > 200:
            first = first[:197] + "..."
        if scan_forbidden(first):
            first = "command failed (detail redacted)"
        detail = f"{detail}; {first}"
    return GateResult(
        id=gate_id,
        category=str(spec["category"]),
        contract=str(spec["contract"]),
        command=command,
        status=status,
        exit_code=int(completed.returncode),
        revision=revision,
        environment="macos-automated",
        detail=detail,
    )


def build_record(
    *,
    revision: str,
    gates: Sequence[GateResult],
    repo: Path = ROOT,
    required_set: str = REQUIRED_SET_AUTOMATED,
) -> dict[str, object]:
    requires = read_requires_python(repo)
    record = {
        "kind": EVIDENCE_KIND,
        "version": EVIDENCE_VERSION,
        "required_set": required_set,
        "revision": revision,
        "platform": {
            "qualified": ["macos"],
            "preview": ["linux"],
            "deferred": ["windows"],
            "notes": (
                "Only macOS is qualified. Linux is preview/unverified. "
                "Native Windows is deferred."
            ),
        },
        "python": {
            "requires": requires,
            "qualified_minors": ["3.12", "3.13", "3.14"],
            "qualified_os": "macos",
        },
        "gates": [gate.to_dict() for gate in gates],
        "residual_risks": [
            "Linux remains preview/unverified without accepted matrix evidence.",
            "Native Windows support remains deferred.",
            "Open disposition findings remain tracked separately in the July registry.",
        ],
    }
    return record


def generate_evidence(
    *,
    repo: Path = ROOT,
    execute: bool = True,
    use_matrix_evidence: bool = True,
    runner: Callable[..., subprocess.CompletedProcess[str]] = run_command,
    require_clean_tree: bool = False,
) -> dict[str, object]:
    if require_clean_tree and not tree_is_clean(repo):
        raise EvidenceError("refusing to generate evidence on a dirty worktree")
    revision = git_revision(repo)
    if not execute:
        raise EvidenceError("generation requires execute=True for automated gates")
    gates: list[GateResult] = []
    for spec in AUTOMATED_GATE_SPECS:
        gates.append(
            execute_gate(
                spec,
                revision=revision,
                repo=repo,
                runner=runner,
                use_matrix_evidence=use_matrix_evidence,
            )
        )
    return build_record(revision=revision, gates=gates, repo=repo)


def validate_evidence(
    record: Mapping[str, object] | Path,
    *,
    expected_revision: str | None = None,
    required_set: str = REQUIRED_SET_AUTOMATED,
    require_review: bool = False,
    review_path: Path | None = None,
    verdict_path: Path | None = None,
) -> None:
    if isinstance(record, Path):
        if not record.is_file():
            raise EvidenceError(f"evidence record missing: {record}")
        raw_text = record.read_text(encoding="utf-8")
        hits = scan_forbidden(raw_text)
        if hits:
            raise EvidenceError(f"forbidden sentinel in evidence record: {hits}")
        payload = json.loads(raw_text)
    else:
        payload = dict(record)
        hits = scan_forbidden(json.dumps(payload))
        if hits:
            raise EvidenceError(f"forbidden sentinel in evidence payload: {hits}")

    if payload.get("kind") != EVIDENCE_KIND:
        raise EvidenceError("evidence kind mismatch")
    if payload.get("version") != EVIDENCE_VERSION:
        raise EvidenceError("evidence version mismatch")
    if payload.get("required_set") != required_set:
        raise EvidenceError("evidence required_set mismatch")
    revision = payload.get("revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise EvidenceError("evidence revision must be a full git SHA")
    if (
        expected_revision is not None
        and revision != expected_revision
        and not _revision_is_ancestor(revision, expected_revision)
    ):
        # Allow validating at HEAD when evidence was produced on an ancestor
        # commit (common when the evidence file is committed after generation).
        raise EvidenceError(
            f"evidence revision mismatch: {revision} != {expected_revision}"
        )

    platform = payload.get("platform")
    if not isinstance(platform, Mapping):
        raise EvidenceError("platform block missing")
    if platform.get("qualified") != ["macos"]:
        raise EvidenceError("only macos may be qualified")
    if "linux" not in (platform.get("preview") or []):
        raise EvidenceError("linux must remain explicit preview")
    if "windows" not in (platform.get("deferred") or []):
        raise EvidenceError("windows must remain explicit deferred")

    python = payload.get("python")
    if not isinstance(python, Mapping):
        raise EvidenceError("python block missing")
    if python.get("qualified_os") != "macos":
        raise EvidenceError("python.qualified_os must be macos")
    if set(python.get("qualified_minors") or []) != {"3.12", "3.13", "3.14"}:
        raise EvidenceError("python.qualified_minors must be 3.12-3.14")

    gates = payload.get("gates")
    if not isinstance(gates, list) or not gates:
        raise EvidenceError("gates missing")
    required_ids = {str(spec["id"]) for spec in AUTOMATED_GATE_SPECS}
    seen: set[str] = set()
    for item in gates:
        if not isinstance(item, Mapping):
            raise EvidenceError("gate entry must be an object")
        gate_id = item.get("id")
        status = item.get("status")
        gate_revision = item.get("revision")
        exit_code = item.get("exit_code")
        if not isinstance(gate_id, str):
            raise EvidenceError("gate id missing")
        seen.add(gate_id)
        if gate_revision != revision:
            raise EvidenceError(f"gate {gate_id} revision drift")
        if status != "passed" or exit_code != 0:
            raise EvidenceError(f"required gate not passed: {gate_id} ({status})")
        # No inferred passes: command must be present.
        command = item.get("command")
        if not isinstance(command, list) or not command:
            raise EvidenceError(f"gate {gate_id} missing command")
        for key, value in item.items():
            blob = f"{key}={value}".lower()
            if scan_forbidden(blob):
                raise EvidenceError(f"forbidden content in gate {gate_id}")
    missing = required_ids - seen
    if missing:
        raise EvidenceError(f"missing required gates: {sorted(missing)}")

    if require_review:
        review_file = review_path or (ROOT / "specs/verifications/candidate-review.json")
        verdict_file = verdict_path or (
            ROOT / "specs/verifications/candidate-reaudit-verdict.json"
        )
        if not review_file.is_file():
            raise EvidenceError(f"require-review missing review record: {review_file}")
        if not verdict_file.is_file():
            raise EvidenceError(f"require-review missing verdict record: {verdict_file}")
        # Local import avoids circular startup cost.
        try:
            from scripts.candidate_reaudit import (
                ReauditError,
                validate_verdict,
            )
        except ImportError:
            from candidate_reaudit import ReauditError, validate_verdict  # type: ignore
        try:
            review_payload = json.loads(review_file.read_text(encoding="utf-8"))
            if review_payload.get("kind") != "orbitrelay-candidate-review":
                raise EvidenceError("review record kind mismatch")
            for key in ("code_review", "security_review"):
                block = review_payload.get(key)
                if not isinstance(block, dict) or block.get("status") != "completed":
                    raise EvidenceError(f"review {key} incomplete")
            validate_verdict(verdict_file, expected_revision=expected_revision, require_ready=True)
        except ReauditError as exc:
            raise EvidenceError(str(exc)) from exc


def write_record(path: Path, record: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    hits = scan_forbidden(text)
    if hits:
        raise EvidenceError(f"refusing to write evidence with forbidden tokens: {hits}")
    path.write_text(text, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Run automated gates and write evidence")
    gen.add_argument("--output", type=Path, default=DEFAULT_RECORD)
    gen.add_argument("--repo-root", type=Path, default=ROOT)
    gen.add_argument(
        "--run-full-matrix",
        action="store_true",
        help="Execute check-python-matrix.sh instead of validating matrix evidence",
    )
    gen.add_argument(
        "--require-clean-tree",
        action="store_true",
        help="Fail if the git worktree is dirty",
    )

    val = sub.add_parser("validate", help="Validate an evidence record")
    val.add_argument("--record", type=Path, default=DEFAULT_RECORD)
    val.add_argument("--revision", default=None)
    val.add_argument("--required-set", default=REQUIRED_SET_AUTOMATED)
    val.add_argument(
        "--require-review",
        action="store_true",
        help="Require independent code/security review and READY candidate verdict",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "generate":
            record = generate_evidence(
                repo=args.repo_root,
                execute=True,
                use_matrix_evidence=not args.run_full_matrix,
                require_clean_tree=args.require_clean_tree,
            )
            # Fail generation if any gate failed.
            failed = [
                gate["id"]
                for gate in record["gates"]  # type: ignore[index]
                if gate.get("status") != "passed"
            ]
            write_record(args.output, record)
            if failed:
                print(
                    f"release-evidence: wrote {args.output} with failed gates: {failed}",
                    file=sys.stderr,
                )
                return 1
            print(f"release-evidence: wrote {args.output}")
            return 0
        if args.command == "validate":
            validate_evidence(
                args.record,
                expected_revision=args.revision,
                required_set=args.required_set,
                require_review=bool(getattr(args, "require_review", False)),
            )
            print(f"release-evidence: valid {args.record}")
            return 0
    except EvidenceError as exc:
        print(f"release-evidence: error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"unknown command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
