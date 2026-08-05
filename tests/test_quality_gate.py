"""Contracts for risk-based coverage/dependency/source-security gates (e09s02)."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check.sh"
POLICY_SCRIPT = REPO_ROOT / "scripts" / "run_quality_policy.py"
POLICY_FILE = REPO_ROOT / "specs" / "quality-policy.yaml"


class QualityPolicyConfigurationTests(unittest.TestCase):
    def test_policy_file_defines_measured_thresholds_and_tools(self) -> None:
        payload = yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 1)
        tools = payload["tools"]
        self.assertGreaterEqual(tools["coverage"]["fail_under"], 80)
        self.assertTrue(tools["coverage"]["branch"])
        self.assertTrue(tools["dependency_audit"]["fail_on_unavailable"])
        self.assertTrue(tools["dependency_audit"]["fail_on_vuln"])
        self.assertEqual(tools["source_security"]["severity"], "medium")
        self.assertIn("src/orbitrelay", tools["source_security"]["paths"])

    def test_check_script_runs_quality_policy_as_named_stage(self) -> None:
        text = CHECK_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('section "Running risk-based quality policy"', text)
        self.assertIn("uv run python scripts/run_quality_policy.py", text)
        self.assertNotIn("run_quality_policy.py || true", text)
        # Unit suite is owned by the coverage stage (no silent skip).
        policy_src = Path(REPO_ROOT, "scripts/run_quality_policy.py").read_text(encoding="utf-8")
        self.assertIn('"unittest"', policy_src)
        self.assertIn('"discover"', policy_src)

    def test_check_script_is_executable(self) -> None:
        mode = CHECK_SCRIPT.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)

    def test_dev_dependencies_lock_quality_tools(self) -> None:
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("coverage", text)
        self.assertIn("pip-audit", text)
        self.assertIn("bandit", text)
        self.assertIn("fail_under = 80", text)


class QualityPolicyRegressionTests(unittest.TestCase):
    def test_coverage_stage_fails_below_threshold_independently(self) -> None:
        from scripts.run_quality_policy import run_coverage_stage

        policy = yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8"))
        policy["tools"]["coverage"]["fail_under"] = 99.9

        def fake_run(argv, **kwargs):
            parts = [str(part) for part in argv]
            if "run" in parts and "report" not in parts and "coverage" in parts:
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
            if "report" in parts and "coverage" in parts:
                return subprocess.CompletedProcess(
                    argv,
                    2,
                    stdout="TOTAL 100 50 50 10 50%\n",
                    stderr="Coverage failure: total of 50 is less than fail-under=99.9\n",
                )
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with patch("scripts.run_quality_policy._run", side_effect=fake_run):
            result = run_coverage_stage(policy, repo_root=REPO_ROOT)
        self.assertFalse(result.ok)
        self.assertEqual(result.name, "coverage")
        self.assertTrue(
            "fail" in result.detail.lower() or "50" in result.detail,
            result.detail,
        )

    def test_coverage_stage_fails_when_unit_suite_fails(self) -> None:
        from scripts.run_quality_policy import run_coverage_stage

        policy = yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8"))

        def fake_run(argv, **kwargs):
            joined = " ".join(str(part) for part in argv)
            if "unittest" in joined:
                return subprocess.CompletedProcess(
                    argv, 1, stdout="FAILED (failures=1)\n", stderr=""
                )
            return subprocess.CompletedProcess(argv, 0, stdout="TOTAL 100%", stderr="")

        with patch("scripts.run_quality_policy._run", side_effect=fake_run):
            result = run_coverage_stage(policy, repo_root=REPO_ROOT)
        self.assertFalse(result.ok)
        self.assertIn("fail", result.detail.lower())

    def test_dependency_audit_fails_closed_when_advisory_unavailable(self) -> None:
        from scripts.run_quality_policy import StageResult, run_dependency_audit_stage

        policy = yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8"))

        def fake_run(argv, **kwargs):
            return subprocess.CompletedProcess(
                args=list(argv),
                returncode=2,
                stdout="",
                stderr="ERROR: could not download vulnerability database: network unreachable",
            )

        with patch("scripts.run_quality_policy._run", side_effect=fake_run):
            result = run_dependency_audit_stage(policy, repo_root=REPO_ROOT)
        self.assertIsInstance(result, StageResult)
        self.assertFalse(result.ok)
        self.assertIn("unavailable", result.detail.lower())

    def test_dependency_audit_fails_on_known_vulnerability_payload(self) -> None:
        import json

        from scripts.run_quality_policy import run_dependency_audit_stage

        policy = yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8"))
        payload = {
            "dependencies": [
                {
                    "name": "example",
                    "version": "1.0.0",
                    "vulns": [{"id": "VULN-1", "description": "demo"}],
                }
            ]
        }

        def fake_run(argv, **kwargs):
            return subprocess.CompletedProcess(
                args=list(argv),
                returncode=1,
                stdout=json.dumps(payload),
                stderr="",
            )

        with patch("scripts.run_quality_policy._run", side_effect=fake_run):
            result = run_dependency_audit_stage(policy, repo_root=REPO_ROOT)
        self.assertFalse(result.ok)
        self.assertIn("1 known vulnerability", result.detail)

    def test_source_security_fails_on_controlled_bandit_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "bad_security.py"
            fixture.write_text(
                "import subprocess\n"
                "def run(cmd: str) -> None:\n"
                "    subprocess.call(cmd, shell=True)\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    "uv",
                    "run",
                    "bandit",
                    "-q",
                    "-r",
                    str(fixture),
                    "-ll",
                    "-ii",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        combined = (completed.stdout + completed.stderr).lower()
        self.assertTrue(
            "shell" in combined or "b602" in combined or "issue" in combined,
            combined,
        )

    def test_cli_returns_nonzero_when_only_one_stage_fails(self) -> None:
        """A single failed stage fails the process even if other stages would pass."""
        from scripts import run_quality_policy as qp

        def fake_all(**kwargs):
            return [
                qp.StageResult("coverage", True, "ok"),
                qp.StageResult("dependency_audit", False, "unavailable"),
                qp.StageResult("source_security", True, "ok"),
            ]

        with patch.object(qp, "run_all_stages", side_effect=fake_all):
            code = qp.main([])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
