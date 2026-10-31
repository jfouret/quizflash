import pytest

from app.config import DEFAULT_OPENROUTER_BASE_URL, api_key_env, base_url_env
from app.judge.openrouter import OpenRouterJudge
from app.stt.openai_compat import OpenAICompatibleSTT
from app.teacher.openrouter import OpenRouterTeacher
from app.tts.openrouter import OpenRouterTTS

ENV_VARS = [
    "JUDGE_BASE_URL",
    "JUDGE_API_KEY",
    "STT_BASE_URL",
    "STT_API_KEY",
    "TEACHER_BASE_URL",
    "TEACHER_API_KEY",
    "TTS_BASE_URL",
    "TTS_API_KEY",
    "TTS_VOICE",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_API_KEY",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_to_openrouter_root_and_no_key() -> None:
    assert base_url_env("JUDGE_BASE_URL") == DEFAULT_OPENROUTER_BASE_URL
    assert api_key_env("JUDGE_API_KEY") == ""
    assert OpenRouterTTS.from_env().voice == "en_paul_neutral"


def test_openrouter_vars_are_the_fallback_for_every_service() -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://or.test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-shared")
    try:
        assert base_url_env("JUDGE_BASE_URL") == "https://or.test"
        assert base_url_env("STT_BASE_URL") == "https://or.test"
        assert base_url_env("TEACHER_BASE_URL", "JUDGE_BASE_URL") == "https://or.test"
        assert base_url_env("TTS_BASE_URL", "TEACHER_BASE_URL") == "https://or.test"
        assert api_key_env("JUDGE_API_KEY") == "sk-or-shared"
        assert api_key_env("STT_API_KEY") == "sk-or-shared"
        assert api_key_env("TTS_API_KEY", "TEACHER_API_KEY") == "sk-or-shared"
        assert OpenRouterJudge.from_env().base_url == "https://or.test"
        assert OpenRouterJudge.from_env().api_key == "sk-or-shared"
        assert OpenRouterTTS.from_env().base_url == "https://or.test"
        assert OpenRouterTTS.from_env().api_key == "sk-or-shared"
        assert OpenRouterTeacher.from_env().base_url == "https://or.test"
        assert OpenRouterTeacher.from_env().api_key == "sk-or-shared"
        assert OpenAICompatibleSTT.from_env().base_url == "https://or.test"
        assert OpenAICompatibleSTT.from_env().api_key == "sk-or-shared"
    finally:
        monkeypatch.undo()


def test_specific_var_wins_over_openrouter_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://or.test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-shared")
    monkeypatch.setenv("TTS_BASE_URL", "https://tts.example.com")
    monkeypatch.setenv("TTS_API_KEY", "sk-tts")
    tts = OpenRouterTTS.from_env()
    assert tts.base_url == "https://tts.example.com"
    assert tts.api_key == "sk-tts"
