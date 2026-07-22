import os
from collections.abc import Mapping
from dataclasses import dataclass


MAX_CHARS = 10000
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


@dataclass(frozen=True)
class ApiConfig:
    base_url: str
    api_key: str
    model: str


def load_api_config(environ: Mapping[str, str] | None = None) -> ApiConfig:
    values = os.environ if environ is None else environ

    api_key = values.get("OPENAI_API_KEY", "").strip()
    base_url = values.get("OPENAI_BASE_URL", DEFAULT_BASE_URL).strip()
    model = values.get("OPENAI_MODEL", DEFAULT_MODEL).strip()

    if not api_key:
        raise ValueError("OPENAI_API_KEY is required")
    if not base_url:
        raise ValueError("OPENAI_BASE_URL cannot be empty")
    if not model:
        raise ValueError("OPENAI_MODEL cannot be empty")

    return ApiConfig(base_url=base_url, api_key=api_key, model=model)
