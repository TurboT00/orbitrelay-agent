import argparse
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from .agent import run_agent
from .config import load_api_config


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Chatbot")
    parser.add_argument("user_prompt", type=str, help="User prompt")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument(
        "--workspace",
        type=str,
        help="Workspace directory (default: current directory)",
    )
    return parser.parse_args(argv)


def resolve_workspace(value: str | None) -> str:
    workspace = Path.cwd() if value is None else Path(value).expanduser()
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise ValueError(f'Workspace is not a directory: "{workspace}"')
    return str(workspace)


def main(argv=None) -> int:
    load_dotenv()
    args = parse_args(argv)
    api_config = load_api_config()
    working_directory = resolve_workspace(args.workspace)
    client = OpenAI(api_key=api_config.api_key, base_url=api_config.base_url)
    result = run_agent(
        client,
        args.user_prompt,
        api_config.model,
        working_directory=working_directory,
        verbose=args.verbose,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
