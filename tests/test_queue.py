from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.crud import get_due
from app.models import CardState, User, utc_now
from tests.conftest import response_dict
from tests.test_study import answer_payload, enable_ai_assess


def test_due_order_and_daily_new_limit(
    client: TestClient, db_session: Session, deck: dict[str, Any], alice: User
) -> None:
    card_ids = []
    for index in range(2):
        created = client.post(
            "/api/cards",
            json={"deck_id": deck["id"], "question": f"Q{index}", "answer": "A"},
        )
        card_ids.append(response_dict(created)["id"])
    now = utc_now()
    first_state = db_session.get(CardState, (alice.id, card_ids[0]))
    second_state = db_session.get(CardState, (alice.id, card_ids[1]))
    assert first_state is not None and second_state is not None
    first_state.due = now + timedelta(seconds=1)
    second_state.due = now
    db_session.add(first_state)
    db_session.add(second_state)
    db_session.commit()

    assert [card.id for card, _ in get_due(db_session, alice, now=now + timedelta(seconds=2))] == [
        card_ids[1],
        card_ids[0],
    ]
    client.patch("/api/settings", json={"daily_new_limit": 1})
    limited = get_due(db_session, alice, now=now + timedelta(seconds=2))
    assert len(limited) == 1
    assert limited[0][0].id == card_ids[1]

    enable_ai_assess(client)
    answered = client.post("/api/study/answer", json=answer_payload(card_ids[1]))
    assert answered.status_code == 200
    db_session.expire_all()
    reviewed_state = db_session.get(CardState, (alice.id, card_ids[1]))
    assert reviewed_state is not None
    reviewed_state.due = now + timedelta(days=2)
    db_session.add(reviewed_state)
    db_session.commit()
    assert get_due(db_session, alice, now=now + timedelta(seconds=2)) == []

    client.patch("/api/settings", json={"daily_new_limit": 0})
    remaining = get_due(db_session, alice, now=now + timedelta(seconds=2))
    assert [card.id for card, _ in remaining] == [card_ids[0]]


def test_daily_review_limit_counts_non_new_reviews(
    client: TestClient, db_session: Session, card: dict[str, Any], alice: User
) -> None:
    enable_ai_assess(client)
    for _ in range(2):
        state = db_session.get(CardState, (alice.id, card["id"]))
        assert state is not None
        state.due = utc_now() - timedelta(seconds=1)
        db_session.add(state)
        db_session.commit()
        response = client.post("/api/study/answer", json=answer_payload(card["id"]))
        assert response.status_code == 200
        db_session.expire_all()

    client.patch("/api/settings", json={"daily_review_limit": 1})
    state = db_session.get(CardState, (alice.id, card["id"]))
    assert state is not None
    state.due = utc_now() - timedelta(seconds=1)
    db_session.add(state)
    db_session.commit()
    assert client.get("/api/study/next").json() is None

    client.patch("/api/settings", json={"daily_review_limit": 2})
    due = response_dict(client.get("/api/study/next"))
    assert due["card"]["id"] == card["id"]
    assert due["is_new"] is False
