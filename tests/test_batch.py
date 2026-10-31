from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import FakeTeacher, FakeTTS, response_dict, response_list


def _make_cards(client: TestClient, deck_id: int, count: int) -> list[dict[str, Any]]:
    cards = []
    for i in range(count):
        response = client.post(
            "/api/cards",
            json={"deck_id": deck_id, "question": f"Q{i}", "answer": f"A{i}"},
        )
        assert response.status_code == 201, response.text
        cards.append(response_dict(response))
    return cards


def test_batch_returns_up_to_size(client: TestClient, deck: dict[str, Any]) -> None:
    _make_cards(client, deck["id"], 6)

    batch = response_list(client.get("/api/study/batch?size=4"))

    assert len(batch) == 4
    assert sorted(item["card"]["question"] for item in batch) == ["Q0", "Q1", "Q2", "Q3"]


def test_batch_caps_size(client: TestClient, deck: dict[str, Any]) -> None:
    _make_cards(client, deck["id"], 3)

    assert len(response_list(client.get("/api/study/batch?size=999"))) == 3


def test_batch_empty_when_nothing_due(client: TestClient) -> None:
    assert response_list(client.get("/api/study/batch")) == []


def test_batch_filters_by_deck(client: TestClient, deck: dict[str, Any]) -> None:
    other = response_dict(client.post("/api/decks", json={"name": "Other"}))
    _make_cards(client, deck["id"], 2)
    _make_cards(client, other["id"], 3)

    batch = response_list(client.get(f"/api/study/batch?deck_id={deck['id']}"))

    assert len(batch) == 2


def test_speak_text_returns_audio(client: TestClient, fake_tts: FakeTTS) -> None:
    client.patch("/api/settings", json={"tts_enabled": True})

    response = client.post("/api/study/speak", json={"text": "Bonjour", "vocal": False})

    assert response.status_code == 200
    assert response.content == b"FAKEAUDIO"
    assert response.headers["Content-Type"].startswith("audio/mpeg")
    assert fake_tts.calls == [("Bonjour", "auto")]


def test_speak_text_runs_the_vocal_pass(
    client: TestClient, fake_tts: FakeTTS, fake_teacher: FakeTeacher
) -> None:
    client.patch("/api/settings", json={"tts_enabled": True, "judge_language": "fr"})

    response = client.post("/api/study/speak", json={"text": "Bonjour", "vocal": True})

    assert response.status_code == 200
    assert fake_teacher.vocal_calls == [{"text": "Bonjour", "language": "fr"}]
    assert fake_tts.calls == [("Vocal: Bonjour", "fr")]


def test_speak_text_requires_tts_enabled(client: TestClient) -> None:
    response = client.post("/api/study/speak", json={"text": "Bonjour"})

    assert response.status_code == 403


def test_study_page_exposes_batch_config(client: TestClient) -> None:
    html = client.get("/study").text

    assert 'data-batch-enabled="true"' in html
    assert 'data-batch-size="5"' in html
    assert 'id="batch-progress"' in html
    assert 'id="start-panel"' in html
    assert 'id="start-study"' in html
    assert 'id="batch-done"' in html
    assert 'id="batch-continue"' in html
    assert 'id="batch-menu"' in html


def test_study_tags_lists_available_tags(client: TestClient, deck: dict[str, Any]) -> None:
    _make_cards(client, deck["id"], 1)
    client.post(
        "/api/cards",
        json={"deck_id": deck["id"], "question": "T", "answer": "A", "tags": ["alpha", "beta"]},
    )

    assert client.get("/api/study/tags").json() == ["alpha", "beta"]


def test_batch_filters_by_tag(client: TestClient, deck: dict[str, Any]) -> None:
    _make_cards(client, deck["id"], 3)
    client.post(
        "/api/cards",
        json={"deck_id": deck["id"], "question": "Tagged", "answer": "A", "tags": ["target"]},
    )

    batch = response_list(client.get("/api/study/batch?size=10&tag=target"))

    assert [item["card"]["question"] for item in batch] == ["Tagged"]


def test_next_filters_by_tag(client: TestClient, deck: dict[str, Any]) -> None:
    _make_cards(client, deck["id"], 3)
    client.post(
        "/api/cards",
        json={"deck_id": deck["id"], "question": "Tagged", "answer": "A", "tags": ["target"]},
    )

    card = response_dict(client.get("/api/study/next?tag=target"))

    assert card["card"]["question"] == "Tagged"


def test_settings_page_exposes_batch_controls(client: TestClient) -> None:
    html = client.get("/settings").text

    assert 'name="batch_enabled"' in html
    assert 'name="batch_size"' in html
