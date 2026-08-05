#!/usr/bin/env python3
"""Produce and validate a reproducible standalone release candidate (e10s03).

Candidate production builds an audited wheel, inspects package contents for
private material, binds identity/revision/hash/gate/verdict evidence, and
never tags, pushes, or publishes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.candidate_reaudit import ReauditError, validate_verdict  # noqa: E402
from scripts.release_evidence import (  # noqa: E402
    DEFAULT_RECORD as DEFAULT_RELEASE_EVIDENCE,
    scan_forbidden,
    validate_evidence,
)

SELECTED_VERSION = "0.6.0"
PACKAGE_NAME = "orbitrelay-agent"
CANDIDATE_KIND = "orbitrelay-release-candidate"
CANDIDATE_SCHEMA_VERSION = 1
DEFAULT_CANDIDATE = ROOT / "specs" / "verifications" / "release-candidate.json"
DEFAULT_VERDICT = ROOT / "specs" / "verifications" / "candidate-reaudit-verdict.json"
DEFAULT_MATRIX = ROOT / "specs" / "verifications" / "python-matrix-evidence.json"
READY_VERDICTS = frozenset({"READY", "READY_WITH_EXPLICIT_ACCEPTANCE"})

# Path prefixes / exact basenames that must never appear inside the wheel.
FORBIDDEN_WHEEL_PREFIXES = (
    "specs/",
    "docs/",
    "tests/",
    "scripts/",
    "examples/",
    ".git/",
)
FORBIDDEN_WHEEL_BASENAMES = {
    ".env",
    "profiles.json",
    "AGENTS.md",
    "CONVENTIONS.md",
    "project-review-2026-07-29.md",
    "remediation-plan-2026-07-29.md",
}
FORBIDDEN_WHEEL_SUBSTRINGS = (
    "project-review",
    "remediation-plan",
)

PRIVATE_RECORD_NAMES = (
    "project-review-2026-07-29.md",
    "remediation-plan-2026-07-29.md",
)


class CandidateError(RuntimeError):
    """Raised when candidate production or validation fails."""


def git_revision(repo: Path = ROOT) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise CandidateError(f"cannot resolve git revision: {completed.stderr.strip()}")
    revision = completed.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise CandidateError(f"unexpected git revision: {revision!r}")
    return revision


def tree_is_clean(repo: Path = ROOT) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise CandidateError(f"cannot inspect git status: {completed.stderr.strip()}")
    return completed.stdout.strip() == ""


def read_package_identity(repo: Path = ROOT) -> dict[str, str]:
    data = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        raise CandidateError("pyproject.toml missing project table")
    name = project.get("name")
    version = project.get("version")
    if not isinstance(name, str) or not name.strip():
        raise CandidateError("project.name must be non-empty text")
    if not isinstance(version, str) or not version.strip():
        raise CandidateError("project.version must be non-empty text")
    module_text = (repo / "src" / "orbitrelay" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', module_text, re.M)
    if match is None:
        raise CandidateError("orbitrelay.__version__ not found")
    module_version = match.group(1)
    return {
        "package_name": name,
        "package_version": version,
        "module_version": module_version,
    }


def assert_identity_aligned(identity: Mapping[str, str]) -> None:
    if identity["package_name"] != PACKAGE_NAME:
        raise CandidateError(
            f"package name {identity['package_name']!r} != {PACKAGE_NAME!r}"
        )
    for key in ("package_version", "module_version"):
        if identity[key] != SELECTED_VERSION:
            raise CandidateError(
                f"{key} {identity[key]!r} != selected identity {SELECTED_VERSION!r}"
            )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def list_wheel_members(wheel: Path) -> list[str]:
    try:
        with zipfile.ZipFile(wheel) as archive:
            return sorted(archive.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise CandidateError(f"cannot read wheel {wheel}: {exc}") from exc


def inspect_wheel_contents(members: Sequence[str]) -> dict[str, Any]:
    """Return content inspection outcome; raise if private material is present."""
    package_members = [name for name in members if name.startswith("orbitrelay/")]
    dist_info = [
        name
        for name in members
        if re.match(r"^orbitrelay_agent-[^/]+\.dist-info/", name)
    ]
    unexpected = [
        name
        for name in members
        if not name.startswith("orbitrelay/")
        and not re.match(r"^orbitrelay_agent-[^/]+\.dist-info/", name)
    ]
    forbidden_hits: list[str] = []
    for name in members:
        lowered = name.lower()
        basename = Path(name).name
        for prefix in FORBIDDEN_WHEEL_PREFIXES:
            if lowered.startswith(prefix.lower()) or f"/{prefix.lower()}" in f"/{lowered}":
                forbidden_hits.append(f"{name} (prefix {prefix})")
        if basename in FORBIDDEN_WHEEL_BASENAMES or basename.lower() in {
            item.lower() for item in FORBIDDEN_WHEEL_BASENAMES
        }:
            forbidden_hits.append(f"{name} (basename {basename})")
        for marker in FORBIDDEN_WHEEL_SUBSTRINGS:
            if marker.lower() in lowered:
                forbidden_hits.append(f"{name} (marker {marker})")
        for private in PRIVATE_RECORD_NAMES:
            if private.lower() in lowered:
                forbidden_hits.append(f"{name} (private {private})")
    if not package_members:
        raise CandidateError("wheel contains no orbitrelay package files")
    if not dist_info:
        raise CandidateError("wheel missing orbitrelay_agent dist-info metadata")
    if unexpected:
        raise CandidateError(
            "wheel contains unexpected non-package paths: " + ", ".join(unexpected[:12])
        )
    if forbidden_hits:
        raise CandidateError(
            "wheel contains forbidden private material: " + "; ".join(forbidden_hits[:12])
        )
    return {
        "status": "passed",
        "member_count": len(members),
        "package_member_count": len(package_members),
        "dist_info_member_count": len(dist_info),
        "forbidden_hits": [],
        "sample_members": list(members[:12]),
    }


def smoke_installed_wheel(wheel: Path, *, repo: Path = ROOT) -> dict[str, Any]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    commands = {
        "help": ["uv", "run", "--isolated", "--no-project", "--with", str(wheel), "orbitrelay", "--help"],
        "version": [
            "uv",
            "run",
            "--isolated",
            "--no-project",
            "--with",
            str(wheel),
            "orbitrelay",
            "--version",
        ],
        "module_version": [
            "uv",
            "run",
            "--isolated",
            "--no-project",
            "--with",
            str(wheel),
            "python",
            "-m",
            "orbitrelay",
            "--version",
        ],
    }
    results: dict[str, Any] = {}
    for name, command in commands.items():
        completed = subprocess.run(
            command,
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        text = completed.stdout + completed.stderr
        hits = scan_forbidden(text)
        if hits:
            raise CandidateError(f"installed smoke {name} leaked forbidden material: {hits}")
        if completed.returncode != 0:
            raise CandidateError(
                f"installed smoke {name} failed ({completed.returncode}): {text[-400:]}"
            )
        if name != "help" and SELECTED_VERSION not in text:
            raise CandidateError(
                f"installed smoke {name} did not report identity {SELECTED_VERSION}: {text!r}"
            )
        results[name] = {
            "status": "passed",
            "exit_code": completed.returncode,
            "reports_identity": SELECTED_VERSION in text if name != "help" else None,
        }
    return results


def build_wheel(*, repo: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["uv", "build", "--out-dir", str(out_dir)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if completed.returncode != 0:
        raise CandidateError(
            f"uv build failed ({completed.returncode}): "
            f"{(completed.stdout + completed.stderr)[-800:]}"
        )
    wheels = sorted(out_dir.glob("*.whl"))
    if not wheels:
        raise CandidateError("uv build produced no wheel")
    wheel = wheels[0]
    if SELECTED_VERSION not in wheel.name:
        raise CandidateError(f"wheel name lacks selected identity: {wheel.name}")
    # hatch normalizes the distribution name to orbitrelay_agent
    normalized = PACKAGE_NAME.replace("-", "_")
    if (
        normalized not in wheel.name
        and PACKAGE_NAME not in wheel.name
        and "orbitrelay_agent" not in wheel.name
    ):
        raise CandidateError(f"unexpected wheel package name: {wheel.name}")
    return wheel


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CandidateError(f"{path} must be a JSON object")
    return value


def _validate_upstream_evidence(
    *,
    revision: str,
    release_evidence: Path,
    verdict_path: Path,
    matrix_path: Path,
) -> dict[str, Any]:
    try:
        validate_evidence(
            release_evidence,
            expected_revision=revision,
            required_set="automated",
            require_review=True,
        )
    except Exception as exc:  # EvidenceError and friends
        # release evidence revision may be an ancestor of HEAD when rebound later
        try:
            validate_evidence(
                release_evidence,
                expected_revision=None,
                required_set="automated",
                require_review=True,
            )
        except Exception as nested:
            raise CandidateError(
                f"release evidence invalid: {exc}; retry without exact revision: {nested}"
            ) from nested

    evidence = _load_json(release_evidence)
    evidence_revision = str(evidence.get("revision") or "")
    if evidence_revision and evidence_revision != revision:
        # Accept ancestor evidence for the candidate tip when gates already passed.
        completed = subprocess.run(
            ["git", "merge-base", "--is-ancestor", evidence_revision, revision],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise CandidateError(
                f"release evidence revision {evidence_revision} is not an ancestor of {revision}"
            )

    try:
        validate_verdict(verdict_path, expected_revision=None, require_ready=True)
    except ReauditError as exc:
        raise CandidateError(f"candidate re-audit invalid: {exc}") from exc
    verdict = _load_json(verdict_path)
    verdict_value = str(verdict.get("verdict") or "")
    if verdict_value not in READY_VERDICTS:
        raise CandidateError(f"candidate re-audit not ready: {verdict_value}")

    if not matrix_path.is_file():
        raise CandidateError(f"missing matrix evidence: {matrix_path}")
    matrix = _load_json(matrix_path)
    matrix_status = str(matrix.get("status") or matrix.get("verdict") or "present")

    gates = evidence.get("gates")
    gate_summary: dict[str, str] = {}
    if isinstance(gates, list):
        for gate in gates:
            if isinstance(gate, dict) and isinstance(gate.get("id"), str):
                gate_summary[str(gate["id"])] = str(gate.get("status") or "unknown")

    return {
        "release_evidence": {
            "path": str(release_evidence.relative_to(ROOT))
            if release_evidence.is_relative_to(ROOT)
            else str(release_evidence),
            "revision": evidence_revision,
            "gates": gate_summary,
            "status": "passed",
        },
        "audit_verdict": {
            "path": str(verdict_path.relative_to(ROOT))
            if verdict_path.is_relative_to(ROOT)
            else str(verdict_path),
            "verdict": verdict_value,
            "status": "passed",
        },
        "matrix": {
            "path": str(matrix_path.relative_to(ROOT))
            if matrix_path.is_relative_to(ROOT)
            else str(matrix_path),
            "status": matrix_status,
        },
    }


def build_candidate_record(
    *,
    revision: str,
    identity: Mapping[str, str],
    wheel: Path,
    wheel_members: Sequence[str],
    content_inspection: Mapping[str, Any],
    installed_smoke: Mapping[str, Any],
    upstream: Mapping[str, Any],
    artifact_retained: bool,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "kind": CANDIDATE_KIND,
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "status": "accepted",
        "identity": {
            "version": SELECTED_VERSION,
            "package_name": identity["package_name"],
            "module_version": identity["module_version"],
            "package_version": identity["package_version"],
        },
        "revision": revision,
        "artifact": {
            "filename": wheel.name,
            "sha256": sha256_file(wheel),
            "size_bytes": wheel.stat().st_size,
            "retained": artifact_retained,
            "path": str(wheel) if artifact_retained else None,
        },
        "gates": upstream["release_evidence"],
        "matrix": upstream["matrix"],
        "audit_verdict": upstream["audit_verdict"],
        "content_inspection": dict(content_inspection),
        "installed_smoke": dict(installed_smoke),
        "publish_authority": {
            "tag": False,
            "push": False,
            "publish": False,
            "hosted_release": False,
            "note": "Candidate production is not publish authorization.",
        },
        "residual_risks": [
            "Explicit release-owner approval is still required before tag/push/publish.",
            "Accepted and deferred disposition findings remain residual risk under READY_WITH_EXPLICIT_ACCEPTANCE.",
        ],
        "member_count": len(wheel_members),
    }
    serialized = json.dumps(record, sort_keys=True)
    hits = scan_forbidden(serialized)
    if hits:
        raise CandidateError(f"candidate record contains forbidden material: {hits}")
    for private in PRIVATE_RECORD_NAMES:
        if private in serialized:
            raise CandidateError(f"candidate record references private file {private}")
    return record


def produce_candidate(
    *,
    repo: Path = ROOT,
    output: Path = DEFAULT_CANDIDATE,
    release_evidence: Path = DEFAULT_RELEASE_EVIDENCE,
    verdict_path: Path = DEFAULT_VERDICT,
    matrix_path: Path = DEFAULT_MATRIX,
    artifact_dir: Path | None = None,
    require_clean_tree: bool = True,
    retain_artifact: bool = False,
) -> dict[str, Any]:
    if require_clean_tree and not tree_is_clean(repo):
        raise CandidateError("git worktree is dirty; refuse candidate production")

    identity = read_package_identity(repo)
    assert_identity_aligned(identity)
    revision = git_revision(repo)
    upstream = _validate_upstream_evidence(
        revision=revision,
        release_evidence=release_evidence,
        verdict_path=verdict_path,
        matrix_path=matrix_path,
    )

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if artifact_dir is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="orbitrelay-rc-")
        build_dir = Path(temp_dir.name)
        artifact_retained = False
    else:
        build_dir = artifact_dir
        artifact_retained = retain_artifact

    try:
        wheel = build_wheel(repo=repo, out_dir=build_dir)
        members = list_wheel_members(wheel)
        inspection = inspect_wheel_contents(members)
        smoke = smoke_installed_wheel(wheel, repo=repo)

        retained_path: Path | None = None
        if retain_artifact:
            output.parent.mkdir(parents=True, exist_ok=True)
            retained_dir = output.parent / "artifacts"
            retained_dir.mkdir(parents=True, exist_ok=True)
            retained_path = retained_dir / wheel.name
            shutil.copy2(wheel, retained_path)
            wheel_for_record = retained_path
            artifact_retained = True
        else:
            wheel_for_record = wheel

        record = build_candidate_record(
            revision=revision,
            identity=identity,
            wheel=wheel_for_record,
            wheel_members=members,
            content_inspection=inspection,
            installed_smoke=smoke,
            upstream=upstream,
            artifact_retained=artifact_retained,
        )
        if not retain_artifact:
            record["artifact"]["path"] = None
        elif retained_path is not None:
            try:
                record["artifact"]["path"] = str(retained_path.relative_to(repo))
            except ValueError:
                record["artifact"]["path"] = str(retained_path)

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return record
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def validate_candidate(
    path: Path,
    *,
    expected_revision: str | None = None,
    require_accepted: bool = True,
) -> dict[str, Any]:
    record = _load_json(path)
    for field in (
        "kind",
        "schema_version",
        "status",
        "identity",
        "revision",
        "artifact",
        "gates",
        "matrix",
        "audit_verdict",
        "content_inspection",
        "installed_smoke",
        "publish_authority",
    ):
        if field not in record:
            raise CandidateError(f"candidate missing field {field}")
    if record.get("kind") != CANDIDATE_KIND:
        raise CandidateError(f"unexpected candidate kind: {record.get('kind')!r}")
    if record.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
        raise CandidateError("unexpected candidate schema_version")
    if require_accepted and record.get("status") != "accepted":
        raise CandidateError(f"candidate status is not accepted: {record.get('status')!r}")

    identity = record["identity"]
    if not isinstance(identity, dict):
        raise CandidateError("identity must be an object")
    if identity.get("version") != SELECTED_VERSION:
        raise CandidateError(f"candidate identity version != {SELECTED_VERSION}")
    if identity.get("package_name") != PACKAGE_NAME:
        raise CandidateError("candidate package_name mismatch")

    revision = record.get("revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise CandidateError("candidate revision must be a 40-char git sha")
    if expected_revision is not None and revision != expected_revision:
        # allow ancestor binding similar to release evidence
        completed = subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, expected_revision],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0 and revision != expected_revision:
            raise CandidateError(
                f"candidate revision {revision} does not match expected {expected_revision}"
            )

    artifact = record["artifact"]
    if not isinstance(artifact, dict):
        raise CandidateError("artifact must be an object")
    for field in ("filename", "sha256", "size_bytes"):
        if field not in artifact:
            raise CandidateError(f"artifact missing {field}")
    if SELECTED_VERSION not in str(artifact.get("filename")):
        raise CandidateError("artifact filename lacks selected identity")
    sha = str(artifact.get("sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise CandidateError("artifact sha256 must be 64 hex chars")

    content = record["content_inspection"]
    if not isinstance(content, dict) or content.get("status") != "passed":
        raise CandidateError("content inspection did not pass")
    if content.get("forbidden_hits"):
        raise CandidateError("content inspection reports forbidden hits")

    smoke = record["installed_smoke"]
    if not isinstance(smoke, dict):
        raise CandidateError("installed_smoke must be an object")
    for name in ("help", "version", "module_version"):
        item = smoke.get(name)
        if not isinstance(item, dict) or item.get("status") != "passed":
            raise CandidateError(f"installed smoke {name} did not pass")

    publish = record["publish_authority"]
    if not isinstance(publish, dict):
        raise CandidateError("publish_authority must be an object")
    for key in ("tag", "push", "publish", "hosted_release"):
        if publish.get(key) is not False:
            raise CandidateError(f"publish_authority.{key} must be false")

    audit = record["audit_verdict"]
    if not isinstance(audit, dict):
        raise CandidateError("audit_verdict must be an object")
    if str(audit.get("verdict") or "") not in READY_VERDICTS:
        raise CandidateError("audit verdict is not READY")

    serialized = json.dumps(record, sort_keys=True)
    hits = scan_forbidden(serialized)
    if hits:
        raise CandidateError(f"candidate record contains forbidden material: {hits}")
    return record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prod = sub.add_parser("produce", help="Build and record a standalone release candidate")
    prod.add_argument("--output", type=Path, default=DEFAULT_CANDIDATE)
    prod.add_argument("--repo-root", type=Path, default=ROOT)
    prod.add_argument("--release-evidence", type=Path, default=DEFAULT_RELEASE_EVIDENCE)
    prod.add_argument("--verdict", type=Path, default=DEFAULT_VERDICT)
    prod.add_argument("--matrix-evidence", type=Path, default=DEFAULT_MATRIX)
    prod.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Optional directory for build output (default: disposable temp)",
    )
    prod.add_argument(
        "--retain-artifact",
        action="store_true",
        help="Copy the wheel next to the candidate record (still not a publish step)",
    )
    prod.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Permit production from a dirty worktree (not for official candidates)",
    )

    val = sub.add_parser("validate", help="Validate a release-candidate record")
    val.add_argument("--record", type=Path, default=DEFAULT_CANDIDATE)
    val.add_argument("--revision", default=None)

    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "produce":
            record = produce_candidate(
                repo=args.repo_root,
                output=args.output,
                release_evidence=args.release_evidence,
                verdict_path=args.verdict,
                matrix_path=args.matrix_evidence,
                artifact_dir=args.artifact_dir,
                require_clean_tree=not args.allow_dirty,
                retain_artifact=args.retain_artifact,
            )
            print(
                "release-candidate: accepted "
                f"version={record['identity']['version']} "
                f"revision={record['revision'][:12]} "
                f"artifact={record['artifact']['filename']} "
                f"sha256={record['artifact']['sha256'][:16]}… "
                f"audit={record['audit_verdict']['verdict']}"
            )
            print(f"release-candidate: wrote {args.output}")
            print(
                "release-candidate: no tag/push/publish performed "
                "(candidate production is not publish authorization)"
            )
            return 0
        if args.command == "validate":
            record = validate_candidate(args.record, expected_revision=args.revision)
            print(
                f"release-candidate: valid {args.record} "
                f"status={record['status']} version={record['identity']['version']}"
            )
            return 0
    except CandidateError as exc:
        print(f"release-candidate: error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
