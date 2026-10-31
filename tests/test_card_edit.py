"""Editing a card from the deck page."""

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import response_dict


def test_card_is_edited_through_the_form(
    client: TestClient, deck: dict[str, Any], card: dict[str, Any]
) -> None:
    response = client.post(
        f"/cards/{card['id']}/update",
        data={
            "deck_id": deck["id"],
            "question": "Capital of Italy?",
            "answer": "Rome",
            "details": "http://example.com",
            "context": "Card context",
            "expected_time_s": "30",
            "tags": "geography, italy",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303, response.text
    updated = response_dict(client.get(f"/api/cards/{card['id']}"))
    assert updated["question"] == "Capital of Italy?"
    assert updated["answer"] == "Rome"
    assert updated["expected_time_s"] == 30
    assert sorted(tag["name"] for tag in updated["tags"]) == ["geography", "italy"]


def test_blank_expected_time_clears_it(
    client: TestClient, deck: dict[str, Any], card: dict[str, Any]
) -> None:
    response = client.post(
        f"/cards/{card['id']}/update",
        data={
            "deck_id": deck["id"],
            "question": card["question"],
            "answer": card["answer"],
            "tags": "geography",
            "expected_time_s": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response_dict(client.get(f"/api/cards/{card['id']}"))["expected_time_s"] is None
