"""Validate the tracked, secret-free release-baseline disposition contract."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ASSESSED_REVISION = "077f5f56781aa1828015f57f1292c0c990912c9a"
EXPECTED_CONTRACT_SHA256 = "3d891be4a71a5e00526b6488db6a87d1c555008aaea611af015f9e6db929f464"
CANONICAL_FINDING_IDS = tuple(
    [f"MAJ-{number:02d}" for number in range(1, 9)]
    + [f"MED-{number:02d}" for number in range(1, 12)]
    + [f"MIN-{number:02d}" for number in range(1, 8)]
)
ALLOWED_STATUSES = {"fixed", "open", "accepted", "deferred"}
ALLOWED_EVIDENCE_OUTCOMES = {"observed", "passed"}
APPROVED_PASSED_COMMANDS = {
    "uv run python -m unittest tests.test_streaming tests.test_run_summary tests.test_connection_service tests.test_provider_cli -v",
    "uv run python -m unittest tests.test_release_identity -v",
    "uv run python -m unittest tests.test_workspace_privacy -v",
    "uv run python -m unittest tests.test_cli_errors -v",
    "uv run python -m unittest tests.test_provider_cli tests.test_connection_service -v",
    "uv run python -m unittest tests.test_codex_bridge tests.test_provider_cli -v",
        "uv run python -m unittest tests.test_session_concurrency tests.test_session_transactions -v",
    "uvx --offline --from ruff==0.16.1 ruff check . --select F401,F841",
    "uv run ruff check .",
    "uv run mypy src/orbitrelay",
}
ALLOWED_EVIDENCE_KINDS = {
    "lock-and-gate-review",
    "offline-lint-run",
    "package-metadata-review",
    "quality-gate-review",
    "release-behavior-review",
    "source-and-gate-review",
    "source-and-scope-review",
    "source-and-test-review",
    "source-and-test-run",
    "source-review",
}
EXPECTED_FINDING_STATUSES = {
    "MAJ-01": "fixed",
    "MAJ-02": "fixed",
    "MAJ-03": "fixed",
    "MAJ-04": "fixed",
    "MAJ-05": "fixed",
    "MAJ-06": "fixed",
    "MAJ-07": "fixed",
    "MAJ-08": "open",
    "MED-01": "open",
    "MED-02": "open",
    "MED-03": "fixed",
    "MED-04": "open",
    "MED-05": "open",
    "MED-06": "open",
    "MED-07": "fixed",
    "MED-08": "open",
    "MED-09": "deferred",
    "MED-10": "fixed",
    "MED-11": "deferred",
    "MIN-01": "fixed",
    "MIN-02": "open",
    "MIN-03": "open",
    "MIN-04": "fixed",
    "MIN-05": "accepted",
    "MIN-06": "open",
    "MIN-07": "open",
}
PRIVATE_RECORD_NAMES = {
    "project-review-2026-07-29.md",
    "remediation-plan-2026-07-29.md",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\b(?:sk|pk|ghp|glpat)-[a-z0-9_-]{12,}"),
    re.compile(r"\bAKIA[A-Z0-9]{12,}\b"),
    re.compile(r"(?:^|[\s(])(?:/Users/|/home/|[A-Za-z]:\\Users\\)"),
)
SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(?:[a-z0-9_]*(?:api[_-]?key|access[_-]?token)|password|private[_-]?payload|"
    r"account[_-]?data|request[_-]?id)\s*[:=]\s*[^,\s}\]]{4,}"
)
TOP_LEVEL_FIELDS = {
    "schema_version",
    "story_id",
    "assessment",
    "summary",
    "evidence",
    "findings",
    "release_version",
}


class ContractError(ValueError):
    """Raised when the release-baseline contract is incomplete or unsafe."""


def contract_path() -> Path:
    return ROOT / "specs" / "verifications" / "current-finding-disposition.json"


def load_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load release-baseline contract: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError("release-baseline contract must be a JSON object")
    return value


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be non-empty text")
    return value


def _require_unique(items: list[dict[str, Any]], key: str, label: str) -> None:
    values = [item.get(key) for item in items]
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ContractError(f"duplicate {label}: {', '.join(str(value) for value in duplicates)}")


def _require_fields(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ContractError(f"unknown {label} fields: {', '.join(unknown)}")


def _validate_assessment(contract: dict[str, Any]) -> str:
    _require_fields(contract, TOP_LEVEL_FIELDS, "contract")
    if contract.get("schema_version") != 1 or contract.get("story_id") != "e05s01":
        raise ContractError("unsupported release-baseline schema or story")
    assessment = contract.get("assessment")
    if not isinstance(assessment, dict):
        raise ContractError("assessment must be an object")
    _require_fields(
        assessment,
        {"revision", "date", "tree_state", "registry", "registry_visibility", "publication", "official_check"},
        "assessment",
    )
    revision = _require_text(assessment.get("revision"), "assessment.revision")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ContractError("assessment.revision must be a full lowercase Git SHA")
    if revision != ASSESSED_REVISION:
        raise ContractError("unexpected assessed revision for the published e05s01 contract")
    if assessment.get("tree_state") != "clean":
        raise ContractError("assessment must record a clean source tree")
    if assessment.get("registry") != "july-review-2026-07-29":
        raise ContractError("assessment must identify the canonical July registry")
    commit = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if commit.returncode != 0:
        raise ContractError("assessed revision does not exist in this repository")
    official_check = assessment.get("official_check")
    if not isinstance(official_check, dict):
        raise ContractError("assessment.official_check must be an object")
    _require_fields(official_check, {"command", "exit_code", "project_tests", "example_tests"}, "official check")
    if official_check.get("command") != "./scripts/check.sh" or official_check.get("exit_code") != 0:
        raise ContractError("official check must record a successful exact command")
    return revision


def _validate_evidence(contract: dict[str, Any], revision: str) -> dict[str, dict[str, Any]]:
    evidence = contract.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ContractError("evidence must be a non-empty list")
    if not all(isinstance(item, dict) for item in evidence):
        raise ContractError("every evidence item must be an object")
    _require_unique(evidence, "id", "evidence id")
    by_id: dict[str, dict[str, Any]] = {}
    for item in evidence:
        _require_fields(item, {"id", "kind", "revision", "outcome", "command", "exit_code", "references"}, "evidence")
        evidence_id = _require_text(item.get("id"), "evidence.id")
        kind = _require_text(item.get("kind"), f"evidence {evidence_id} kind")
        if kind not in ALLOWED_EVIDENCE_KINDS:
            raise ContractError(f"invalid evidence kind for {evidence_id}")
        if item.get("outcome") not in ALLOWED_EVIDENCE_OUTCOMES:
            raise ContractError(f"invalid evidence outcome for {evidence_id}")
        if item.get("revision") != revision:
            raise ContractError(f"stale evidence for {evidence_id}")
        if item.get("outcome") == "passed":
            command = _require_text(item.get("command"), f"passed evidence {evidence_id} command")
            if command not in APPROVED_PASSED_COMMANDS:
                raise ContractError(f"unapproved passed evidence command for {evidence_id}")
            if item.get("exit_code") != 0:
                raise ContractError(f"passed evidence {evidence_id} needs exit code zero")
        references = item.get("references")
        if not isinstance(references, list) or not references:
            raise ContractError(f"evidence {evidence_id} needs repository references")
        for reference in references:
            if not isinstance(reference, dict):
                raise ContractError(f"evidence {evidence_id} has an invalid reference")
            _require_fields(reference, {"path", "locator"}, "evidence reference")
            path_text = _require_text(reference.get("path"), f"evidence {evidence_id} path")
            path = Path(path_text)
            if path.is_absolute() or ".." in path.parts or not (ROOT / path).is_file():
                raise ContractError(f"evidence {evidence_id} path is not a repository file: {path_text}")
            _require_text(reference.get("locator"), f"evidence {evidence_id} locator")
            at_revision = subprocess.run(
                ["git", "cat-file", "-e", f"{revision}:{path.as_posix()}"],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if at_revision.returncode != 0:
                raise ContractError(f"evidence path is absent at assessed revision: {path_text}")
            changed = subprocess.run(
                ["git", "diff", "--quiet", revision, "--", path.as_posix()],
                cwd=ROOT,
                check=False,
            )
            if changed.returncode != 0:
                raise ContractError(f"stale evidence path changed after assessment: {path_text}")
        by_id[evidence_id] = item
    return by_id


def _validate_findings(contract: dict[str, Any], evidence: dict[str, dict[str, Any]]) -> None:
    findings = contract.get("findings")
    if not isinstance(findings, list) or not all(isinstance(item, dict) for item in findings):
        raise ContractError("findings must be a list of objects")
    _require_unique(findings, "id", "finding")
    finding_ids = [item.get("id") for item in findings]
    if set(finding_ids) != set(CANONICAL_FINDING_IDS) or len(finding_ids) != len(CANONICAL_FINDING_IDS):
        raise ContractError("finding registry mismatch")
    represented_statuses: set[str] = set()
    for finding in findings:
        _require_fields(
            finding,
            {"id", "severity", "title", "status", "evidence_ids", "rationale", "release_effect", "owner", "residual_risk"},
            "finding",
        )
        finding_id = str(finding["id"])
        status = finding.get("status")
        if status not in ALLOWED_STATUSES:
            raise ContractError(f"invalid status for {finding_id}")
        if status != EXPECTED_FINDING_STATUSES[finding_id]:
            raise ContractError(f"unexpected disposition for {finding_id}")
        represented_statuses.add(status)
        for field in ("severity", "title", "rationale", "release_effect", "owner", "residual_risk"):
            _require_text(finding.get(field), f"{finding_id}.{field}")
        evidence_ids = finding.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise ContractError(f"{finding_id} must reference current evidence")
        if any(evidence_id not in evidence for evidence_id in evidence_ids):
            raise ContractError(f"{finding_id} references unknown evidence")
        if status == "fixed" and not any(evidence[evidence_id]["outcome"] == "passed" for evidence_id in evidence_ids):
            raise ContractError(f"fixed finding {finding_id} lacks passed current evidence")
    if represented_statuses != ALLOWED_STATUSES:
        raise ContractError("the publication must contain fixed, open, accepted, and deferred outcomes")


def _validate_summary(contract: dict[str, Any]) -> None:
    summary = contract.get("summary")
    if not isinstance(summary, dict):
        raise ContractError("summary must be an object")
    _require_fields(summary, {"counts", "release_blockers"}, "summary")
    findings = contract["findings"]
    expected_counts = {status: sum(item["status"] == status for item in findings) for status in sorted(ALLOWED_STATUSES)}
    if summary.get("counts") != expected_counts:
        raise ContractError("summary disposition counts do not match findings")
    expected_blockers = sorted(item["id"] for item in findings if item["status"] == "open")
    if summary.get("release_blockers") != expected_blockers:
        raise ContractError("summary release blockers do not match open findings")
def _validate_release_checkpoint(contract: dict[str, Any]) -> None:
    release = contract.get("release_version")
    if not isinstance(release, dict):
        raise ContractError("release_version must be an object")
    _require_fields(release, {"state", "selected", "implications"}, "release version")
    if release.get("state") != "selected":
        raise ContractError("release version must record the selected stabilization identity")
    if release.get("selected") != "0.6.0":
        raise ContractError("release version must remain the approved 0.6.0 identity")
    implications = release.get("implications")
    if not isinstance(implications, list) or not implications:
        raise ContractError("release version implications must be recorded")
    for index, implication in enumerate(implications):
        _require_text(implication, f"release implication {index}")


def _validate_secret_free(contract: dict[str, Any]) -> None:
    serialized = json.dumps(contract, sort_keys=True)
    if any(name in serialized for name in PRIVATE_RECORD_NAMES):
        raise ContractError("private local review filenames must not be published")
    for pattern in SECRET_PATTERNS:
        if pattern.search(serialized):
            raise ContractError("secret-bearing value found in release-baseline contract")
    normalized = serialized.replace("\\", "").replace('"', "")
    if SENSITIVE_ASSIGNMENT.search(normalized):
        raise ContractError("secret-bearing or private payload found in release-baseline contract")


def _validate_contract_digest(contract: dict[str, Any]) -> None:
    canonical = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != EXPECTED_CONTRACT_SHA256:
        raise ContractError("contract content does not match the reviewed e05s01 publication")


def validate_contract(contract: dict[str, Any]) -> None:
    _validate_secret_free(contract)
    revision = _validate_assessment(contract)
    evidence = _validate_evidence(contract, revision)
    _validate_findings(contract, evidence)
    _validate_summary(contract)
    _validate_release_checkpoint(contract)
    _validate_contract_digest(contract)


def main() -> int:
    contract = load_contract(contract_path())
    validate_contract(contract)
    counts = contract["summary"]["counts"]
    count_text = ", ".join(f"{status}={counts[status]}" for status in sorted(counts))
    blockers = ", ".join(contract["summary"]["release_blockers"])
    print(f"release-baseline contract passed: {len(contract['findings'])} findings ({count_text})")
    print(f"release blockers: {blockers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
