from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.judge.base import JudgeError, JudgeResult
from app.models import AnswerLog, CardState, User
from app.stt.base import STTError
from tests.conftest import FakeJudge, FakeSTT, response_dict


def answer_payload(card_id: int, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "card_id": card_id,
        "answer_text": "Paris",
        "input_method": "text",
        "response_time_ms": 1500,
    }
    payload.update(overrides)
    return payload


def enable_ai_assess(client: TestClient) -> None:
    response = client.patch("/api/settings", json={"eval_mode": "ai_assess"})
    assert response.status_code == 200


def test_ai_preselect_requires_confirmation(client: TestClient, card: dict[str, Any]) -> None:
    proposed = response_dict(client.post("/api/study/answer", json=answer_payload(card["id"])))
    assert proposed["status"] == "pending"
    assert proposed["rating"] == 3
    assert proposed["is_correct"] is True
    assert (
        response_dict(client.get("/api/stats", params={"scope": "card", "id": card["id"]}))["total"]
        == 0
    )

    confirmed_payload = answer_payload(
        card["id"],
        confirmed=True,
        rating=2,
        is_correct=False,
        judge_feedback=proposed["feedback"],
        judge_model=proposed["judge_model"],
    )
    confirmed = response_dict(client.post("/api/study/answer", json=confirmed_payload))
    assert confirmed["status"] == "reviewed"
    assert confirmed["mode"] == "ai_preselect"
    assert confirmed["rating"] == 2
    assert confirmed["is_correct"] is False
    assert confirmed["due"] is not None
    stats = response_dict(client.get("/api/stats", params={"scope": "card", "id": card["id"]}))
    assert stats["total"] == 1
    assert stats["incorrect"] == 1
    assert stats["by_mode"] == {"ai_preselect": 1}
    assert client.get("/api/study/next").json() is None


def test_ai_assess_voice_metrics_and_judge_context(
    client: TestClient,
    db_session: Session,
    card: dict[str, Any],
    fake_judge: FakeJudge,
    fake_stt: FakeSTT,
) -> None:
    enable_ai_assess(client)
    client.patch("/api/settings", json={"judge_language": "fr", "stt_language": "en"})
    transcript = response_dict(
        client.post(
            "/api/study/transcribe",
            files={"audio": ("answer.webm", b"fake audio", "audio/webm")},
        )
    )
    assert transcript == {
        "text": "voice transcript",
        "stt_duration_ms": 45,
        "audio_duration_ms": 1200,
    }
    assert fake_stt.calls == [(b"fake audio", "en")]

    result = response_dict(
        client.post(
            "/api/study/answer",
            json=answer_payload(
                card["id"],
                answer_text=transcript["text"],
                input_method="voice",
                stt_duration_ms=transcript["stt_duration_ms"],
                audio_duration_ms=transcript["audio_duration_ms"],
            ),
        )
    )
    assert result["status"] == "reviewed"
    assert result["mode"] == "ai_assess"
    assert fake_judge.calls[0]["expected_time_s"] == 20
    assert fake_judge.calls[0]["response_time_ms"] == 1500
    assert fake_judge.calls[0]["language"] == "fr"
    assert fake_judge.calls[0]["user_answer"] == "voice transcript"

    logs = list(db_session.exec(select(AnswerLog)).all())
    assert len(logs) == 1
    assert logs[0].input_method == "voice"
    assert logs[0].stt_duration_ms == 45
    assert logs[0].audio_duration_ms == 1200
    assert logs[0].response_time_ms == 1500


def test_ai_assess_preview_can_be_corrected_before_saving(
    client: TestClient,
    db_session: Session,
    card: dict[str, Any],
    fake_judge: FakeJudge,
) -> None:
    enable_ai_assess(client)
    first = response_dict(
        client.post(
            "/api/study/answer",
            json=answer_payload(card["id"], answer_text="Pari", preview=True),
        )
    )
    assert first["status"] == "pending"
    assert first["mode"] == "ai_assess"
    assert (
        response_dict(client.get("/api/stats", params={"scope": "card", "id": card["id"]}))["total"]
        == 0
    )

    fake_judge.result = JudgeResult(rating=4, is_correct=True, feedback="")
    corrected = response_dict(
        client.post(
            "/api/study/answer",
            json=answer_payload(card["id"], answer_text="Paris", preview=True),
        )
    )
    assert corrected["status"] == "pending"
    assert corrected["rating"] == 4
    assert len(fake_judge.calls) == 2

    saved = response_dict(
        client.post(
            "/api/study/answer",
            json=answer_payload(
                card["id"],
                answer_text="Paris",
                confirmed=True,
                rating=corrected["rating"],
                is_correct=corrected["is_correct"],
                judge_feedback=corrected["feedback"],
                judge_model=corrected["judge_model"],
            ),
        )
    )
    assert saved["status"] == "reviewed"
    assert saved["mode"] == "ai_assess"
    log = db_session.exec(select(AnswerLog)).one()
    assert log.answer_text == "Paris"
    assert log.rating == 4


