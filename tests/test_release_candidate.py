"""Contracts for standalone release candidate production (e10s03)."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.release_candidate import (
    SELECTED_VERSION,
    CandidateError,
    assert_identity_aligned,
    build_candidate_record,
    inspect_wheel_contents,
    produce_candidate,
    read_package_identity,
    validate_candidate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _clean_members() -> list[str]:
    return [
        "orbitrelay/__init__.py",
        "orbitrelay/cli.py",
        "orbitrelay_agent-0.6.0.dist-info/METADATA",
        "orbitrelay_agent-0.6.0.dist-info/RECORD",
        "orbitrelay_agent-0.6.0.dist-info/WHEEL",
        "orbitrelay_agent-0.6.0.dist-info/entry_points.txt",
        "orbitrelay_agent-0.6.0.dist-info/licenses/LICENSE",
    ]


class WheelInspectionTests(unittest.TestCase):
    def test_clean_wheel_members_pass(self) -> None:
        outcome = inspect_wheel_contents(_clean_members())
        self.assertEqual(outcome["status"], "passed")
        self.assertEqual(outcome["forbidden_hits"], [])

    def test_private_review_material_is_rejected(self) -> None:
        members = [*_clean_members(), "orbitrelay/project-review-2026-07-29.md"]
        with self.assertRaisesRegex(CandidateError, "forbidden private material"):
            inspect_wheel_contents(members)

    def test_specs_path_is_rejected(self) -> None:
        members = [*_clean_members(), "specs/verifications/release-evidence.json"]
        with self.assertRaisesRegex(CandidateError, "unexpected non-package|forbidden"):
            inspect_wheel_contents(members)

    def test_tests_directory_is_rejected(self) -> None:
        members = [*_clean_members(), "tests/test_agent.py"]
        with self.assertRaisesRegex(CandidateError, "unexpected non-package|forbidden"):
            inspect_wheel_contents(members)


class IdentityAlignmentTests(unittest.TestCase):
    def test_repo_identity_is_selected_version(self) -> None:
        identity = read_package_identity(REPO_ROOT)
        assert_identity_aligned(identity)
        self.assertEqual(identity["package_version"], SELECTED_VERSION)
        self.assertEqual(identity["module_version"], SELECTED_VERSION)


class CandidateRecordTests(unittest.TestCase):
    def test_record_requires_false_publish_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wheel = Path(tmp) / f"orbitrelay_agent-{SELECTED_VERSION}-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                for name in _clean_members():
                    archive.writestr(name, "x")
            identity = {
                "package_name": "orbitrelay-agent",
                "package_version": SELECTED_VERSION,
                "module_version": SELECTED_VERSION,
            }
            inspection = inspect_wheel_contents(_clean_members())
            smoke = {
                "help": {"status": "passed", "exit_code": 0, "reports_identity": None},
                "version": {
                    "status": "passed",
                    "exit_code": 0,
                    "reports_identity": True,
                },
                "module_version": {
                    "status": "passed",
                    "exit_code": 0,
                    "reports_identity": True,
                },
            }
            upstream = {
                "release_evidence": {"status": "passed", "gates": {"official-check": "passed"}},
                "matrix": {"status": "passed"},
                "audit_verdict": {
                    "status": "passed",
                    "verdict": "READY_WITH_EXPLICIT_ACCEPTANCE",
                },
            }
            record = build_candidate_record(
                revision="a" * 40,
                identity=identity,
                wheel=wheel,
                wheel_members=_clean_members(),
                content_inspection=inspection,
                installed_smoke=smoke,
                upstream=upstream,
                artifact_retained=False,
            )
            self.assertEqual(record["status"], "accepted")
            self.assertFalse(record["publish_authority"]["tag"])
            self.assertFalse(record["publish_authority"]["push"])
            self.assertFalse(record["publish_authority"]["publish"])
            self.assertFalse(record["publish_authority"]["hosted_release"])
            self.assertEqual(record["identity"]["version"], SELECTED_VERSION)

            path = Path(tmp) / "release-candidate.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            validate_candidate(path, expected_revision="a" * 40)

    def test_validate_rejects_publish_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wheel = Path(tmp) / f"orbitrelay_agent-{SELECTED_VERSION}-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                for name in _clean_members():
                    archive.writestr(name, "x")
            identity = {
                "package_name": "orbitrelay-agent",
                "package_version": SELECTED_VERSION,
                "module_version": SELECTED_VERSION,
            }
            inspection = inspect_wheel_contents(_clean_members())
            smoke = {
                "help": {"status": "passed", "exit_code": 0, "reports_identity": None},
                "version": {
                    "status": "passed",
                    "exit_code": 0,
                    "reports_identity": True,
                },
                "module_version": {
                    "status": "passed",
                    "exit_code": 0,
                    "reports_identity": True,
                },
            }
            upstream = {
                "release_evidence": {"status": "passed", "gates": {}},
                "matrix": {"status": "passed"},
                "audit_verdict": {"status": "passed", "verdict": "READY"},
            }
            record = build_candidate_record(
                revision="b" * 40,
                identity=identity,
                wheel=wheel,
                wheel_members=_clean_members(),
                content_inspection=inspection,
                installed_smoke=smoke,
                upstream=upstream,
                artifact_retained=False,
            )
            record["publish_authority"]["publish"] = True
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(CandidateError, "publish_authority.publish"):
                validate_candidate(path)


class ProduceCandidateGuardTests(unittest.TestCase):
    def test_dirty_tree_blocks_official_candidate(self) -> None:
        with (
            patch("scripts.release_candidate.tree_is_clean", return_value=False),
            self.assertRaisesRegex(CandidateError, "dirty"),
        ):
            produce_candidate(require_clean_tree=True)

    def test_identity_drift_blocks_candidate(self) -> None:
        with (
            patch("scripts.release_candidate.tree_is_clean", return_value=True),
            patch(
                "scripts.release_candidate.read_package_identity",
                return_value={
                    "package_name": "orbitrelay-agent",
                    "package_version": "0.5.0",
                    "module_version": "0.5.0",
                },
            ),
            self.assertRaisesRegex(CandidateError, "selected identity"),
        ):
            produce_candidate(require_clean_tree=True)


class TrackedCandidateArtifactTests(unittest.TestCase):
    def test_tracked_candidate_record_is_valid_when_present(self) -> None:
        path = REPO_ROOT / "specs" / "verifications" / "release-candidate.json"
        if not path.is_file():
            self.skipTest("release-candidate.json not produced yet")
        # Allow ancestor revision relative to HEAD.
        validate_candidate(path, expected_revision=None, require_accepted=True)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["identity"]["version"], SELECTED_VERSION)
        self.assertEqual(data["content_inspection"]["status"], "passed")
        self.assertFalse(data["publish_authority"]["tag"])
        self.assertFalse(data["publish_authority"]["publish"])


if __name__ == "__main__":
    unittest.main()
