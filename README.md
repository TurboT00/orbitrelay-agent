# OrbitRelay Agent

OrbitRelay is a coding-agent CLI that relays work through a configurable
OpenAI-compatible model endpoint. It uses hosted endpoints today; support and
setup for local LLM servers are future scope, not a current feature.

## Setup

Install the locked dependencies and the project command:

```bash
uv sync --locked
```

Copy the environment template and add your API key:

```bash
cp .env.example .env
```

The default provider configuration is:

```dotenv
OPENAI_API_KEY=replace-with-your-api-key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash
```

`OPENAI_API_KEY` is required. The base URL and model can be overridden for
another OpenAI-compatible Chat Completions endpoint. That endpoint must support
function/tool calling and accept provider-specific assistant fields when they
are replayed as conversation history.

## Run OrbitRelay

OrbitRelay works inside the current directory by default:

```bash
cd /path/to/project
uv run orbitrelay "inspect this project and explain how it works"
```

Select another workspace explicitly with `--workspace`:

```bash
uv run orbitrelay \
  "inspect the calculator and run its tests" \
  --workspace examples/calculator
```

Include per-response usage and tool-call details with `--verbose`. The module
entry point is equivalent:

```bash
uv run python -m orbitrelay --help
```

To install the command in an isolated uv tool environment:

```bash
uv tool install .
orbitrelay --help
```

## Configuration

OrbitRelay currently requires an OpenAI-compatible Chat Completions endpoint
with function/tool calling. Configure a different hosted endpoint with
`OPENAI_BASE_URL` and `OPENAI_MODEL`.

The same protocol boundary is intended to accommodate local servers such as
Ollama or vLLM in a later release, but no local endpoint is currently tested or
supported.

## Tools and safety boundary

The model can call four local tools:

- `get_files_info`
- `get_file_content`
- `run_python_file`
- `write_file`

Every tool path is resolved within the selected workspace, and symlink paths
that escape it are rejected. The model cannot configure or override that
workspace. `run_python_file` starts an ordinary local Python process; it
restricts which script can be selected but is not an operating-system-level
sandbox for the script's own behavior.

The agent allows at most eight model responses, including the final textual
response. If response eight asks for more tools, none of those calls are
executed and the CLI exits with a clear turn-limit error.

## Project structure

```text
src/orbitrelay/        installable application package
src/orbitrelay/tools/  tool declarations, dispatch, and handlers
tests/                 offline automated tests
examples/calculator/   repository-only demo workspace
```

The calculator is not shipped inside the wheel and is not the default runtime
workspace. It exists only as a safe, small checkout example.

## License

OrbitRelay Agent is available under the [MIT License](LICENSE).

## Roadmap

See [docs/project-roadmap.md](docs/project-roadmap.md) for the dependency-aware
capability roadmap, authentication constraints, and next implementation slice.

## Development and verification

The automated agent tests use scripted responses and never call a live model
API. Run the complete local check from any working directory:

```bash
./scripts/check.sh
```

The script validates the lockfile, synchronizes dependencies, runs both test
suites, checks package imports and CLI entry points, builds the distributions,
and starts the command from an isolated wheel installation. Build artifacts are
created in a temporary directory and removed automatically.

The current script targets Bash on macOS and Linux, including Arch and Ubuntu.
A native Windows check can be added when Windows 11 becomes an explicitly
supported development platform; until then, Git Bash or WSL can run this script.
