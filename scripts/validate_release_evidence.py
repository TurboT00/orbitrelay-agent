#!/usr/bin/env python3
"""CLI wrapper: validate OrbitRelay automated release evidence (e10s01)."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `uv run python scripts/validate_release_evidence.py ...`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_evidence import main

if __name__ == "__main__":
    # Translate historical flags into the shared CLI.
    argv = list(sys.argv[1:])
    if argv and argv[0] not in {"generate", "validate", "-h", "--help"}:
        argv = ["validate", *argv]
    raise SystemExit(main(argv))
