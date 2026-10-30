from datetime import timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import auth
from app.auth import AuthConfig
from app.models import AuthSession, User, utc_now
from tests.conftest import (
    BASE_URL,
    PASSWORD,
    FakeTeacher,
    make_user,
    new_client,
    response_dict,
)


def _sessions(app: FastAPI, user: User) -> list[AuthSession]:
    with Session(app.state.engine) as session:
        return list(session.exec(select(AuthSession).where(AuthSession.user_id == user.id)))


def test_session_cookie_is_hardened_and_stored_hashed(
    app: FastAPI, lifespan_client: TestClient, alice: User
) -> None:
    response = lifespan_client.post(
        "/login", data={"email": alice.email, "password": PASSWORD}, follow_redirects=False
    )
    assert response.status_code == 303
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-session=")
    for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert flag.lower() in cookie.lower()
    raw = lifespan_client.cookies["__Host-session"]
    stored = _sessions(app, alice)
    assert len(stored) == 1 and stored[0].token_hash != raw and raw not in stored[0].token_hash


def test_login_rotates_and_logout_revokes(app: FastAPI, alice: User) -> None:
    first = new_client(app, alice.email)
    old_token = first.cookies["__Host-session"]
    second = new_client(app, alice.email)
    assert second.get("/api/auth/me").status_code == 200

    # Re-login on the same browser replaces its previous session.
    first.post("/login", data={"email": alice.email, "password": PASSWORD})
    assert first.cookies["__Host-session"] != old_token
    stale = TestClient(app, base_url=BASE_URL, cookies={"__Host-session": old_token})
    assert stale.get("/api/auth/me").status_code == 401

    csrf = response_dict(second.get("/api/auth/me"))["csrf_token"]
    token = second.cookies["__Host-session"]
    assert (
        second.post("/logout", data={"csrf_token": csrf}, follow_redirects=False).status_code == 303
    )
    replay = TestClient(app, base_url=BASE_URL, cookies={"__Host-session": token})
    assert replay.get("/api/auth/me").status_code == 401
    assert first.get("/api/auth/me").status_code == 200


def test_bad_credentials_and_account_status(app: FastAPI, lifespan_client: TestClient) -> None:
    make_user(app, "pending@example.com", status="pending")
    make_user(app, "disabled@example.com", status="disabled")
    anon = new_client(app)
    bad = anon.post("/login", data={"email": "pending@example.com", "password": "wrong-password"})
    assert bad.status_code == 400
    unknown = anon.post("/login", data={"email": "ghost@example.com", "password": PASSWORD})
    assert unknown.status_code == 400 and unknown.text == bad.text.replace(
        "pending@example.com", "ghost@example.com"
    )
    for email, text in (("pending@example.com", "approval"), ("disabled@example.com", "suspended")):
        response = anon.post("/login", data={"email": email, "password": PASSWORD})
        assert response.status_code == 403 and text in response.text
        assert "__Host-session" not in anon.cookies


def test_login_throttle(app: FastAPI, alice: User) -> None:
    anon = new_client(app)
    for _ in range(5):
        assert anon.post("/login", data={"email": alice.email, "password": "x"}).status_code == 400
    blocked = anon.post("/login", data={"email": alice.email, "password": PASSWORD})
    assert blocked.status_code == 429


def test_csrf_and_origin_checks(client: TestClient) -> None:
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.get("/api/decks").status_code == 200
    assert client.post("/api/decks", json={"name": "x"}).status_code == 403
    wrong = client.post("/api/decks", json={"name": "x"}, headers={"X-CSRF-Token": "nope"})
    assert wrong.status_code == 403
    form = client.post("/decks", data={"name": "Form", "csrf_token": csrf}, follow_redirects=False)
    assert form.status_code == 303
    assert client.post("/decks", data={"name": "No token"}).status_code == 403
    cross = client.post(
        "/api/decks",
        json={"name": "x"},
        headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"},
    )
    assert cross.status_code == 403
    same = client.post(
        "/api/decks", json={"name": "ok"}, headers={"X-CSRF-Token": csrf, "Origin": BASE_URL}
    )
    assert same.status_code == 201
    login_cross = client.post(
        "/login",
        data={"email": "a@b.c", "password": "x"},
        headers={"Origin": "https://evil.example"},
    )
    assert login_cross.status_code == 403


def test_expired_and_idle_sessions_are_rejected(
    app: FastAPI, client: TestClient, alice: User
) -> None:
    for field, value in (
        ("expires_at", utc_now() - timedelta(seconds=1)),
        ("last_seen_at", utc_now() - timedelta(days=8)),
    ):
        login_client = new_client(app, alice.email)
        with Session(app.state.engine) as session:
            stored = session.exec(
                select(AuthSession).order_by(AuthSession.id.desc())  # type: ignore[union-attr]
            ).first()
            assert stored is not None
            setattr(stored, field, value)
            session.add(stored)
            session.commit()
        assert login_client.get("/api/auth/me").status_code == 401
        assert login_client.get("/", follow_redirects=False).headers["location"] == "/login"


