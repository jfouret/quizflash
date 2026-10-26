from fastapi.testclient import TestClient

from tests.conftest import response_dict


def test_settings_defaults_and_update(client: TestClient) -> None:
    defaults = response_dict(client.get("/api/settings"))
    assert defaults["eval_mode"] == "ai_preselect"
    assert defaults["judge_language"] == "auto"
    assert defaults["daily_new_limit"] == 0
    assert defaults["daily_review_limit"] == 0

    updated = response_dict(
        client.patch(
            "/api/settings",
            json={
                "eval_mode": "ai_assess",
                "judge_language": "fr",
                "stt_language": "en",
                "daily_new_limit": 5,
                "daily_review_limit": 20,
            },
        )
    )
    assert updated["eval_mode"] == "ai_assess"
    assert updated["judge_language"] == "fr"
    assert updated["stt_language"] == "en"
    assert updated["daily_new_limit"] == 5
    assert updated["daily_review_limit"] == 20


def test_settings_validation(client: TestClient) -> None:
    assert client.patch("/api/settings", json={"eval_mode": "self"}).status_code == 422
    assert client.patch("/api/settings", json={"daily_new_limit": -1}).status_code == 422
    assert client.patch("/api/settings", json={"judge_language": None}).status_code == 400
