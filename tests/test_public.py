from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import __version__
from app.models import CardState, User
from app.templating import templates
from tests.conftest import response_dict, response_list
from tests.test_study import answer_payload, enable_ai_assess


def test_footer_shows_version_and_build_tag(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(templates.env.globals, "build_tag", "9.9.9-2026-01-01")

    html = client.get("/login").text

    assert f"QuizDeck v{__version__}" in html
    assert "build 9.9.9-2026-01-01" in html


def _public_deck(client: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    deck = response_dict(client.post("/api/decks", json={"name": "Shared", "visibility": "public"}))
    card = response_dict(
        client.post(
            "/api/cards",
            json={"deck_id": deck["id"], "question": "Q?", "answer": "A", "tags": ["shared"]},
        )
    )
    return deck, card


def test_follow_trains_without_ownership(
    app: FastAPI, client: TestClient, client_b: TestClient, alice: User, bob: User
) -> None:
    deck, card = _public_deck(client)
    listed = response_list(client_b.get("/api/public/decks"))
    assert [(d["id"], d["card_count"], d["following"]) for d in listed] == [(deck["id"], 1, False)]

    # Readable before following, but not trainable.
    assert client_b.get(f"/api/decks/{deck['id']}").status_code == 200
    assert client_b.post("/api/study/answer", json=answer_payload(card["id"])).status_code == 403
    assert client_b.get("/api/study/next").json() is None

    assert client_b.post(f"/api/decks/{deck['id']}/follow").status_code == 200
    assert [d["id"] for d in response_list(client_b.get("/api/decks"))] == [deck["id"]]
    assert response_dict(client_b.get("/api/study/next"))["card"]["id"] == card["id"]

    enable_ai_assess(client_b)
    reviewed = client_b.post("/api/study/answer", json=answer_payload(card["id"]))
    assert response_dict(reviewed)["status"] == "reviewed"

    # Schedules and stats are per learner.
    assert alice.id is not None and bob.id is not None
    with Session(app.state.engine) as session:
        states = {s.user_id: s for s in session.exec(select(CardState))}
    assert states[bob.id].last_review is not None
    assert states[alice.id].last_review is None
    assert response_dict(client.get("/api/study/next"))["card"]["id"] == card["id"]
    assert response_dict(client_b.get(f"/api/stats?scope=deck&id={deck['id']}"))["total"] == 1
    assert response_dict(client.get(f"/api/stats?scope=deck&id={deck['id']}"))["total"] == 0
    tag_id = card["tags"][0]["id"]
    assert response_dict(client_b.get(f"/api/stats?scope=tag&id={tag_id}"))["total"] == 1

    # Follower cannot edit the owner's content.
    assert client_b.patch(f"/api/decks/{deck['id']}", json={"name": "x"}).status_code == 403
    assert client_b.delete(f"/api/decks/{deck['id']}").status_code == 403
    new_card = {"deck_id": deck["id"], "question": "Q", "answer": "A"}
    assert client_b.post("/api/cards", json=new_card).status_code == 403
    assert client_b.patch(f"/api/cards/{card['id']}", json={"answer": "x"}).status_code == 403
    assert client_b.delete(f"/api/cards/{card['id']}").status_code == 403
    assert client_b.delete(f"/api/tags/{tag_id}").status_code == 404
    assert client.post(f"/api/decks/{deck['id']}/follow").status_code == 400

    # Owner updates are visible to followers.
    client.patch(f"/api/cards/{card['id']}", json={"answer": "Updated"})
    assert response_dict(client_b.get(f"/api/cards/{card['id']}"))["answer"] == "Updated"

    # Unpublishing cuts access; unfollow then works only while following.
    client.patch(f"/api/decks/{deck['id']}", json={"visibility": "private"})
    assert client_b.get(f"/api/decks/{deck['id']}").status_code == 404
    assert response_list(client_b.get("/api/decks")) == []
    assert response_list(client_b.get("/api/cards")) == []
    assert client_b.post("/api/study/answer", json=answer_payload(card["id"])).status_code == 404

    # Deleting the deck removes every learner's progress without FK errors.
    assert client.delete(f"/api/decks/{deck['id']}").status_code == 204
    with Session(app.state.engine) as session:
        assert list(session.exec(select(CardState))) == []


def test_copy_creates_an_independent_private_deck(
    client: TestClient, client_b: TestClient, bob: User
) -> None:
    deck, card = _public_deck(client)
    copy = response_dict(client_b.post(f"/api/decks/{deck['id']}/copy"))
    assert copy["owner_id"] == bob.id
    assert copy["visibility"] == "private"
    assert copy["source_deck_id"] == deck["id"]
    cards = response_list(client_b.get(f"/api/cards?deck_id={copy['id']}"))
    assert [(c["question"], [t["name"] for t in c["tags"]]) for c in cards] == [("Q?", ["shared"])]
    assert cards[0]["tags"][0]["id"] != card["tags"][0]["id"]

    client_b.patch(f"/api/cards/{cards[0]['id']}", json={"answer": "Bob's"})
    assert response_dict(client.get(f"/api/cards/{card['id']}"))["answer"] == "A"
    assert client.get(f"/api/decks/{copy['id']}").status_code == 404
    assert response_dict(client_b.get("/api/study/next"))["card"]["id"] == cards[0]["id"]


def test_public_pages(client: TestClient, client_b: TestClient) -> None:
    deck, _ = _public_deck(client)
    explore = client_b.get("/explore")
    assert explore.status_code == 200 and "Shared" in explore.text
    assert "Follow" in client_b.get(f"/decks/{deck['id']}").text
    follow = client_b.post(f"/decks/{deck['id']}/follow", follow_redirects=False)
    assert follow.status_code == 303
    copy = client_b.post(f"/decks/{deck['id']}/copy", follow_redirects=False)
    assert copy.status_code == 303 and copy.headers["location"] != f"/decks/{deck['id']}"
    assert client_b.post(f"/decks/{deck['id']}/unfollow", follow_redirects=False).status_code == 303