def test_signup_respects_registration_policy(
    app: FastAPI, admin_client: TestClient, lifespan_client: TestClient
) -> None:
    anon = new_client(app)
    form = {"email": "new@example.com", "password": PASSWORD}
    assert anon.post("/signup", data={**form, "password": "short"}).status_code == 400

    pending = anon.post("/signup", data=form)
    assert pending.status_code == 200 and "approval" in pending.text
    assert "__Host-session" not in anon.cookies

    admin_client.patch("/api/admin/settings", json={"registration": "open"})
    opened = anon.post(
        "/signup", data={"email": "open@example.com", "password": PASSWORD}, follow_redirects=False
    )
    assert opened.status_code == 303
    assert response_dict(anon.get("/api/auth/me"))["user"]["role"] == "user"
    assert anon.post("/signup", data=form).status_code == 400  # duplicate email

    admin_client.patch("/api/admin/settings", json={"registration": "closed"})
    closed = new_client(app).post("/signup", data={"email": "c@example.com", "password": PASSWORD})
    assert closed.status_code == 403


def test_security_headers(client: TestClient) -> None:
    response = client.get("/")
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_password_hashing() -> None:
    stored = auth.hash_password(PASSWORD)
    assert stored.startswith("scrypt$") and PASSWORD not in stored
    assert auth.verify_password(PASSWORD, stored)
    assert not auth.verify_password(PASSWORD + "x", stored)
    assert not auth.verify_password(PASSWORD, None)
    assert auth.hash_password(PASSWORD) != stored


# --- OIDC ---------------------------------------------------------------------

OIDC = AuthConfig(
    cookie_secure=True,
    secret_key="test-secret",
    oidc_issuer="https://idp.example",
    oidc_client_id="quizdeck",
    oidc_client_secret="secret",
    oidc_role_claim="realm_access.roles",
    oidc_admin_role="quizdeck-admin",
)


def _claims(sub: str, *roles: str, email: str | None = None) -> dict[str, Any]:
    return {
        "iss": "https://idp.example",
        "sub": sub,
        "email": email or f"{sub}@example.com",
        "name": sub.title(),
        "realm_access": {"roles": list(roles)},
    }


class FakeOIDCClient:
    def __init__(self) -> None:
        self.claims: dict[str, Any] = {}

    async def authorize_access_token(self, _: Any) -> dict[str, Any]:
        return {"userinfo": self.claims}

    async def userinfo(self, token: Any) -> dict[str, Any]:
        return {}


def test_oidc_mode_disables_local_login_and_syncs_roles() -> None:
    from app.main import create_app

    app = create_app("sqlite://", teacher=FakeTeacher(), auth_config=OIDC)
    fake = FakeOIDCClient()
    app.state.oauth.oidc = fake
    with TestClient(app, base_url=BASE_URL) as client:
        assert (
            client.post("/login", data={"email": "a@b.c", "password": PASSWORD}).status_code == 404
        )
        assert client.get("/signup").status_code == 404
        assert (
            client.post("/signup", data={"email": "a@b.c", "password": PASSWORD}).status_code == 404
        )
        assert "/auth/oidc/login" in client.get("/login").text

        # Admin role comes from the IdP claim; admins skip approval.
        fake.claims = _claims("root", "quizdeck-admin")
        assert client.get("/auth/oidc/callback", follow_redirects=False).status_code == 303
        me = response_dict(client.get("/api/auth/me"))
        assert me["user"]["role"] == "admin"
        client.headers["X-CSRF-Token"] = me["csrf_token"]

        # Default registration policy is approval: new users wait.
        user_client = TestClient(app, base_url=BASE_URL)
        fake.claims = _claims("carol")
        assert user_client.get("/auth/oidc/callback").status_code == 403
        carol = next(
            u for u in client.get("/api/admin/users").json() if u["oidc_subject"] == "carol"
        )
        assert carol["status"] == "pending"
        assert (
            client.patch(f"/api/admin/users/{carol['id']}", json={"role": "admin"}).status_code
            == 403
        )
        assert (
            client.patch(f"/api/admin/users/{carol['id']}", json={"status": "active"}).status_code
            == 200
        )
        assert user_client.get("/auth/oidc/callback", follow_redirects=False).status_code == 303
        assert response_dict(user_client.get("/api/auth/me"))["user"]["role"] == "user"

        # Losing the IdP role demotes on next login and kills existing sessions.
        fake.claims = _claims("root")
        TestClient(app, base_url=BASE_URL).get("/auth/oidc/callback")
        assert client.get("/api/auth/me").status_code == 401


def test_oidc_never_links_by_email(app: FastAPI, alice: User) -> None:
    with Session(app.state.engine) as session:
        # Same email as an existing local account, different identity: refused.
        try:
            auth.provision_oidc_user(session, _claims("mallory", email=alice.email), OIDC)
        except PermissionError:
            pass
        else:
            raise AssertionError("OIDC login must not take over an account by email")
        first = auth.provision_oidc_user(session, _claims("dave"), OIDC)
        again = auth.provision_oidc_user(
            session, _claims("dave", email="changed@example.com"), OIDC
        )
        assert first.id == again.id
        other_issuer = {
            **_claims("dave", email="dave2@example.com"),
            "iss": "https://other.example",
        }
        assert auth.provision_oidc_user(session, other_issuer, OIDC).id != first.id
