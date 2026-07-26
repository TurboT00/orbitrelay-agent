# story: e03s01

import os
from collections.abc import Mapping
from dataclasses import dataclass

MAX_CHARS = 10000
DEEPSEEK_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_DEFAULT_MODEL = "gemini-3.6-flash"
XAI_URL = "https://api.x.ai/v1"
XAI_DEFAULT_MODEL = "grok-4.5"


@dataclass(frozen=True)
class ApiConfig:
    base_url: str
    api_key: str
    model: str


def load_api_config(environ: Mapping[str, str] | None = None) -> ApiConfig:
    values = os.environ if environ is None else environ

    deepseek_api_key = values.get("DEEPSEEK_API_KEY", "").strip()
    gemini_api_key = values.get("GEMINI_API_KEY", "").strip()
    xai_api_key = values.get("XAI_API_KEY", "").strip()

    if deepseek_api_key:
        base_url = DEEPSEEK_URL
        model = values.get("DEEPSEEK_MODEL", DEEPSEEK_DEFAULT_MODEL).strip()
        if not model:
            raise ValueError("DEEPSEEK_MODEL cannot be empty")
        return ApiConfig(base_url=base_url, api_key=deepseek_api_key, model=model)

    if gemini_api_key:
        base_url = GEMINI_URL
        model = values.get("GEMINI_MODEL", GEMINI_DEFAULT_MODEL).strip()
        if not model:
            raise ValueError("GEMINI_MODEL cannot be empty")
        return ApiConfig(base_url=base_url, api_key=gemini_api_key, model=model)

    if xai_api_key:
        base_url = XAI_URL
        model = values.get("XAI_MODEL", XAI_DEFAULT_MODEL).strip()
        if not model:
            raise ValueError("XAI_MODEL cannot be empty")
        return ApiConfig(base_url=base_url, api_key=xai_api_key, model=model)

    raise ValueError("DEEPSEEK_API_KEY, GEMINI_API_KEY or XAI_API_KEY is required")
