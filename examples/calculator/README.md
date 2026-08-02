# Calculator example workspace

This self-contained calculator is a small repository-only workspace for trying
OrbitRelay's file and Python tools. It is not included in built wheels and does
not define OrbitRelay as a coding-specific assistant.

Run its tests directly:

```bash
uv run python examples/calculator/tests.py
```

Use it with OrbitRelay:

```bash
uv run orbitrelay "inspect the calculator and run its tests" \
  --workspace examples/calculator
```
