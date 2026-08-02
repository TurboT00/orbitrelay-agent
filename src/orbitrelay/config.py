# story: e03s01

from dataclasses import dataclass

MAX_CHARS = 10000


@dataclass(frozen=True)
class ApiConfig:
    base_url: str
    api_key: str
    model: str
