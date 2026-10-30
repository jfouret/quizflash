import os

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai"


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


def base_url_env(*names: str) -> str:
    """First of X_BASE_URL..., then OPENROUTER_BASE_URL, then the OpenRouter default."""
    return _first_env(*names, "OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL


def api_key_env(*names: str) -> str:
    """First of X_API_KEY..., then OPENROUTER_API_KEY."""
    return _first_env(*names, "OPENROUTER_API_KEY")
