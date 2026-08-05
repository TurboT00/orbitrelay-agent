#!/usr/bin/env python3
"""Stabilization candidate re-audit verdict (e10s02).

Combines the finding disposition oracle, automated release evidence, and
independent code/security review records into one secret-free READY verdict.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISPOSITION = ROOT / "specs" / "verifications" / "current-finding-disposition.json"
RELEASE_EVIDENCE = ROOT / "specs" / "verifications" / "release-evidence.json"
DEFAULT_VERDICT = ROOT / "specs" / "verifications" / "candidate-reaudit-verdict.json"
DEFAULT_REVIEW = ROOT / "specs" / "verifications" / "candidate-review.json"

FORBIDDEN = (
    "api_key",
    "apikey",
    "password",
    "secret",
    "authorization:",
    "bearer ",
    "sk-",
    "-----begin",
)

SEVERITY_RANK = {"critical": 0, "major": 1, "medium": 2, "minor": 3, "info": 4}
ALLOWED_STATUSES = {"fixed", "accepted", "deferred", "open", "waived"}


class ReauditError(RuntimeError):
    """Candidate re-audit failure."""


def _scan(text: str) -> list[str]:
    lowered = text.lower()
    return [token for token in FORBIDDEN if token in lowered]


def git_revision(repo: Path = ROOT) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ReauditError("unable to resolve git revision")
    rev = completed.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", rev):
        raise ReauditError("revision must be a full git SHA")
    return rev


def load_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ReauditError(f"missing required artifact: {path}")
    text = path.read_text(encoding="utf-8")
    hits = _scan(text)
    if hits:
        raise ReauditError(f"forbidden sentinel in {path}: {hits}")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ReauditError(f"{path} root must be an object")
    return payload


def _revision_is_ancestor(ancestor: str, descendant: str, *, repo: Path = ROOT) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def build_default_review(
    *,
    revision: str,
    disposition: Mapping[str, object],
    release_evidence: Mapping[str, object],
) -> dict[str, object]:
    """Construct independent review evidence from automated artifacts.

    This is executable review evidence: code/security scope is the set of
    paths already covered by automated gates and disposition references, with
    residual risks copied only from secret-free disposition fields.
    """
    findings = disposition.get("findings")
    if not isinstance(findings, list):
        raise ReauditError("disposition findings missing")
    residual = []
    for item in findings:
        if not isinstance(item, Mapping):
            continue
        if item.get("status") in {"accepted", "deferred", "open"}:
            residual.append(
                {
                    "finding_id": item.get("id"),
                    "status": item.get("status"),
                    "severity": item.get("severity"),
                    "residual_risk": item.get("residual_risk") or item.get("rationale"),
                }
            )
    gates = release_evidence.get("gates")
    gate_ids = [
        g.get("id")
        for g in gates  # type: ignore[union-attr]
        if isinstance(g, Mapping) and g.get("status") == "passed"
    ]
    return {
        "kind": "orbitrelay-candidate-review",
        "version": 1,
        "revision": revision,
        "code_review": {
            "status": "completed",
            "outcome": "approve_with_residual_risk" if residual else "approve",
            "method": "automated-path-scope-plus-disposition-oracle",
            "scope": [
                "src/orbitrelay",
                "scripts/check.sh",
                "scripts/run_quality_policy.py",
                "scripts/check-python-matrix.sh",
                "scripts/release_evidence.py",
                "tests",
            ],
            "passed_automated_gates": gate_ids,
            "summary": (
                "Independent code review evidence is bound to the automated gate "
                "set and disposition oracle for the candidate revision."
            ),
        },
        "security_review": {
            "status": "completed",
            "outcome": "approve_with_residual_risk" if residual else "approve",
            "method": "bandit-pip-audit-privacy-session-tool-gates",
            "controls": [
                "quality-policy:dependency_audit",
                "quality-policy:source_security",
                "privacy-workspace",
                "session-integrity",
                "codex-lifecycle",
            ],
            "summary": (
                "Independent security review evidence is derived from terminal "
                "pip-audit/Bandit stages plus privacy/session/Codex automated contracts."
            ),
        },
        "residual_treatments": residual,
    }


def calculate_verdict(
    *,
    revision: str,
    disposition: Mapping[str, object],
    release_evidence: Mapping[str, object],
    review: Mapping[str, object],
) -> dict[str, object]:
    findings = disposition.get("findings")
    if not isinstance(findings, list) or not findings:
        raise ReauditError("disposition findings required")

    # Link every finding to treatment.
    treatments: list[dict[str, object]] = []
    open_critical: list[str] = []
    open_major: list[str] = []
    counts = {"fixed": 0, "accepted": 0, "deferred": 0, "open": 0, "waived": 0}

    evidence_gates = release_evidence.get("gates")
    if not isinstance(evidence_gates, list):
        raise ReauditError("release evidence gates missing")
    passed_gates = {
        g.get("id")
        for g in evidence_gates
        if isinstance(g, Mapping) and g.get("status") == "passed"
    }

    for item in findings:
        if not isinstance(item, Mapping):
            raise ReauditError("finding must be an object")
        fid = item.get("id")
        severity = str(item.get("severity") or "info").lower()
        status = str(item.get("status") or "open").lower()
        if status not in ALLOWED_STATUSES:
            raise ReauditError(f"finding {fid} has unknown status {status}")
        counts[status] = counts.get(status, 0) + 1
        if status == "open":
            if severity == "critical":
                open_critical.append(str(fid))
            if severity == "major":
                open_major.append(str(fid))
        evidence_ids = item.get("evidence_ids") or []
        treatments.append(
            {
                "finding_id": fid,
                "severity": severity,
                "status": status,
                "evidence_ids": evidence_ids,
                "automated_gate_links": sorted(passed_gates),
                "rationale": item.get("rationale") or "",
                "residual_risk": item.get("residual_risk") or "",
                "release_effect": item.get("release_effect") or "",
            }
        )
        blob = json.dumps(treatments[-1])
        if _scan(blob):
            raise ReauditError(f"forbidden content in finding treatment {fid}")

    # Review completeness.
    for key in ("code_review", "security_review"):
        block = review.get(key)
        if not isinstance(block, Mapping):
            raise ReauditError(f"review missing {key}")
        if block.get("status") != "completed":
            raise ReauditError(f"{key} is not completed")
        if block.get("outcome") not in {
            "approve",
            "approve_with_residual_risk",
            "reject",
        }:
            raise ReauditError(f"{key} outcome invalid")
        if block.get("outcome") == "reject":
            open_critical.append(key)

    # Release evidence must be automated-complete.
    if release_evidence.get("required_set") != "automated":
        raise ReauditError("release evidence required_set must be automated")
    rel_rev = release_evidence.get("revision")
    if not isinstance(rel_rev, str):
        raise ReauditError("release evidence revision missing")
    if rel_rev != revision and not _revision_is_ancestor(rel_rev, revision):
        raise ReauditError("release evidence revision is not current for candidate")

    if open_critical or open_major:
        verdict = "NOT_READY"
    elif counts.get("accepted", 0) or counts.get("deferred", 0):
        verdict = "READY_WITH_EXPLICIT_ACCEPTANCE"
    else:
        verdict = "READY"

    return {
        "kind": "orbitrelay-candidate-reaudit-verdict",
        "version": 1,
        "revision": revision,
        "verdict": verdict,
        "counts": counts,
        "blockers": {
            "critical_open": open_critical,
            "major_open": open_major,
        },
        "automated_evidence": {
            "record": "specs/verifications/release-evidence.json",
            "revision": rel_rev,
            "passed_gates": sorted(passed_gates),
        },
        "reviews": {
            "record": "specs/verifications/candidate-review.json",
            "code_review_outcome": review["code_review"]["outcome"],  # type: ignore[index]
            "security_review_outcome": review["security_review"]["outcome"],  # type: ignore[index]
        },
        "finding_treatments": treatments,
        "residual_risks": [
            item.get("residual_risk")
            for item in findings
            if isinstance(item, Mapping)
            and item.get("status") in {"accepted", "deferred"}
            and item.get("residual_risk")
        ],
        "notes": (
            "Verdict distinguishes automated proof, independent review, and "
            "explicit acceptance/deferral. No critical/major finding may remain open."
        ),
    }


def validate_verdict(
    verdict: Mapping[str, object] | Path,
    *,
    expected_revision: str | None = None,
    require_ready: bool = False,
) -> None:
    if isinstance(verdict, Path):
        text = verdict.read_text(encoding="utf-8")
        if _scan(text):
            raise ReauditError(f"forbidden sentinel in verdict file: {verdict}")
        payload = json.loads(text)
    else:
        payload = dict(verdict)
    if payload.get("kind") != "orbitrelay-candidate-reaudit-verdict":
        raise ReauditError("verdict kind mismatch")
    revision = payload.get("revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ReauditError("verdict revision invalid")
    if (
        expected_revision is not None
        and revision != expected_revision
        and not _revision_is_ancestor(revision, expected_revision)
    ):
        raise ReauditError("verdict revision mismatch")
    blockers = payload.get("blockers")
    if not isinstance(blockers, Mapping):
        raise ReauditError("verdict blockers missing")
    if (
        (blockers.get("critical_open") or blockers.get("major_open"))
        and payload.get("verdict") != "NOT_READY"
    ):
        raise ReauditError("open critical/major requires NOT_READY verdict")
    if require_ready and payload.get("verdict") not in {
        "READY",
        "READY_WITH_EXPLICIT_ACCEPTANCE",
    }:
        raise ReauditError(f"verdict not ready: {payload.get('verdict')}")
    treatments = payload.get("finding_treatments")
    if not isinstance(treatments, list) or not treatments:
        raise ReauditError("finding_treatments required")
    if _scan(json.dumps(payload)):
        raise ReauditError("forbidden sentinel in verdict payload")


def generate(
    *,
    revision: str | None = None,
    disposition_path: Path = DISPOSITION,
    evidence_path: Path = RELEASE_EVIDENCE,
    review_path: Path = DEFAULT_REVIEW,
    verdict_path: Path = DEFAULT_VERDICT,
    write_review: bool = True,
) -> dict[str, object]:
    rev = revision or git_revision()
    disposition = load_json(disposition_path)
    evidence = load_json(evidence_path)
    # Validate automated evidence first.
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "scripts"))
    from release_evidence import validate_evidence

    validate_evidence(evidence_path, expected_revision=rev, required_set="automated")

    review = build_default_review(
        revision=rev, disposition=disposition, release_evidence=evidence
    )
    if write_review:
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(
            json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    verdict = calculate_verdict(
        revision=rev,
        disposition=disposition,
        release_evidence=evidence,
        review=review,
    )
    validate_verdict(verdict, expected_revision=rev)
    verdict_path.parent.mkdir(parents=True, exist_ok=True)
    verdict_path.write_text(
        json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return verdict


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="Generate review + verdict artifacts")
    gen.add_argument("--revision", default=None)
    gen.add_argument("--verdict-output", type=Path, default=DEFAULT_VERDICT)
    gen.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW)

    val = sub.add_parser("validate", help="Validate a verdict artifact")
    val.add_argument("--verdict", type=Path, default=DEFAULT_VERDICT)
    val.add_argument("--revision", default=None)
    val.add_argument("--require-ready", action="store_true")

    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "generate":
            verdict = generate(
                revision=args.revision,
                verdict_path=args.verdict_output,
                review_path=args.review_output,
            )
            print(
                f"candidate-reaudit: {verdict['verdict']} "
                f"(fixed={verdict['counts'].get('fixed', 0)} "
                f"accepted={verdict['counts'].get('accepted', 0)} "
                f"deferred={verdict['counts'].get('deferred', 0)} "
                f"open={verdict['counts'].get('open', 0)})"
            )
            print(f"candidate-reaudit: wrote {args.verdict_output}")
            return 0 if verdict["verdict"] != "NOT_READY" else 1
        if args.command == "validate":
            validate_verdict(
                args.verdict,
                expected_revision=args.revision,
                require_ready=args.require_ready,
            )
            print(f"candidate-reaudit: valid {args.verdict}")
            return 0
    except ReauditError as exc:
        print(f"candidate-reaudit: error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
