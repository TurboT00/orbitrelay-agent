"""Contracts for stabilization candidate re-audit (e10s02)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.candidate_reaudit import (
    ReauditError,
    build_default_review,
    calculate_verdict,
    validate_verdict,
)
from scripts.release_evidence import AUTOMATED_GATE_SPECS, GateResult, build_record

REPO_ROOT = Path(__file__).resolve().parents[1]


def _gates(revision: str) -> list[GateResult]:
    return [
        GateResult(
            id=str(spec["id"]),
            category=str(spec["category"]),
            contract=str(spec["contract"]),
            command=[str(p) for p in spec["command"]],  # type: ignore[index]
            status="passed",
            exit_code=0,
            revision=revision,
            environment="macos-automated",
        )
        for spec in AUTOMATED_GATE_SPECS
    ]


class CandidateReauditTests(unittest.TestCase):
    def test_ready_with_acceptance_when_no_open_major(self) -> None:
        revision = "a" * 40
        disposition = {
            "findings": [
                {
                    "id": "MAJ-01",
                    "severity": "major",
                    "status": "fixed",
                    "rationale": "fixed",
                    "residual_risk": "",
                    "release_effect": "none",
                    "evidence_ids": ["e1"],
                },
                {
                    "id": "MIN-05",
                    "severity": "minor",
                    "status": "accepted",
                    "rationale": "ok",
                    "residual_risk": "residual note",
                    "release_effect": "accepted",
                    "evidence_ids": ["e2"],
                },
            ]
        }
        evidence = build_record(revision=revision, gates=_gates(revision))
        review = build_default_review(
            revision=revision, disposition=disposition, release_evidence=evidence
        )
        with patch("scripts.candidate_reaudit._revision_is_ancestor", return_value=True):
            verdict = calculate_verdict(
                revision=revision,
                disposition=disposition,
                release_evidence=evidence,
                review=review,
            )
        self.assertEqual(verdict["verdict"], "READY_WITH_EXPLICIT_ACCEPTANCE")
        validate_verdict(verdict, expected_revision=revision, require_ready=True)

    def test_open_major_is_not_ready(self) -> None:
        revision = "b" * 40
        disposition = {
            "findings": [
                {
                    "id": "MAJ-08",
                    "severity": "major",
                    "status": "open",
                    "rationale": "still open",
                    "residual_risk": "risk",
                    "release_effect": "blocks",
                    "evidence_ids": [],
                }
            ]
        }
        evidence = build_record(revision=revision, gates=_gates(revision))
        review = build_default_review(
            revision=revision, disposition=disposition, release_evidence=evidence
        )
        verdict = calculate_verdict(
            revision=revision,
            disposition=disposition,
            release_evidence=evidence,
            review=review,
        )
        self.assertEqual(verdict["verdict"], "NOT_READY")
        with self.assertRaises(ReauditError):
            validate_verdict(verdict, expected_revision=revision, require_ready=True)

    def test_forbidden_sentinel_rejected(self) -> None:
        revision = "c" * 40
        disposition = {
            "findings": [
                {
                    "id": "MAJ-01",
                    "severity": "major",
                    "status": "fixed",
                    "rationale": "api_key=secret",
                    "residual_risk": "",
                    "release_effect": "none",
                    "evidence_ids": [],
                }
            ]
        }
        evidence = build_record(revision=revision, gates=_gates(revision))
        review = build_default_review(
            revision=revision, disposition=disposition, release_evidence=evidence
        )
        with self.assertRaises(ReauditError):
            calculate_verdict(
                revision=revision,
                disposition=disposition,
                release_evidence=evidence,
                review=review,
            )


if __name__ == "__main__":
    unittest.main()
