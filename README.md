# OrbitRelay

OrbitRelay is a general-purpose, text-first personal assistant that runs from
the command line.

It relays natural-language requests through configurable hosted model
connections and can use workspace-confined file and Python tools when a task
needs them.

Project and coding work are supported use cases, not the product boundary.
Voice interaction, device actions, service integrations, and local LLM servers
are future direction rather than current features.

## Setup

Install the locked dependencies and the project command:

```bash
uv sync --locked
```

Provider setup is described in [Configuration](#configuration).

## Run OrbitRelay

OrbitRelay works inside the current directory by default:

```bash
cd /path/to/project
uv run orbitrelay "help me plan this week and identify scheduling conflicts"
```

For tasks involving local files, select a workspace explicitly:

```bash
uv run orbitrelay \
  "summarize the notes in this folder and suggest next actions" \
  --workspace /path/to/notes
```

Include per-response usage and tool-call details with `--verbose`. Verbose mode
also emits secret-free approval decision lines and a structured run summary on
stderr. Opt into live model deltas and tool progress with `--stream` (progress
on stderr; final answer still on stdout).

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

OrbitRelay resolves exactly one stored provider connection for an agent run.
`--provider NAME` is a one-run override; without it, the selected connection is
used. Normal runs do not read provider environment variables or `.env` files.

```bash
orbitrelay provider list
orbitrelay provider connect openai --method api_key
orbitrelay provider connect gemini --method api_key
orbitrelay provider connect grok --method api_key
orbitrelay provider connect deepseek --method api_key
orbitrelay "inspect this project" --provider deepseek
```

`provider import-env --provider NAME` is available only to migrate one legacy
API key from the environment or `.env`. It rejects multiple provider keys,
interpolation, and endpoint overrides, then stores the imported key in the
native credential service. The sample `.env.example` is therefore import-only.

### Available connection methods

These methods are implemented and covered by offline tests. Availability does
not claim live-provider conformance; qualify a provider with disposable manual
tests before relying on it for release work.

| Provider | Available method | Notes |
| --- | --- | --- |
| OpenAI | API key | Uses the OpenAI-compatible agent route. |
| Codex | Subscription | Delegates login, logout, and execution to the official installed Codex CLI; OrbitRelay never reads Codex credentials. |
| Gemini | API key | Gemini OAuth is unavailable until its documented integration probe passes. |
| Grok (xAI) | API key | No third-party subscription OAuth is offered. |
| DeepSeek | API key | No subscription OAuth is offered. |

Connection metadata is stored in `~/.orbitrelay/profiles.json`, and credentials
remain in the operating system credential store. Set `ORBITRELAY_HOME` for an
isolated application directory. The storage directory must be user-owned and
not group/world writable; metadata never includes a secret. Existing version-1
metadata is migrated atomically while preserving its credential-key namespace.

### Codex CLI bridge

Install the official `codex` CLI separately. Its credentials and sign-in remain
provider-owned:

```bash
orbitrelay provider connect codex --method subscription
orbitrelay codex status
orbitrelay codex exec "summarize this repository" --workspace .
```

The removed `profile` and `auth` commands now exit with migration guidance; use
`orbitrelay provider --help` instead.

## Conversations, streaming, and sessions

OrbitRelay runs on a shared internal event model (`run.started`, model/tool/
approval/usage events, `run.completed`). That model backs streaming, local
session persistence, context budgeting, and run summaries.

### Streaming

```bash
# Live token deltas and tool progress on stderr; final answer on stdout
uv run orbitrelay "explain this project" --stream

# Structured run summary on stderr (status, tool counts, usage)
uv run orbitrelay "explain this project" --verbose
```

Non-stream mode remains the default so scripts and pipes only see the final
answer on stdout.

### Local sessions

Resumable sessions are stored **per user**, not in the project repo:

- Path: `~/.orbitrelay/sessions/<id>/` (or `$ORBITRELAY_HOME/sessions/<id>/`)
- Layout: `metadata.json`, `messages.jsonl`, `events.jsonl`
- Permissions: directories `0700`, files `0600`; symlinks and group/world-writable
  paths are rejected
- Retention: keep until you delete (no auto-purge)
- Secrets: provider API keys and OAuth tokens are **never** written into session
  files (redaction applies). P4 does **not** encrypt session payloads at the app
  layer—disk access with your user privileges can still read transcripts.

```bash
# Create or resume a named session
uv run orbitrelay "first turn" --session demo
uv run orbitrelay "continue" --session demo

# Auto-generate a session id (printed on stderr)
uv run orbitrelay "start" --new-session

# Manage sessions
uv run orbitrelay session list
uv run orbitrelay session show demo
uv run orbitrelay session delete demo
uv run orbitrelay session delete-all --confirm
```

Context history sent to the model is budgeted so tool-call/result pairs are never
split: older complete segments drop first; if the newest segment alone cannot fit,
OrbitRelay fails closed instead of orphaning a tool result.

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
workspace. It is a safe, small demonstration of the file and Python tools, not
a statement that OrbitRelay is coding-specific.

## License

OrbitRelay is available under the [MIT License](LICENSE).

## Roadmap

See [docs/project-roadmap.md](docs/project-roadmap.md) for current product status
and future direction. See [docs/architecture.md](docs/architecture.md) for the
durable provider, agent, safety, and persistence boundaries.

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
