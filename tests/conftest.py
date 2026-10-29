from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.dependencies import get_judge, get_stt, get_teacher
from app.judge.base import JudgeError, JudgeResult
from app.main import create_app
from app.stt.base import STTError, STTResult
from app.teacher.base import TeacherError, TeacherResult


class FakeJudge:
    model = "fake-judge"

    def __init__(self) -> None:
        self.result = JudgeResult(rating=3, is_correct=True, feedback="Good answer")
        self.error: JudgeError | None = None
        self.calls: list[dict[str, Any]] = []

    def evaluate(
        self,
        *,
        question: str,
        expected_answer: str,
        user_answer: str,
        expected_time_s: int | None,
        response_time_ms: int,
        language: str,
    ) -> JudgeResult:
        self.calls.append(
            {
                "question": question,
                "expected_answer": expected_answer,
                "user_answer": user_answer,
                "expected_time_s": expected_time_s,
                "response_time_ms": response_time_ms,
                "language": language,
            }
        )
        if self.error is not None:
            raise self.error
        return self.result


class FakeTeacher:
    model = "fake-teacher"

    def __init__(self) -> None:
        self.result = TeacherResult(explanation="Paris is the capital of France.")
        self.error: TeacherError | None = None
        self.calls: list[dict[str, Any]] = []

    def explain(
        self,
        *,
        deck_context: str,
        card_context: str,
        question: str,
        expected_answer: str,
        user_answer: str,
        is_correct: bool | None,
        language: str,
    ) -> TeacherResult:
        self.calls.append(
            {
                "deck_context": deck_context,
                "card_context": card_context,
                "question": question,
                "expected_answer": expected_answer,
                "user_answer": user_answer,
                "is_correct": is_correct,
                "language": language,
            }
        )
        if self.error is not None:
            raise self.error
        return self.result


class FakeSTT:
    def __init__(self) -> None:
        self.result = STTResult(
            text="voice transcript", audio_duration_ms=1200, stt_duration_ms=45
        )
        self.error: STTError | None = None
        self.calls: list[tuple[bytes, str]] = []

    def transcribe(self, audio: bytes, language: str) -> STTResult:
        self.calls.append((audio, language))
        if self.error is not None:
            raise self.error
        return self.result


def response_dict(response: Response) -> dict[str, Any]:
    data = response.json()
    assert isinstance(data, dict)
    return data


def response_list(response: Response) -> list[dict[str, Any]]:
    data = response.json()
    assert isinstance(data, list)
    return data


@pytest.fixture
def fake_judge() -> FakeJudge:
    return FakeJudge()


@pytest.fixture
def fake_stt() -> FakeSTT:
    return FakeSTT()


@pytest.fixture
def fake_teacher() -> FakeTeacher:
    return FakeTeacher()


@pytest.fixture
def app(fake_judge: FakeJudge, fake_stt: FakeSTT, fake_teacher: FakeTeacher) -> FastAPI:
    application = create_app("sqlite://", teacher=fake_teacher)
    application.dependency_overrides[get_judge] = lambda: fake_judge
    application.dependency_overrides[get_stt] = lambda: fake_stt
    application.dependency_overrides[get_teacher] = lambda: fake_teacher
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session(app: FastAPI, client: TestClient) -> Iterator[Session]:
    engine = app.state.engine
    assert isinstance(engine, Engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def deck(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/decks",
        json={
            "name": "Geography",
            "description": "World facts",
            "context": "Upper-secondary geography course",
            "scheduler": "fsrs",
            "scheduler_params": {"desired_retention": 0.85},
        },
    )
    assert response.status_code == 201
    return response_dict(response)


@pytest.fixture
def card(client: TestClient, deck: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/api/cards",
        json={
            "deck_id": deck["id"],
            "question": "Capital of France?",
            "answer": "Paris",
            "details": "https://en.wikipedia.org/wiki/Paris",
            "context": "Capitals are seated in the city proper, not the metro area.",
            "expected_time_s": 20,
            "tags": ["geography", "europe"],
        },
    )
    assert response.status_code == 201
    return response_dict(response)
