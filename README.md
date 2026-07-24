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

Include per-response usage and tool-call details with `--verbose`. Verbose mode
also emits secret-free approval decision lines on stderr.

The module entry point is equivalent:

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

## Provider profiles

Named profiles store endpoint, model, auth-kind, and capability metadata in the
current user's `~/.orbitrelay/profiles.json`. Set `ORBITRELAY_HOME` to use a
different application directory, which is useful for isolated development and
tests. A custom directory and its ancestors must be controlled by the current
user; OrbitRelay rejects symlinked, foreign-owned, or group/world-writable profile
storage at the application-directory boundary. Profile files never contain
credentials.

Create an API-key profile. OrbitRelay prompts without echoing the credential.
For xAI defaults, prefer `--preset xai` (see Supported hosted access above).

```bash
orbitrelay profile create deepseek-work \
  --base-url https://api.deepseek.com \
  --model deepseek-v4-flash \
  --auth-kind api_key \
  --capability tool_calling \
  --capability assistant_message_passthrough
```

For automation, add `--secret-stdin` and pipe the credential through standard
input. Secret-valued command-line options are intentionally unsupported.

Manage and select profiles with:

```bash
orbitrelay profile list
orbitrelay profile show deepseek-work
orbitrelay profile select deepseek-work
orbitrelay profile delete deepseek-work
```

At runtime, `--profile NAME` takes precedence over the saved selection, which
takes precedence over the existing `OPENAI_*` environment configuration:

```bash
orbitrelay "inspect this project" --profile deepseek-work
```

Profile credentials use the operating system's native credential service through
Python `keyring`. OrbitRelay fails closed when no approved native backend is
available; it never falls back to a plaintext credential file. Linux systems
need a configured Secret Service or KWallet backend. On macOS, credentials
created by a Python executable may be readable by that same executable without a
new prompt unless access is tightened in Keychain Access.

P1 profile persistence is supported on macOS and Linux. Windows profile locking
and credential storage remain P7 work. If `keyring` selects a chainer backend,
configure one supported native backend explicitly; OrbitRelay rejects chained or
custom backends rather than guessing where a secret will be stored.

Credential identifiers are bound to the canonical profile-file path. Moving
`ORBITRELAY_HOME` therefore creates a new credential namespace and requires
re-entering profile credentials. Mutations use a process-safe lock on macOS and
Linux. Atomic replacement protects metadata from torn writes, but P1 does not
claim power-loss atomicity across the metadata file and OS keychain.

OrbitRelay does not combine partial provider settings from the process
environment and a project `.env`: if the process supplies any `OPENAI_*` or
`XAI_*` transport setting, that mapping is validated as one source; otherwise the
loaded `.env` mapping is used. This prevents a project file from pairing its
endpoint with an inherited credential. OrbitRelay parses `OPENAI_API_KEY`,
`OPENAI_BASE_URL`, `OPENAI_MODEL`, `XAI_API_KEY`, `XAI_BASE_URL`, and `XAI_MODEL`
from `.env`; it never copies project-defined proxy, CA, or other transport
variables into the process environment. Dotenv interpolation is disabled, and
unresolved `${...}` placeholders in provider settings are rejected rather than
expanded from inherited process secrets.

Validated auth kinds include `api_key`, `subscription_oauth`,
`external_first_party_cli`, `local_none`, and `local_service_bearer`. Executable
run paths today are `api_key` and SuperGrok `subscription_oauth`. Codex uses a
separate CLI process boundary rather than the Chat Completions profile loop.

### xAI BYOK

Use an xAI API key (pay-as-you-go; **not** SuperGrok subscription quota):

```bash
export XAI_API_KEY=...
# defaults: https://api.x.ai/v1 and grok-4.5
uv run orbitrelay "inspect this project"
```

Or create a named profile:

```bash
uv run orbitrelay profile create xai-work --preset xai \
  --capability tool_calling \
  --capability assistant_message_passthrough
uv run orbitrelay "inspect this project" --profile xai-work
```

### SuperGrok / X Premium OAuth

Subscription usage is a separate track from `XAI_API_KEY`. Login uses xAI device
code OAuth; tokens stay in the OS keyring (OrbitRelay never reads `~/.grok/auth.json`):

```bash
uv run orbitrelay auth supergrok login
uv run orbitrelay auth supergrok status
uv run orbitrelay "inspect this project" --profile supergrok
uv run orbitrelay auth supergrok logout
```

If inference returns HTTP 403 after a successful login, the account may be
entitlement-gated. Fall back to `XAI_API_KEY` BYOK or verify the subscription tier.

### Codex CLI bridge

Install the official `codex` CLI yourself (not bundled). OrbitRelay only invokes
documented commands and never reads `CODEX_HOME/auth.json`:

```bash
uv run orbitrelay codex status
uv run orbitrelay codex login
# or: uv run orbitrelay codex login --device-auth
uv run orbitrelay codex exec "summarize this repository" --workspace .
uv run orbitrelay codex logout
```

`codex exec` is an **alternate runtime path**. Codex owns its own tool sandbox and
approvals for that path; OrbitRelay local tool approvals still apply to the
Chat Completions agent loop (`api_key` / SuperGrok profiles).

## Tool approval policies

OrbitRelay authorizes an entire validated tool-call batch before any approved
handler runs. Workspace-confined reads are allowed by default. Writes and local
Python execution require consent.

Interactive confirmation is the default policy:

```bash
uv run orbitrelay "create notes.txt" --workspace /path/to/project
```

Prompts appear on stderr as `Approve ...? [y/N/d=disable]`. Answer `y` to allow
once, `n` (or Enter/EOF/timeout) to deny, or `d` to disable that tool for the
rest of the run. Confirmation times out after 60 seconds by default and can be
overridden with `--approval-timeout SECONDS` (maximum 300).

Other run policies:

```bash
# Deny every write/execute without prompting; reads continue.
uv run orbitrelay "inspect only" --approval-policy read-only

# Allow exact consequential tools without prompting. Unlisted tools stay denied.
uv run orbitrelay "write the report" \
  --approval-policy pre-approved \
  --approve-tool write_file
```

`--approve-tool` is repeatable and accepts only `write_file` and
`run_python_file`. Pre-approved mode requires at least one tool name. Path,
symlink, argument, and workspace validation still apply after approval.

Denied calls return structured tool errors to the model. With `--verbose`,
OrbitRelay also prints ordered, control-escaped approval events to stderr. Those
events include call IDs and reasons, not write content, process arguments,
provider secrets, or tool results.

## Tools and safety boundary

The model can call four local tools:

- `get_files_info`
- `get_file_content`
- `run_python_file`
- `write_file`

Every tool path is resolved within the selected workspace, and symlink paths
that escape it are rejected. The model cannot configure or override that
workspace. `run_python_file` starts an ordinary local Python process with the
current interpreter, list arguments, and a trusted workspace cwd; it is not an
operating-system-level sandbox for the script's own behavior.

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
