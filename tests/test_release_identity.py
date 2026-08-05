"""Contracts for reproducible post-0.5.0 release identity (e05s02)."""

from __future__ import annotations

import io
import os
import re
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
SELECTED_VERSION = "0.6.0"
PACKAGE_NAME = "orbitrelay-agent"


def _read_pyproject_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = data["project"]["version"]
    if not isinstance(version, str) or not version.strip():
        raise AssertionError("pyproject.toml project.version must be non-empty text")
    return version


def _read_release_plan_version() -> str:
    text = (REPO_ROOT / "specs" / "release-plan.yaml").read_text(encoding="utf-8")
    match = re.search(r'^release:\n(?:.*\n)*?  version: "([^"]+)"', text, re.M)
    if match is None:
        # simpler line scan
        in_release = False
        for line in text.splitlines():
            if line.startswith("release:"):
                in_release = True
                continue
            if in_release and line.startswith("  version:"):
                value = line.split(":", 1)[1].strip().strip('"').strip("'")
                return value
            if in_release and line and not line.startswith(" "):
                break
        raise AssertionError("release-plan version not found")
    return match.group(1)


def _read_state_next_target() -> str:
    text = (REPO_ROOT / "specs" / "state.yaml").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().startswith("next_target:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("state.yaml next_target not found")


class ReleaseIdentitySelectionTests(unittest.TestCase):
    def test_selected_version_is_evidence_backed_and_not_guessed(self) -> None:
        plan_version = _read_release_plan_version()
        state_target = _read_state_next_target()
        self.assertEqual(plan_version, SELECTED_VERSION)
        self.assertEqual(state_target, SELECTED_VERSION)
        self.assertNotEqual(plan_version, "TBD")
        self.assertNotEqual(plan_version, "0.5.0")


class ReleaseIdentitySurfaceTests(unittest.TestCase):
    def test_package_module_and_metadata_share_one_version(self) -> None:
        from orbitrelay import __version__

        package_version = _read_pyproject_version()
        self.assertEqual(package_version, SELECTED_VERSION)
        self.assertEqual(__version__, SELECTED_VERSION)
        self.assertEqual(package_version, __version__)

    def test_cli_version_flag_reports_selected_identity(self) -> None:
        from orbitrelay import __version__, cli

        output = io.StringIO()
        error = io.StringIO()
        with (
            patch("sys.stdout", output),
            patch("sys.stderr", error),
        ):
            result = cli.main(["--version"])
        self.assertEqual(result, 0)
        text = output.getvalue() + error.getvalue()
        self.assertRegex(text, rf"\b{re.escape(__version__)}\b")
        self.assertIn(SELECTED_VERSION, text)

    def test_module_entry_point_version_flag_reports_selected_identity(self) -> None:
        completed = subprocess.run(
            ["uv", "run", "python", "-m", "orbitrelay", "--version"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        text = completed.stdout + completed.stderr
        self.assertIn(SELECTED_VERSION, text)

    def test_script_entry_point_version_flag_reports_selected_identity(self) -> None:
        completed = subprocess.run(
            ["uv", "run", "orbitrelay", "--version"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        text = completed.stdout + completed.stderr
        self.assertIn(SELECTED_VERSION, text)


class ReleaseIdentityWheelTests(unittest.TestCase):
    def test_built_wheel_command_reports_selected_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            build = subprocess.run(
                ["uv", "build", "--out-dir", str(out_dir)],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            wheels = sorted(out_dir.glob("*.whl"))
            self.assertTrue(wheels, "build did not produce a wheel")
            wheel = wheels[0]
            self.assertIn(SELECTED_VERSION, wheel.name)
            completed = subprocess.run(
                [
                    "uv",
                    "run",
                    "--isolated",
                    "--no-project",
                    "--with",
                    str(wheel),
                    "orbitrelay",
                    "--version",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(
                completed.returncode, 0, completed.stdout + completed.stderr
            )
            text = completed.stdout + completed.stderr
            self.assertIn(SELECTED_VERSION, text)



class PlatformSupportClaimTests(unittest.TestCase):
    """e09s04: package metadata, docs, and state must agree on support claims."""

    def _read(self, relative: str) -> str:
        return (REPO_ROOT / relative).read_text(encoding="utf-8")

    def test_python_floor_matches_package_metadata_and_docs(self) -> None:
        data = tomllib.loads(self._read("pyproject.toml"))
        requires = data["project"]["requires-python"]
        self.assertEqual(requires, ">=3.12")
        classifiers = set(data["project"]["classifiers"])
        for minor in ("3.12", "3.13", "3.14"):
            self.assertIn(f"Programming Language :: Python :: {minor}", classifiers)
        self.assertIn("Operating System :: MacOS", classifiers)
        # Do not claim OS Independent / Windows / Linux as qualified OS classifiers.
        for forbidden in (
            "Operating System :: Microsoft :: Windows",
            "Operating System :: POSIX :: Linux",
            "Operating System :: OS Independent",
        ):
            self.assertNotIn(forbidden, classifiers)

        readme = self._read("README.md")
        roadmap = self._read("docs/project-roadmap.md")
        agents = self._read("AGENTS.md")
        state = self._read("specs/state.yaml")
        for text in (readme, roadmap, agents, state):
            self.assertRegex(text, r"3\.12")
            self.assertRegex(text.lower(), r"macos")

        self.assertIn("Qualified", readme)
        self.assertRegex(readme, r"Preview\s*/\s*unverified|preview/unverified")
        self.assertRegex(readme.lower(), r"windows.*deferred|deferred.*windows")

    def test_linux_and_windows_are_not_described_as_qualified(self) -> None:
        surfaces = {
            "README.md": self._read("README.md"),
            "docs/project-roadmap.md": self._read("docs/project-roadmap.md"),
            "AGENTS.md": self._read("AGENTS.md"),
            "docs/architecture.md": self._read("docs/architecture.md"),
        }
        # Forbidden phrasing that overstates unqualified platforms.
        forbidden = [
            r"linux is (the )?qualified",
            r"linux is (a )?supported platform",
            r"windows is (the )?qualified",
            r"windows is (a )?supported platform",
            r"macos and linux are the supported platforms",
            r"qualified on linux",
            r"qualified on windows",
        ]
        for name, text in surfaces.items():
            lowered = text.lower()
            for pattern in forbidden:
                self.assertIsNone(
                    __import__("re").search(pattern, lowered),
                    f"{name} overstates support via /{pattern}/",
                )
            # Positive required claims
            if name != "docs/architecture.md":
                self.assertIn("preview", lowered)
                self.assertIn("deferred", lowered)

    def test_state_python_support_decision_matches_metadata(self) -> None:
        state = self._read("specs/state.yaml")
        self.assertIn("Python 3.12 through 3.14 is qualified on macOS", state)
        self.assertIn("Linux is preview", state)
        self.assertIn("Windows remains deferred", state)
        self.assertIn(">=3.12", state)

    def test_matrix_evidence_exists_for_qualified_minors(self) -> None:
        from scripts.python_matrix import validate_matrix_evidence

        evidence = REPO_ROOT / "specs" / "verifications" / "python-matrix-evidence.json"
        self.assertTrue(evidence.is_file())
        validate_matrix_evidence(evidence)


if __name__ == "__main__":
    unittest.main()
