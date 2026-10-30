from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models import User
from tests.conftest import PASSWORD, make_user, new_client, response_dict, response_list


def _status(admin_client: TestClient, user: User, status: str) -> int:
    response = admin_client.patch(f"/api/admin/users/{user.id}", json={"status": status})
    return int(response.status_code)


def test_admin_validates_suspends_and_reactivates(app: FastAPI, admin_client: TestClient) -> None:
    pending = make_user(app, "pending@example.com", status="pending")
    users = response_list(admin_client.get("/api/admin/users"))
    assert {u["email"]: u["status"] for u in users}["pending@example.com"] == "pending"
    assert "password_hash" not in users[0]

    anon = new_client(app)
    assert (
        anon.post("/login", data={"email": pending.email, "password": PASSWORD}).status_code == 403
    )
    assert _status(admin_client, pending, "active") == 200
    user_client = new_client(app, pending.email)
    assert user_client.get("/api/auth/me").status_code == 200

    # Suspension kills live sessions immediately.
    assert _status(admin_client, pending, "disabled") == 200
    assert user_client.get("/api/auth/me").status_code == 401
    assert _status(admin_client, pending, "active") == 200
    assert new_client(app, pending.email).get("/api/auth/me").status_code == 200


def test_admin_delete_user_removes_their_content(
    app: FastAPI,
    admin_client: TestClient,
    client: TestClient,
    alice: User,
    client_b: TestClient,
    bob: User,
) -> None:
    deck = response_dict(client.post("/api/decks", json={"name": "A", "visibility": "public"}))
    client.post("/api/cards", json={"deck_id": deck["id"], "question": "Q", "answer": "A"})
    client_b.post(f"/api/decks/{deck['id']}/follow")
    assert client_b.get("/api/study/next").json() is not None
    client.post("/api/settings/tokens", json={"name": "t"})

    assert admin_client.delete(f"/api/admin/users/{alice.id}").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert client_b.get(f"/api/decks/{deck['id']}").status_code == 404
    assert client_b.get("/api/study/next").json() is None
    emails = {u["email"] for u in response_list(admin_client.get("/api/admin/users"))}
    assert alice.email not in emails and bob.email in emails


def test_admin_guards(app: FastAPI, admin: User, admin_client: TestClient, bob: User) -> None:
    assert (
        admin_client.patch(f"/api/admin/users/{admin.id}", json={"status": "disabled"}).status_code
        == 403
    )
    assert admin_client.delete(f"/api/admin/users/{admin.id}").status_code == 403
    assert (
        admin_client.patch(f"/api/admin/users/{bob.id}", json={"role": "admin"}).status_code == 200
    )
    bob_client = new_client(app, bob.email)
    # Bob is now admin; demoting Alice-the-admin works while another admin remains.
    assert (
        bob_client.patch(f"/api/admin/users/{admin.id}", json={"role": "user"}).status_code == 200
    )
    assert admin_client.get("/api/auth/me").status_code == 401  # role change revoked sessions
    assert response_list(bob_client.get("/api/admin/users"))
    assert admin_client.get("/api/admin/users").status_code == 401
    assert bob_client.patch(f"/api/admin/users/{bob.id}", json={"role": "user"}).status_code == 403
    assert bob_client.patch("/api/admin/users/999", json={"status": "active"}).status_code == 404


def test_admin_has_no_access_to_private_content(
    client: TestClient, admin_client: TestClient
) -> None:
    deck = response_dict(client.post("/api/decks", json={"name": "Private"}))
    assert admin_client.get(f"/api/decks/{deck['id']}").status_code == 404
    assert admin_client.post(f"/api/admin/decks/{deck['id']}/unpublish").status_code == 404


def test_app_settings_defaults_and_switches(
    app: FastAPI, admin_client: TestClient, client: TestClient, card: dict[str, object]
) -> None:
    assert response_dict(client.get("/api/settings"))["eval_mode"] == "ai_preselect"
    updated = response_dict(
        admin_client.patch(
            "/api/admin/settings",
            json={
                "teacher_allowed": False,
                "voice_allowed": False,
                "allow_public_decks": False,
                "default_settings": {"eval_mode": "ai_assess", "daily_new_limit": 7},
            },
        )
    )
    assert updated["default_settings"] == {"eval_mode": "ai_assess", "daily_new_limit": 7}
    newcomer = new_client(app, make_user(app, "new@example.com").email)
    settings = response_dict(newcomer.get("/api/settings"))
    assert settings["eval_mode"] == "ai_assess" and settings["daily_new_limit"] == 7
    assert response_dict(client.get("/api/settings"))["eval_mode"] == "ai_preselect"

    assert client.post("/api/study/explain", json={"card_id": card["id"]}).status_code == 403
    audio = {"audio": ("a.webm", b"x", "audio/webm")}
    assert client.post("/api/study/transcribe", files=audio).status_code == 403
    assert "Record voice" in client.get("/study").text  # rendered but hidden
    assert 'id="record" type="button" class="secondary" hidden' in client.get("/study").text
    public = client.patch(f"/api/decks/{card['deck_id']}", json={"visibility": "public"})
    assert public.status_code == 403
    assert client.post("/api/decks", json={"name": "P", "visibility": "public"}).status_code == 403


def test_admin_unpublish_and_pages(client: TestClient, admin_client: TestClient, bob: User) -> None:
    deck = response_dict(client.post("/api/decks", json={"name": "Pub", "visibility": "public"}))
    page = admin_client.get("/admin")
    assert page.status_code == 200 and bob.email in page.text and "Pub" in page.text
    assert (
        admin_client.post(
            f"/admin/decks/{deck['id']}/unpublish", follow_redirects=False
        ).status_code
        == 303
    )
    assert response_dict(client.get(f"/api/decks/{deck['id']}"))["visibility"] == "private"
    suspend = admin_client.post(
        f"/admin/users/{bob.id}", data={"action": "suspend"}, follow_redirects=False
    )
    assert suspend.status_code == 303
    users = {u["email"]: u for u in response_list(admin_client.get("/api/admin/users"))}
    assert users[bob.email]["status"] == "disabled"
