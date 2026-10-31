import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.judge.base import JudgeError
from app.judge.openrouter import OpenRouterJudge
from app.models import AgentConfig
from app.teacher.openrouter import OpenRouterTeacher


def test_agent_defaults_are_seeded(admin_client: TestClient, app: FastAPI) -> None:
    with Session(app.state.engine) as session:
        configs = {config.step: config for config in crud.list_agent_configs(session)}

    assert set(configs) == {"judge", "teacher", "tts", "verbalizer", "stt"}
    assert "person who answered it" in configs["teacher"].system_prompt
    assert "may or may not be the card's author" in configs["teacher"].system_prompt
    assert "Respect the requested language" in configs["teacher"].system_prompt
    assert "do not over-translate them" in configs["teacher"].system_prompt
    assert "{{ card.question }}" in configs["teacher"].prompt_template
    assert configs["tts"].prompt_template == ""
    assert configs["stt"].prompt_template == ""


def test_agent_page_lists_every_step_and_no_secret_field(admin_client: TestClient) -> None:
    response = admin_client.get("/admin/agents")

    assert response.status_code == 200
    for label in ("Judge", "Teacher", "TTS", "Verbalizer", "STT"):
        assert label in response.text
    assert "OPENROUTER_API_KEY" in response.text
    assert 'type="password"' not in response.text


def test_agent_page_is_admin_only(client: TestClient) -> None:
    assert client.get("/admin/agents").status_code == 403


def test_admin_can_save_agent_prompt(
    admin_client: TestClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEACHER_API_KEY", "test-key")
    response = admin_client.post(
        "/admin/agents/teacher",
        data={
            "model": "teacher-model",
            "base_url": "https://teacher.test",
            "api_key_env": "TEACHER_API_KEY",
            "voice": "",
            "system_prompt": "Custom system prompt",
            "prompt_template": "Explain {{ card.question }}",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    with Session(app.state.engine) as session:
        config = crud.get_agent_config(session, "teacher")
    assert config.model == "teacher-model"
    assert config.base_url == "https://teacher.test"
    assert config.api_key_env == "TEACHER_API_KEY"
    assert config.system_prompt == "Custom system prompt"
    assert config.prompt_template == "Explain {{ card.question }}"


def test_agent_save_requires_the_key_in_the_environment(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("TEACHER_API_KEY", raising=False)

    response = admin_client.post(
        "/admin/agents/teacher",
        data={
            "model": "",
            "base_url": "",
            "api_key_env": "TEACHER_API_KEY",
            "voice": "",
            "system_prompt": "",
            "prompt_template": "Explain {{ card.question }}",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "must be defined in the environment" in response.text


def test_teacher_prompt_template_renders_card_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    config = AgentConfig(
        step="teacher",
        model="teacher-model",
        base_url="https://teacher.test",
        api_key_env="OPENROUTER_API_KEY",
        system_prompt="System prompt",
        prompt_template="Q={{ card.question }} A={{ card.answer }} U={{ user_answer }}",
    )
    verbalizer = AgentConfig(
        step="verbalizer",
        model="vocal-model",
        base_url="https://teacher.test",
        api_key_env="OPENROUTER_API_KEY",
        system_prompt="Verbalizer prompt",
        prompt_template="{{ text }}",
    )
    teacher = OpenRouterTeacher.from_config(config, verbalizer)
    teacher.transport = httpx.MockTransport(handler)

    teacher.explain(
        deck_context="Deck",
        card_context="Context",
        question="Capital of France?",
        expected_answer="Paris",
        user_answer="Lyon",
        is_correct=False,
        language="fr",
    )

    body = bodies[0].decode()
    assert "Q=Capital of France?" in body
    assert "A=Paris" in body
    assert "U=Lyon" in body
    assert "System prompt" in body


def test_agent_requires_api_key_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    judge = OpenRouterJudge(base_url="https://openrouter.ai", model="judge-model")

    with pytest.raises(JudgeError, match="API key is not set"):
        judge.evaluate(
            question="Q",
            expected_answer="A",
            user_answer="A",
            expected_time_s=None,
            response_time_ms=1000,
            language="auto",
        )
