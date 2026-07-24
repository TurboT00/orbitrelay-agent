# story: e03s01

import os
from collections.abc import Mapping
from dataclasses import dataclass


MAX_CHARS = 10000
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
XAI_DEFAULT_BASE_URL = "https://api.x.ai/v1"
XAI_DEFAULT_MODEL = "grok-4.5"


@dataclass(frozen=True)
class ApiConfig:
    base_url: str
    api_key: str
    model: str


def load_api_config(environ: Mapping[str, str] | None = None) -> ApiConfig:
    values = os.environ if environ is None else environ

    openai_api_key = values.get("OPENAI_API_KEY", "").strip()
    xai_api_key = values.get("XAI_API_KEY", "").strip()

    if openai_api_key:
        base_url = values.get("OPENAI_BASE_URL", DEFAULT_BASE_URL).strip()
        model = values.get("OPENAI_MODEL", DEFAULT_MODEL).strip()
        if not base_url:
            raise ValueError("OPENAI_BASE_URL cannot be empty")
        if not model:
            raise ValueError("OPENAI_MODEL cannot be empty")
        return ApiConfig(base_url=base_url, api_key=openai_api_key, model=model)

    if xai_api_key:
        if "XAI_BASE_URL" in values:
            base_url = values.get("XAI_BASE_URL", "").strip()
            if not base_url:
                raise ValueError("XAI_BASE_URL cannot be empty")
        else:
            base_url = XAI_DEFAULT_BASE_URL
        if "XAI_MODEL" in values:
            model = values.get("XAI_MODEL", "").strip()
            if not model:
                raise ValueError("XAI_MODEL cannot be empty")
        else:
            model = XAI_DEFAULT_MODEL
        return ApiConfig(base_url=base_url, api_key=xai_api_key, model=model)

    raise ValueError("OPENAI_API_KEY or XAI_API_KEY is required")