def test_judge_failure_uses_flagged_self_fallback(
    client: TestClient,
    db_session: Session,
    card: dict[str, Any],
    fake_judge: FakeJudge,
) -> None:
    enable_ai_assess(client)
    fake_judge.error = JudgeError("timeout")
    failed = response_dict(client.post("/api/study/answer", json=answer_payload(card["id"])))
    assert failed["status"] == "fallback_required"
    assert failed["mode"] == "self_fallback"
    assert failed["fallback_token"] is not None
    assert (
        response_dict(client.get("/api/stats", params={"scope": "card", "id": card["id"]}))["total"]
        == 0
    )

    fallback = response_dict(
        client.post(
            "/api/study/answer",
            json=answer_payload(
                card["id"],
                self_fallback=True,
                fallback_token=failed["fallback_token"],
                rating=1,
                is_correct=False,
                judge_feedback=failed["feedback"],
            ),
        )
    )
    assert fallback["status"] == "reviewed"
    assert fallback["mode"] == "self_fallback"
    assert len(fake_judge.calls) == 1
    log = db_session.exec(select(AnswerLog)).one()
    assert log.mode == "self_fallback"
    assert log.rating == 1
    assert "AI judge failed" in log.judge_feedback


def test_self_fallback_cannot_be_selected_without_judge_failure(
    client: TestClient, card: dict[str, Any]
) -> None:
    response = client.post(
        "/api/study/answer",
        json=answer_payload(card["id"], self_fallback=True, rating=1, is_correct=False),
    )
    assert response.status_code == 400
    assert (
        response_dict(client.get("/api/stats", params={"scope": "card", "id": card["id"]}))["total"]
        == 0
    )


def test_stt_failure_still_allows_text_answer(
    client: TestClient, card: dict[str, Any], fake_stt: FakeSTT
) -> None:
    enable_ai_assess(client)
    fake_stt.error = STTError("remote unavailable")
    response = client.post(
        "/api/study/transcribe",
        files={"audio": ("answer.webm", b"fake audio", "audio/webm")},
    )
    assert response.status_code == 502
    assert "type the answer instead" in response_dict(response)["detail"]

    answered = response_dict(client.post("/api/study/answer", json=answer_payload(card["id"])))
    assert answered["status"] == "reviewed"
    assert answered["mode"] == "ai_assess"


def test_deck_evaluation_mode_override(client: TestClient, card: dict[str, Any]) -> None:
    assert (
        client.patch(f"/api/decks/{card['deck_id']}", json={"eval_mode": "ai_assess"}).status_code
        == 200
    )
    result = response_dict(client.post("/api/study/answer", json=answer_payload(card["id"])))
    assert result["status"] == "reviewed"
    assert result["mode"] == "ai_assess"


def test_sm2_deck_scheduler_reschedules_low_rating(
    client: TestClient, db_session: Session, fake_judge: FakeJudge, alice: User
) -> None:
    enable_ai_assess(client)
    deck = response_dict(client.post("/api/decks", json={"name": "SM2", "scheduler": "sm2"}))
    card = response_dict(
        client.post(
            "/api/cards",
            json={"deck_id": deck["id"], "question": "Q", "answer": "A"},
        )
    )
    before = datetime.now(UTC)
    fake_judge.result = JudgeResult(rating=1, is_correct=False, feedback="Again")
    result = response_dict(client.post("/api/study/answer", json=answer_payload(card["id"])))
    due = datetime.fromisoformat(result["due"].replace("Z", "+00:00"))
    assert before + timedelta(hours=23) < due < before + timedelta(hours=25)
    state = db_session.get(CardState, (alice.id, card["id"]))
    assert state is not None
    assert state.scheduler == "sm2"
    assert state.state["repetitions"] == 0


def test_study_page_never_autofocuses_the_answer_field(client: TestClient) -> None:
    """A focused textarea raises the phone keyboard and hides the next card.

    The page must not carry `autofocus`, and study.js skips the focus call when the
    device has no fine pointer at all (see focusAnswer in the script).
    """
    page = client.get("/study").text

    assert 'id="answer-input"' in page
    assert "autofocus" not in page
    script = client.get("/static/js/study.js").text
    assert "(any-pointer: coarse)" in script
    assert "(any-pointer: fine)" in script
