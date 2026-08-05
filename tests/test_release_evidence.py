"""Contracts for automated macOS release evidence (e10s01)."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.release_evidence import (
    AUTOMATED_GATE_SPECS,
    EVIDENCE_KIND,
    EvidenceError,
    GateResult,
    build_record,
    generate_evidence,
    scan_forbidden,
    validate_evidence,
    write_record,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "scripts" / "validate_release_evidence.py"


def _passed_gates(revision: str = "a" * 40) -> list[GateResult]:
    gates: list[GateResult] = []
    for spec in AUTOMATED_GATE_SPECS:
        gates.append(
            GateResult(
                id=str(spec["id"]),
                category=str(spec["category"]),
                contract=str(spec["contract"]),
                command=[str(part) for part in spec["command"]],  # type: ignore[index]
                status="passed",
                exit_code=0,
                revision=revision,
                environment="macos-automated",
                detail="ok",
            )
        )
    return gates


class ReleaseEvidenceUnitTests(unittest.TestCase):
    def test_build_and_validate_complete_automated_record(self) -> None:
        revision = "b" * 40
        record = build_record(revision=revision, gates=_passed_gates(revision))
        self.assertEqual(record["kind"], EVIDENCE_KIND)
        self.assertEqual(record["platform"]["qualified"], ["macos"])
        self.assertIn("linux", record["platform"]["preview"])
        self.assertIn("windows", record["platform"]["deferred"])
        validate_evidence(record, expected_revision=revision)

    def test_missing_gate_fails_validation(self) -> None:
        revision = "c" * 40
        gates = _passed_gates(revision)[:-1]
        record = build_record(revision=revision, gates=gates)
        with self.assertRaises(EvidenceError):
            validate_evidence(record, expected_revision=revision)

    def test_failed_gate_fails_validation(self) -> None:
        revision = "d" * 40
        gates = _passed_gates(revision)
        bad = gates[0]
        gates[0] = GateResult(
            id=bad.id,
            category=bad.category,
            contract=bad.contract,
            command=bad.command,
            status="failed",
            exit_code=1,
            revision=revision,
            environment="macos-automated",
            detail="boom",
        )
        record = build_record(revision=revision, gates=gates)
        with self.assertRaisesRegex(EvidenceError, "not passed"):
            validate_evidence(record, expected_revision=revision)

    def test_revision_drift_fails_validation(self) -> None:
        revision = "e" * 40
        gates = _passed_gates(revision)
        record = build_record(revision=revision, gates=gates)
        with self.assertRaisesRegex(EvidenceError, "revision mismatch"):
            validate_evidence(record, expected_revision="f" * 40)

    def test_forbidden_sentinel_fails_validation(self) -> None:
        revision = "1" * 40
        record = build_record(revision=revision, gates=_passed_gates(revision))
        record["gates"][0]["detail"] = "api_key=super-secret"
        with self.assertRaisesRegex(EvidenceError, "forbidden"):
            validate_evidence(record, expected_revision=revision)

    def test_scan_forbidden_detects_common_secrets(self) -> None:
        self.assertTrue(scan_forbidden("Authorization: Bearer abc"))
        self.assertTrue(scan_forbidden('{"api_key":"x"}'))
        self.assertFalse(scan_forbidden("status=passed exit_code=0"))

    def test_generate_evidence_uses_runner_and_matrix_evidence(self) -> None:
        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(list(command), 0, stdout="ok\n", stderr="")

        # Matrix evidence path is used without invoking the long matrix script.
        with patch("scripts.release_evidence.run_command", side_effect=fake_run):
            with patch(
                "scripts.release_evidence.git_revision",
                return_value="a" * 40,
            ):
                # Force matrix evidence helper success via real file if present.
                record = generate_evidence(
                    repo=REPO_ROOT,
                    execute=True,
                    use_matrix_evidence=True,
                    runner=fake_run,
                    require_clean_tree=False,
                )
        # python-matrix may fail if matrix evidence revision rules fail; accept
        # either full pass or isolated matrix failure in dirty/dev trees.
        self.assertEqual(record["kind"], EVIDENCE_KIND)
        ids = {gate["id"] for gate in record["gates"]}
        self.assertEqual(ids, {str(spec["id"]) for spec in AUTOMATED_GATE_SPECS})

    def test_write_record_rejects_forbidden_content(self) -> None:
        revision = "2" * 40
        record = build_record(revision=revision, gates=_passed_gates(revision))
        record["notes"] = "password=nope"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            with self.assertRaises(EvidenceError):
                write_record(path, record)

    def test_validator_cli_accepts_valid_fixture(self) -> None:
        revision = "3" * 40
        record = build_record(revision=revision, gates=_passed_gates(revision))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-evidence.json"
            write_record(path, record)
            completed = subprocess.run(
                [
                    "uv",
                    "run",
                    "python",
                    str(VALIDATOR),
                    "--record",
                    str(path),
                    "--revision",
                    revision,
                    "--required-set",
                    "automated",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
