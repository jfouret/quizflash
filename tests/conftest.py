from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy.engine import Engine
from sqlmodel import Session

from app import auth
from app.auth import AuthConfig
from app.dependencies import get_judge, get_stt, get_teacher, get_tts
from app.judge.base import JudgeError, JudgeResult
from app.main import create_app
from app.models import User
from app.stt.base import STTError, STTResult
from app.teacher.base import TeacherError, TeacherResult
from app.tts.base import TTSError, TTSResult, TTSStream


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
        max_level: int = 5,
        labels: dict[int, str] | None = None,
    ) -> JudgeResult:
        self.calls.append(
            {
                "question": question,
                "expected_answer": expected_answer,
                "user_answer": user_answer,
                "expected_time_s": expected_time_s,
                "response_time_ms": response_time_ms,
                "language": language,
                "max_level": max_level,
                "labels": labels,
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
        self.vocal_calls: list[dict[str, Any]] = []

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

    def to_vocal(self, text: str, *, language: str) -> str:
        self.vocal_calls.append({"text": text, "language": language})
        if self.error is not None:
            raise self.error
        return "Vocal: " + text


class FakeSTT:
    def __init__(self) -> None:
        self.result = STTResult(text="voice transcript", audio_duration_ms=1200, stt_duration_ms=45)
        self.error: STTError | None = None
        self.calls: list[tuple[bytes, str]] = []

    def transcribe(self, audio: bytes, language: str) -> STTResult:
        self.calls.append((audio, language))
        if self.error is not None:
            raise self.error
        return self.result


class FakeTTS:
    model = "fake-tts"

    def __init__(self) -> None:
        self.result = TTSResult(audio=b"FAKEAUDIO", content_type="audio/mpeg")
        self.error: TTSError | None = None
        self.calls: list[tuple[str, str]] = []

    def speak(self, text: str, language: str) -> TTSResult:
        self.calls.append((text, language))
        if self.error is not None:
            raise self.error
        return self.result

    def speak_stream(self, text: str, language: str) -> TTSStream:
        result = self.speak(text, language)
        return TTSStream(content_type=result.content_type, chunks=iter([result.audio]))


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
def fake_tts() -> FakeTTS:
    return FakeTTS()


PASSWORD = "correct horse battery staple"
BASE_URL = "https://testserver"


@pytest.fixture
def auth_config() -> AuthConfig:
    return AuthConfig(cookie_secure=True, secret_key="test-secret")


@pytest.fixture
def app(
    fake_judge: FakeJudge,
    fake_stt: FakeSTT,
    fake_teacher: FakeTeacher,
    fake_tts: FakeTTS,
    auth_config: AuthConfig,
) -> FastAPI:
    application = create_app("sqlite://", teacher=fake_teacher, auth_config=auth_config)
    application.dependency_overrides[get_judge] = lambda: fake_judge
    application.dependency_overrides[get_stt] = lambda: fake_stt
    application.dependency_overrides[get_teacher] = lambda: fake_teacher
    application.dependency_overrides[get_tts] = lambda: fake_tts
    return application


def make_user(app: FastAPI, email: str, *, role: str = "user", status: str = "active") -> User:
    with Session(app.state.engine) as session:
        return auth.create_local_user(
            session, email=email, password=PASSWORD, role=role, status=status
        )


def login(client: TestClient, email: str, password: str = PASSWORD) -> TestClient:
    """Log in through the real form and attach the session CSRF token to the client."""
    response = client.post(
        "/login", data={"email": email, "password": password}, follow_redirects=False
    )
    assert response.status_code == 303, response.text
    client.headers["X-CSRF-Token"] = response_dict(client.get("/api/auth/me"))["csrf_token"]
    return client


@pytest.fixture
def lifespan_client(app: FastAPI) -> Iterator[TestClient]:
    """The only client that runs the app lifespan (DB migrations, MCP session manager)."""
    with TestClient(app, base_url=BASE_URL) as test_client:
        yield test_client


@pytest.fixture
def alice(app: FastAPI, lifespan_client: TestClient) -> User:
    return make_user(app, "alice@example.com")


@pytest.fixture
def client(lifespan_client: TestClient, alice: User) -> TestClient:
    return login(lifespan_client, alice.email)


def new_client(app: FastAPI, email: str | None = None) -> TestClient:
    test_client = TestClient(app, base_url=BASE_URL)
    return login(test_client, email) if email else test_client


@pytest.fixture
def bob(app: FastAPI, lifespan_client: TestClient) -> User:
    return make_user(app, "bob@example.com")


@pytest.fixture
def client_b(app: FastAPI, bob: User) -> TestClient:
    return new_client(app, bob.email)


@pytest.fixture
def admin(app: FastAPI, lifespan_client: TestClient) -> User:
    return make_user(app, "admin@example.com", role="admin")


@pytest.fixture
def admin_client(app: FastAPI, admin: User) -> TestClient:
    return new_client(app, admin.email)


@pytest.fixture
def anon_client(app: FastAPI, lifespan_client: TestClient) -> TestClient:
    return new_client(app)


@pytest.fixture
def db_session(app: FastAPI, client: TestClient) -> Iterator[Session]:
    engine = app.state.engine
    assert isinstance(engine, Engine)
    with Session(engine) as session:
        yield session


def mcp_call(
    client: TestClient, token: str | None, name: str, arguments: dict[str, Any] | None = None
) -> Response:
    headers = {"Accept": "application/json, text/event-stream"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    response: Response = client.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        },
        headers=headers,
    )
    return response


def mcp_tool(
    client: TestClient, token: str, name: str, arguments: dict[str, Any] | None = None
) -> Any:
    """Call a tool and return its structured result; raise on tool errors."""
    response = mcp_call(client, token, name, arguments)
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    if result.get("isError"):
        raise AssertionError(result["content"][0]["text"])
    structured = result.get("structuredContent")
    if structured is not None and set(structured) == {"result"}:
        return structured["result"]
    return structured


def mcp_token(client: TestClient, name: str = "agent") -> str:
    response = client.post("/api/settings/tokens", json={"name": name})
    assert response.status_code == 201, response.text
    token = response_dict(response)["token"]
    assert isinstance(token, str)
    return token


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
