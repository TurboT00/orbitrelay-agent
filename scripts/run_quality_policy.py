#!/usr/bin/env python3
"""Enforce OrbitRelay risk-based coverage, dependency, and source-security gates.

Each stage is independent and fail-closed. A passing unit suite cannot skip these
gates. Advisory-database unavailability is an explicit failure, not a silent pass.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a locked dev dependency
    yaml = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = REPO_ROOT / "specs" / "quality-policy.yaml"


@dataclass(frozen=True)
class StageResult:
    name: str
    ok: bool
    detail: str


class PolicyError(RuntimeError):
    """Quality policy configuration or execution failure."""


def load_policy(path: Path) -> dict[str, object]:
    if yaml is None:
        raise PolicyError("PyYAML is required to load quality policy")
    if not path.is_file():
        raise PolicyError(f"quality policy not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PolicyError("quality policy root must be a mapping")
    return payload


def _run(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def run_coverage_stage(
    policy: dict[str, object],
    *,
    repo_root: Path,
) -> StageResult:
    tools = policy.get("tools")
    if not isinstance(tools, dict):
        raise PolicyError("quality policy tools must be a mapping")
    coverage_policy = tools.get("coverage")
    if not isinstance(coverage_policy, dict):
        raise PolicyError("coverage policy missing")
    fail_under = coverage_policy.get("fail_under", 80)
    if not isinstance(fail_under, (int, float)):
        raise PolicyError("coverage.fail_under must be a number")
    branch = bool(coverage_policy.get("branch", True))
    source = str(policy.get("source", "orbitrelay"))

    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    with tempfile.TemporaryDirectory(prefix="orbitrelay-cov-") as tmp:
        data_file = str(Path(tmp) / "coverage.dat")
        env["COVERAGE_FILE"] = data_file
        run_argv = [
            "uv",
            "run",
            "coverage",
            "run",
            f"--source={source}",
            "--data-file",
            data_file,
        ]
        if branch:
            run_argv.append("--branch")
        run_argv.extend(["-m", "unittest", "discover", "-s", "tests", "-q"])
        ran = _run(run_argv, cwd=repo_root, env=env)
        if ran.returncode != 0:
            detail = (ran.stdout + ran.stderr).strip()
            return StageResult(
                name="coverage",
                ok=False,
                detail=(
                    detail
                    or f"unit suite failed under coverage (exit {ran.returncode})"
                ),
            )
        report = _run(
            [
                "uv",
                "run",
                "coverage",
                "report",
                f"--fail-under={fail_under:g}",
                "--data-file",
                data_file,
            ],
            cwd=repo_root,
            env=env,
        )
    combined = (report.stdout + report.stderr).strip()
    if report.returncode != 0:
        return StageResult(
            name="coverage",
            ok=False,
            detail=combined or f"coverage failed (exit {report.returncode})",
        )
    total_line = ""
    for line in report.stdout.splitlines():
        if line.startswith("TOTAL"):
            total_line = line.strip()
    return StageResult(
        name="coverage",
        ok=True,
        detail=total_line or "coverage threshold met",
    )


def run_dependency_audit_stage(
    policy: dict[str, object],
    *,
    repo_root: Path,
) -> StageResult:
    tools = policy.get("tools")
    assert isinstance(tools, dict)
    audit_policy = tools.get("dependency_audit")
    if not isinstance(audit_policy, dict):
        raise PolicyError("dependency_audit policy missing")
    fail_on_unavailable = bool(audit_policy.get("fail_on_unavailable", True))

    cache_dir = repo_root / ".cache" / "pip-audit"
    cache_dir.mkdir(parents=True, exist_ok=True)
    completed = _run(
        [
            "uv",
            "run",
            "pip-audit",
            "--progress-spinner",
            "off",
            "--skip-editable",
            "--cache-dir",
            str(cache_dir),
            # Audit the active uv-managed project environment.
            "--format",
            "json",
        ],
        cwd=repo_root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    combined = f"{stdout}\n{stderr}".strip()

    if completed.returncode == 0:
        return StageResult(
            name="dependency_audit",
            ok=True,
            detail="no known vulnerabilities in locked environment",
        )

    unavailable_markers = (
        "unable to",
        "could not",
        "failed to download",
        "network",
        "offline",
        "no such file",
        "connection",
        "temporary failure",
        "name or service not known",
        "cache",
    )
    lowered = combined.lower()
    looks_unavailable = any(marker in lowered for marker in unavailable_markers)

    # pip-audit returns nonzero for vulns; try to parse JSON for a clear count.
    vuln_count = None
    try:
        payload = json.loads(stdout) if stdout else None
        if isinstance(payload, dict) and "dependencies" in payload:
            vuln_count = sum(
                len(dep.get("vulns") or [])
                for dep in payload.get("dependencies", [])
                if isinstance(dep, dict)
            )
        elif isinstance(payload, list):
            vuln_count = sum(
                len(item.get("vulns") or [])
                for item in payload
                if isinstance(item, dict)
            )
    except json.JSONDecodeError:
        vuln_count = None

    if vuln_count is not None and vuln_count > 0:
        return StageResult(
            name="dependency_audit",
            ok=False,
            detail=f"dependency audit found {vuln_count} known vulnerability finding(s)",
        )

    if looks_unavailable and fail_on_unavailable:
        return StageResult(
            name="dependency_audit",
            ok=False,
            detail=(
                "dependency advisory data unavailable; refusing to pass closed. "
                "Restore network/cache access and re-run pip-audit."
            ),
        )

    return StageResult(
        name="dependency_audit",
        ok=False,
        detail=combined or f"dependency audit failed (exit {completed.returncode})",
    )


def run_source_security_stage(
    policy: dict[str, object],
    *,
    repo_root: Path,
) -> StageResult:
    tools = policy.get("tools")
    assert isinstance(tools, dict)
    security = tools.get("source_security")
    if not isinstance(security, dict):
        raise PolicyError("source_security policy missing")
    severity = str(security.get("severity", "medium")).lower()
    confidence = str(security.get("confidence", "medium")).lower()
    paths = security.get("paths", ["src/orbitrelay"])
    if not isinstance(paths, list) or not paths:
        raise PolicyError("source_security.paths must be a non-empty list")

    severity_flag = {
        "low": "-l",
        "medium": "-ll",
        "high": "-lll",
    }.get(severity, "-ll")
    confidence_flag = {
        "low": "-i",
        "medium": "-ii",
        "high": "-iii",
    }.get(confidence, "-ii")

    argv = [
        "uv",
        "run",
        "bandit",
        "-q",
        "-r",
        *[str(path) for path in paths],
        severity_flag,
        confidence_flag,
        "-f",
        "txt",
    ]
    completed = _run(
        argv,
        cwd=repo_root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    combined = (completed.stdout + completed.stderr).strip()
    if completed.returncode == 0:
        return StageResult(
            name="source_security",
            ok=True,
            detail=f"bandit clean at severity>={severity}, confidence>={confidence}",
        )
    # Bandit uses exit 1 when issues found.
    return StageResult(
        name="source_security",
        ok=False,
        detail=combined or f"bandit failed (exit {completed.returncode})",
    )


def run_all_stages(
    *,
    policy_path: Path = DEFAULT_POLICY,
    repo_root: Path = REPO_ROOT,
    stages: Sequence[str] | None = None,
) -> list[StageResult]:
    policy = load_policy(policy_path)
    selected = set(stages) if stages else {"coverage", "dependency_audit", "source_security"}
    results: list[StageResult] = []
    if "coverage" in selected:
        results.append(run_coverage_stage(policy, repo_root=repo_root))
    if "dependency_audit" in selected:
        results.append(run_dependency_audit_stage(policy, repo_root=repo_root))
    if "source_security" in selected:
        results.append(run_source_security_stage(policy, repo_root=repo_root))
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY,
        help="Path to quality-policy.yaml",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=("coverage", "dependency_audit", "source_security"),
        help="Run only the named stage (repeatable)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        results = run_all_stages(
            policy_path=args.policy,
            repo_root=args.repo_root,
            stages=args.only,
        )
    except PolicyError as exc:
        print(f"quality-policy: error: {exc}", file=sys.stderr)
        return 2

    failed = False
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"quality-policy[{result.name}]: {status}: {result.detail}")
        if not result.ok:
            failed = True
            # Print multi-line details for failures when useful.
            if "\n" in result.detail:
                print(result.detail, file=sys.stderr)
    if failed:
        print("quality-policy: one or more stages failed", file=sys.stderr)
        return 1
    print("quality-policy: all stages passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
