#!/usr/bin/env python3
"""Helpers for the macOS Python 3.12-3.14 qualification matrix (e09s03).

Tracks provisional candidate-floor metadata without mutating the caller's tree
unless apply mode is requested.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

DEFAULT_MINORS = ("3.12", "3.13", "3.14")
TRACKED_FLOOR_MARKER = 'requires-python = ">=3.14"'
CANDIDATE_FLOOR = "3.12"


class MatrixError(RuntimeError):
    """Matrix configuration or staging failure."""


def read_requires_python(pyproject_text: str) -> str:
    match = re.search(r'^requires-python\s*=\s*"([^"]+)"', pyproject_text, re.M)
    if match is None:
        raise MatrixError("requires-python not found in pyproject.toml")
    return match.group(1)


def read_python_classifiers(pyproject_text: str) -> tuple[str, ...]:
    return tuple(
        re.findall(
            r'"Programming Language :: Python :: (3\.\d+)"',
            pyproject_text,
        )
    )


def apply_candidate_floor(pyproject_text: str, floor: str = CANDIDATE_FLOOR) -> str:
    """Return pyproject text with a provisional requires-python floor and classifiers."""
    if not re.fullmatch(r"3\.\d+", floor):
        raise MatrixError(f"invalid Python floor: {floor}")
    majors = _minors_from_floor(floor, DEFAULT_MINORS[-1])
    text = re.sub(
        r'^requires-python\s*=\s*"[^"]+"',
        f'requires-python = ">={floor}"',
        pyproject_text,
        count=1,
        flags=re.M,
    )
    # Replace existing 3.x classifiers block entries with the qualified set.
    classifier_lines = [
        f'    "Programming Language :: Python :: {minor}",' for minor in majors
    ]
    pattern = re.compile(
        r'(    "Programming Language :: Python :: 3",\n)(?:    "Programming Language :: Python :: 3\.\d+",\n)+',
        re.M,
    )
    replacement = r"\1" + "\n".join(classifier_lines) + "\n"
    if pattern.search(text) is None:
        raise MatrixError("Python version classifiers block not found")
    text = pattern.sub(replacement, text, count=1)
    # mypy python_version tracks the floor for the qualified range.
    text = re.sub(
        r'^python_version\s*=\s*"[^"]+"',
        f'python_version = "{floor}"',
        text,
        count=1,
        flags=re.M,
    )
    return text


def _minors_from_floor(floor: str, ceiling: str) -> tuple[str, ...]:
    start = tuple(int(part) for part in floor.split("."))
    end = tuple(int(part) for part in ceiling.split("."))
    if start[0] != 3 or end[0] != 3 or start[1] > end[1]:
        raise MatrixError(f"unsupported floor/ceiling: {floor}..{ceiling}")
    return tuple(f"3.{minor}" for minor in range(start[1], end[1] + 1))


def stage_candidate_tree(
    repo_root: Path,
    destination: Path,
    *,
    floor: str = CANDIDATE_FLOOR,
    exclude_names: Iterable[str] = (
        ".git",
        ".venv",
        ".coverage",
        ".cache",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        "htmlcov",
        "dist",
        "build",
        ".bigpowers",
    ),
) -> Path:
    """Copy a disposable project tree and apply provisional floor metadata."""
    if destination.exists():
        if any(destination.iterdir()):
            raise MatrixError(f"destination already exists and is not empty: {destination}")
    else:
        destination.mkdir(parents=True)
    exclude = set(exclude_names)
    for path in repo_root.iterdir():
        if path.name in exclude:
            continue
        target = destination / path.name
        if path.is_dir():
            shutil.copytree(
                path,
                target,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.pyc",
                    ".venv",
                    ".coverage",
                    ".cache",
                ),
            )
        else:
            shutil.copy2(path, target)
    pyproject = destination / "pyproject.toml"
    original = pyproject.read_text(encoding="utf-8")
    pyproject.write_text(apply_candidate_floor(original, floor), encoding="utf-8")
    return destination


def write_matrix_evidence(
    path: Path,
    *,
    revision: str,
    floor: str,
    results: Sequence[dict[str, object]],
    tracked_requires_python: str,
) -> None:
    payload = {
        "kind": "python-matrix-evidence",
        "version": 1,
        "revision": revision,
        "floor": floor,
        "tracked_requires_python": tracked_requires_python,
        "minors": list(DEFAULT_MINORS),
        "results": list(results),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_matrix_evidence(
    path: Path,
    *,
    expected_revision: str | None = None,
    required_minors: Sequence[str] = DEFAULT_MINORS,
) -> None:
    if not path.is_file():
        raise MatrixError(f"matrix evidence missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("kind") != "python-matrix-evidence":
        raise MatrixError("matrix evidence kind mismatch")
    if expected_revision is not None and payload.get("revision") != expected_revision:
        raise MatrixError("matrix evidence revision mismatch")
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise MatrixError("matrix evidence results missing")
    seen: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            raise MatrixError("matrix evidence result must be an object")
        minor = item.get("python")
        status = item.get("status")
        if not isinstance(minor, str) or not isinstance(status, str):
            raise MatrixError("matrix evidence result missing python/status")
        seen.add(minor)
        if status != "passed":
            raise MatrixError(f"matrix evidence records failure for Python {minor}")
        # Secret-bearing keys are rejected.
        for key, value in item.items():
            text = f"{key}={value}".lower()
            if any(token in text for token in ("api_key", "secret", "password", "token=")):
                raise MatrixError("matrix evidence contains forbidden secret-bearing fields")
    missing = set(required_minors) - seen
    if missing:
        raise MatrixError(f"matrix evidence missing minors: {sorted(missing)}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show-tracked", help="Show tracked Python floor metadata")
    show.add_argument("--repo-root", type=Path, default=Path.cwd())

    stage = sub.add_parser("stage-candidate", help="Stage disposable candidate tree")
    stage.add_argument("--repo-root", type=Path, default=Path.cwd())
    stage.add_argument("--destination", type=Path, required=True)
    stage.add_argument("--floor", default=CANDIDATE_FLOOR)

    apply_cmd = sub.add_parser("render-floor", help="Print pyproject with floor applied")
    apply_cmd.add_argument("--repo-root", type=Path, default=Path.cwd())
    apply_cmd.add_argument("--floor", default=CANDIDATE_FLOOR)

    validate = sub.add_parser("validate-evidence", help="Validate matrix evidence JSON")
    validate.add_argument("path", type=Path)
    validate.add_argument("--revision", default=None)

    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "show-tracked":
            text = (args.repo_root / "pyproject.toml").read_text(encoding="utf-8")
            requires = read_requires_python(text)
            classifiers = read_python_classifiers(text)
            print(f"requires-python={requires}")
            print("classifiers=" + ",".join(classifiers))
            return 0
        if args.command == "stage-candidate":
            stage_candidate_tree(args.repo_root, args.destination, floor=args.floor)
            print(args.destination)
            return 0
        if args.command == "render-floor":
            text = (args.repo_root / "pyproject.toml").read_text(encoding="utf-8")
            sys.stdout.write(apply_candidate_floor(text, args.floor))
            return 0
        if args.command == "validate-evidence":
            validate_matrix_evidence(args.path, expected_revision=args.revision)
            print(f"valid: {args.path}")
            return 0
    except MatrixError as exc:
        print(f"python-matrix: error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
