from fastapi.testclient import TestClient

from tests.conftest import response_dict


def test_settings_defaults_and_update(client: TestClient) -> None:
    defaults = response_dict(client.get("/api/settings"))
    assert defaults["eval_mode"] == "ai_preselect"
    assert defaults["judge_language"] == "auto"
    assert defaults["voice_auto_judge"] is False
    assert defaults["teacher_enabled"] is True
    assert defaults["daily_new_limit"] == 0
    assert defaults["daily_review_limit"] == 0

    updated = response_dict(
        client.patch(
            "/api/settings",
            json={
                "eval_mode": "ai_assess",
                "judge_language": "fr",
                "stt_language": "en",
                "voice_auto_judge": True,
                "teacher_enabled": False,
                "daily_new_limit": 5,
                "daily_review_limit": 20,
            },
        )
    )
    assert updated["eval_mode"] == "ai_assess"
    assert updated["judge_language"] == "fr"
    assert updated["stt_language"] == "en"
    assert updated["voice_auto_judge"] is True
    assert updated["teacher_enabled"] is False
    assert updated["daily_new_limit"] == 5
    assert updated["daily_review_limit"] == 20


def test_settings_validation(client: TestClient) -> None:
    assert client.patch("/api/settings", json={"eval_mode": "self"}).status_code == 422
    assert client.patch("/api/settings", json={"daily_new_limit": -1}).status_code == 422
    assert client.patch("/api/settings", json={"judge_language": None}).status_code == 400
    assert client.patch("/api/settings", json={"voice_auto_judge": None}).status_code == 400
    assert client.patch("/api/settings", json={"teacher_enabled": None}).status_code == 400


def test_settings_form_updates_voice_auto_judge(client: TestClient) -> None:
    response = client.post(
        "/settings",
        data={
            "eval_mode": "ai_preselect",
            "judge_language": "auto",
            "stt_language": "auto",
            "voice_auto_judge": "true",
            "teacher_enabled": "true",
            "daily_new_limit": "0",
            "daily_review_limit": "0",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    settings = response_dict(client.get("/api/settings"))
    assert settings["voice_auto_judge"] is True
    assert settings["teacher_enabled"] is True
