"""Security regression tests: no unauthenticated access, everywhere, in both auth modes.

The route lists come from the app itself, so a new route or MCP tool without an
access decision fails the suite instead of shipping open.
"""

import asyncio
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import pytest
from authlib.integrations.base_client.errors import OAuthError
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from fastmcp import Client
from sqlmodel import Session

from app import auth
from app.auth import AuthConfig
from app.main import ROUTERS, create_app
from app.models import User
from tests.conftest import (
    BASE_URL,
    FakeTeacher,
    make_user,
    mcp_call,
    mcp_token,
    new_client,
    response_dict,
    response_list,
)

PASSWORD = "correct horse battery staple"

# Routes that must work without a session. Everything else must refuse anonymous calls.
PUBLIC_ROUTES = {
    ("GET", "/healthz"),
    ("GET", "/login"),
    ("POST", "/login"),
    ("GET", "/signup"),
    ("POST", "/signup"),
    ("GET", "/auth/oidc/login"),
    ("GET", "/auth/oidc/callback"),
    ("GET", "/openapi.json"),
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/redoc"),
}

MCP_PROTOCOL_METHODS = [
    "initialize",
    "ping",
    "tools/list",
    "tools/call",
    "resources/list",
    "resources/templates/list",
    "prompts/list",
    "logging/setLevel",
]

# Every MCP tool, listed on purpose: a new tool must be added here after deciding
# who may call it. All of them require a personal token.
KNOWN_MCP_TOOLS = {
    "list_decks",
    "get_deck",
    "create_deck",
    "update_deck",
    "delete_deck",
    "list_cards",
    "get_card",
    "create_card",
    "update_card",
    "delete_card",
    "list_tags",
    "list_due",
    "get_stats",
    "explain_card",
    "list_public_decks",
    "follow_deck",
    "copy_deck",
}

OIDC = AuthConfig(
    cookie_secure=True,
    secret_key="test-secret",
    oidc_issuer="https://idp.example",
    oidc_client_id="quizdeck",
    oidc_client_secret="secret",
    oidc_role_claim="realm_access.roles",
    oidc_admin_role="quizdeck-admin",
)


def _claims(sub: str, *roles: str) -> dict[str, Any]:
    return {
        "iss": "https://idp.example",
        "sub": sub,
        "email": f"{sub}@example.com",
        "name": sub.title(),
        "realm_access": {"roles": list(roles)},
    }


class FakeOIDC:
    """Mimics authlib: a bad state or an IdP error never yields a token."""

    def __init__(self) -> None:
        self.claims: dict[str, Any] = {}

    async def authorize_access_token(self, request: Any) -> dict[str, Any]:
        if request.query_params.get("error"):
            raise OAuthError(error=request.query_params["error"])
        if request.query_params.get("state") != "expected":
            raise OAuthError(error="invalid_state")
        return {"userinfo": self.claims}

    async def userinfo(self, token: Any) -> dict[str, Any]:
        return {}


def _route_calls() -> list[tuple[str, str]]:
    """Every route with its path parameters filled with a plausible ID."""
    calls: list[tuple[str, str]] = []
    for router in ROUTERS:
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in sorted(route.methods or ()):
                if method in {"HEAD", "OPTIONS"}:
                    continue
                path = (
                    route.path.replace("{token_id}", "1")
                    .replace("{user_id}", "1")
                    .replace("{deck_id}", "1")
                    .replace("{card_id}", "1")
                    .replace("{tag_id}", "1")
                )
                calls.append((method, path))
    calls += [
        ("GET", "/openapi.json"),
        ("GET", "/docs"),
        ("GET", "/docs/oauth2-redirect"),
        ("GET", "/redoc"),
    ]
    return calls


def _local_app() -> FastAPI:
    return create_app(
        "sqlite://",
        teacher=FakeTeacher(),
        auth_config=AuthConfig(cookie_secure=True, secret_key="test-secret"),
    )


def _oidc_app() -> tuple[FastAPI, FakeOIDC]:
    application = create_app("sqlite://", teacher=FakeTeacher(), auth_config=OIDC)
    fake = FakeOIDC()
    application.state.oauth.oidc = fake
    return application, fake


@pytest.fixture
def oidc() -> Iterator[tuple[FastAPI, FakeOIDC, TestClient]]:
    application, fake = _oidc_app()
    with TestClient(application, base_url=BASE_URL) as client:
        yield application, fake, client


def _is_public(method: str, path: str) -> bool:
    return (method, path) in PUBLIC_ROUTES


def _assert_denied(method: str, path: str, response: Any) -> None:
    if path.startswith(("/api", "/mcp")):
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
    else:
        assert response.status_code == 303, f"{method} {path} -> {response.status_code}"
        assert response.headers["location"] == "/login", f"{method} {path}"


def test_every_route_denies_anonymous_access_local_mode() -> None:
    app = _local_app()
    with TestClient(app, base_url=BASE_URL) as client:
        failures = []
        for method, path in _route_calls():
            if _is_public(method, path):
                continue
            response = client.request(method, path, follow_redirects=False)
            try:
                _assert_denied(method, path, response)
            except AssertionError as exc:
                failures.append(str(exc))
        assert failures == []


def test_every_route_denies_anonymous_access_oidc_mode(
    oidc: tuple[FastAPI, FakeOIDC, TestClient],
) -> None:
    _, _, client = oidc
    failures = []
    for method, path in _route_calls():
        if _is_public(method, path):
            continue
        response = client.request(method, path, follow_redirects=False)
        try:
            _assert_denied(method, path, response)
        except AssertionError as exc:
            failures.append(str(exc))
    assert failures == []


def test_public_routes_are_reachable_without_a_session(
    oidc: tuple[FastAPI, FakeOIDC, TestClient],
) -> None:
    _, _, client = oidc
    assert client.get("/healthz").status_code == 200
    assert client.get("/login").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_mcp_denies_every_protocol_method_without_a_token(
    lifespan_client: TestClient,
) -> None:
    headers = {"Accept": "application/json, text/event-stream"}
    for method in MCP_PROTOCOL_METHODS:
        response = lifespan_client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": {}},
            headers=headers,
        )
        assert response.status_code == 401, f"{method} -> {response.status_code}"


def test_mcp_denies_every_tool_without_a_token(lifespan_client: TestClient) -> None:
    for tool in sorted(KNOWN_MCP_TOOLS):
        assert mcp_call(lifespan_client, None, tool).status_code == 401, tool


def test_mcp_tool_list_is_reviewed(app: FastAPI, lifespan_client: TestClient) -> None:
    async def list_tools() -> set[str]:
        async with Client(app.state.mcp) as mcp_client:
            return {tool.name for tool in await mcp_client.list_tools()}

    assert asyncio.run(list_tools()) == KNOWN_MCP_TOOLS


@pytest.mark.parametrize(
    "authorization",
    [
        "",
        "Bearer",
        "Bearer ",
        "Bearer qd_",
        "Bearer qd_not-a-real-token",
        "Bearer " + "a" * 5000,
        "Basic cTpk",
        "Token qd_abc",
    ],
)
def test_mcp_rejects_malformed_tokens(lifespan_client: TestClient, authorization: str) -> None:
    response = lifespan_client.post(
        "/mcp/",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={
            "Accept": "application/json, text/event-stream",
            "Authorization": authorization,
        },
    )
    assert response.status_code == 401


def test_mcp_rejects_tokens_in_the_query_string(lifespan_client: TestClient) -> None:
    response = lifespan_client.post(
        "/mcp/?token=qd_abc&access_token=qd_abc",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert response.status_code == 401


def test_mcp_rejects_browser_cookies(client: TestClient) -> None:
    # `client` carries a valid session cookie for a real user.
    assert client.get("/api/auth/me").status_code == 200
    assert mcp_call(client, None, "list_decks").status_code == 401


def test_revoked_and_suspended_tokens_are_rejected(
    app: FastAPI, client: TestClient, client_b: TestClient, bob: User
) -> None:
    token = mcp_token(client)
    assert mcp_call(client, token, "list_decks").status_code == 200

    tokens = response_list(client.get("/api/settings/tokens"))
    assert client.delete(f"/api/settings/tokens/{tokens[0]['id']}").status_code == 204
    assert mcp_call(client, token, "list_decks").status_code == 401

    bob_token = mcp_token(client_b)
    with Session(app.state.engine) as session:
        user = session.get(User, bob.id)
        assert user is not None
        user.status = "disabled"
        session.add(user)
        session.commit()
    assert mcp_call(client_b, bob_token, "list_decks").status_code == 401


def test_pending_and_deleted_users_hold_no_valid_token(
    app: FastAPI, admin_client: TestClient, lifespan_client: TestClient
) -> None:
    pending = make_user(app, "pending@example.com", status="pending")
    with Session(app.state.engine) as session:
        _, raw = auth.create_api_token(session, pending, "pending agent")
    assert mcp_call(lifespan_client, raw, "list_decks").status_code == 401

    victim = make_user(app, "victim@example.com")
    with Session(app.state.engine) as session:
        _, raw = auth.create_api_token(session, victim, "victim agent")
    assert mcp_call(lifespan_client, raw, "list_decks").status_code == 200
    assert admin_client.delete(f"/api/admin/users/{victim.id}").status_code == 204
    assert mcp_call(lifespan_client, raw, "list_decks").status_code == 401


def test_admin_token_cannot_read_private_content(
    client: TestClient, admin_client: TestClient
) -> None:
    deck = response_dict(client.post("/api/decks", json={"name": "Alice private"}))
    admin_token = mcp_token(admin_client)
    result = mcp_call(admin_client, admin_token, "get_deck", {"deck_id": deck["id"]}).json()
    assert result["result"]["isError"] is True
    assert mcp_tool_list(admin_client, admin_token) == []


def mcp_tool_list(client: TestClient, token: str) -> list[dict[str, Any]]:
    response = mcp_call(client, token, "list_decks")
    assert response.status_code == 200
    data = response.json()["result"]["structuredContent"]
    assert isinstance(data, dict)
    result = data["result"]
    assert isinstance(result, list)
    return result


def test_rest_api_rejects_bearer_tokens(app: FastAPI, client: TestClient) -> None:
    token = mcp_token(client)
    anon = TestClient(app, base_url=BASE_URL)
    for path in ("/api/decks", "/api/settings", "/api/auth/me", "/api/admin/users"):
        response = anon.get(path, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, path
    # The session cookie, never the header, is what authenticates the REST API.
    assert client.get("/api/decks", headers={"Authorization": "Bearer garbage"}).status_code == 200


def test_csrf_token_is_required_on_every_unsafe_route(
    client: TestClient, anon_client: TestClient
) -> None:
    failures = []
    for method, path in _route_calls():
        if method in {"GET", "HEAD", "OPTIONS"} or _is_public(method, path):
            continue
        response = client.request(
            method, path, json={}, follow_redirects=False, headers={"X-CSRF-Token": ""}
        )
        if response.status_code != 403:
            failures.append(f"{method} {path} -> {response.status_code}")
    assert failures == []


def test_cross_origin_unsafe_requests_are_rejected(client: TestClient) -> None:
    csrf = client.headers["X-CSRF-Token"]
    response = client.post(
        "/api/decks",
        json={"name": "x"},
        headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert response_list(client.get("/api/decks")) == []


def test_session_cookie_edge_cases(app: FastAPI) -> None:
    other = _local_app()
    with TestClient(other, base_url=BASE_URL) as other_client:
        make_user(other, "alice@example.com")
        login = other_client.post(
            "/login",
            data={"email": "alice@example.com", "password": PASSWORD},
            follow_redirects=False,
        )
        assert login.status_code == 303
        foreign_token = other_client.cookies["__Host-session"]

    with TestClient(app, base_url=BASE_URL):
        make_user(app, "alice@example.com")
        valid = new_client(app, "alice@example.com")
        mcp = mcp_token(valid)
        cases = {
            "random": "not-a-session",
            "empty": "",
            "oversized": "a" * 10_000,
            "foreign app": foreign_token,
            "mcp token": mcp,
            "sql injection": "' OR 1=1 --",
        }
        for label, value in cases.items():
            probe = TestClient(app, base_url=BASE_URL, cookies={"__Host-session": value})
            assert probe.get("/api/auth/me").status_code == 401, label
        wrong_name = TestClient(app, base_url=BASE_URL, cookies={"quizdeck_session": foreign_token})
        assert wrong_name.get("/api/auth/me").status_code == 401


def test_static_files_cannot_escape_the_static_directory(client: TestClient) -> None:
    for path in (
        "/static/../app/auth.py",
        "/static/%2e%2e/app/auth.py",
        "/static/..%2fapp%2fauth.py",
        f"/static/{quote('../app/auth.py')}",
    ):
        assert client.get(path).status_code == 404, path


def test_security_headers_are_set(client: TestClient) -> None:
    response = client.get("/")
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "same-origin"
    assert "microphone=(self)" in response.headers["permissions-policy"]
    assert "max-age=31536000" in response.headers["strict-transport-security"]
    csp = response.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp
    assert "frame-ancestors 'none'" in csp
    assert response.headers["cache-control"] == "no-store"


def test_api_docs_get_a_relaxed_but_bounded_policy(client: TestClient) -> None:
    csp = client.get("/docs").headers["content-security-policy"]
    assert "https://cdn.jsdelivr.net" in csp
    assert "object-src 'none'" in csp


INLINE_SCRIPT = r"<script(?![^>]*\bsrc=)"
INLINE_HANDLER = r"\son(?:click|load|error|change|submit|input|keydown|focus|blur|mouseover)\s*="
INLINE_STYLE = r"\sstyle\s*="


def test_pages_contain_no_inline_script_or_style(
    client: TestClient, admin_client: TestClient, deck: dict[str, Any]
) -> None:
    import re

    pages = {
        "index": client.get("/"),
        "study": client.get("/study"),
        "explore": client.get("/explore"),
        "settings": client.get("/settings"),
        "deck": client.get(f"/decks/{deck['id']}"),
        "admin": admin_client.get("/admin"),
        "login": client.get("/login"),
    }
    for name, response in pages.items():
        assert response.status_code == 200, name
        html = response.text
        assert not re.search(INLINE_SCRIPT, html), f"{name} has an inline <script>"
        assert not re.search(INLINE_HANDLER, html), f"{name} has an inline event handler"
        assert not re.search(INLINE_STYLE, html), f"{name} has an inline style attribute"


def test_oidc_callback_rejects_forged_state(
    oidc: tuple[FastAPI, FakeOIDC, TestClient],
) -> None:
    _, fake, client = oidc
    fake.claims = _claims("root", "quizdeck-admin")
    for query in ("?code=abc&state=forged", "?code=abc", "?error=access_denied"):
        response = client.get(f"/auth/oidc/callback{query}", follow_redirects=False)
        assert response.status_code == 400, query
        assert "__Host-session" not in response.headers.get("set-cookie", "")
    assert client.get("/api/auth/me").status_code == 401


def test_oidc_pending_and_disabled_users_get_no_session(
    oidc: tuple[FastAPI, FakeOIDC, TestClient],
) -> None:
    app, fake, admin = oidc
    fake.claims = _claims("root", "quizdeck-admin")
    assert (
        admin.get("/auth/oidc/callback?state=expected", follow_redirects=False).status_code == 303
    )
    admin.headers["X-CSRF-Token"] = response_dict(admin.get("/api/auth/me"))["csrf_token"]

    fake.claims = _claims("carol")
    with TestClient(app, base_url=BASE_URL) as carol:
        assert carol.get("/auth/oidc/callback?state=expected").status_code == 403
        assert "__Host-session" not in carol.cookies

    fake.claims = _claims("dave", "quizdeck-admin")
    with TestClient(app, base_url=BASE_URL) as dave:
        assert (
            dave.get("/auth/oidc/callback?state=expected", follow_redirects=False).status_code
            == 303
        )
        users = {u["oidc_subject"]: u for u in response_list(admin.get("/api/admin/users"))}
        assert (
            admin.patch(
                f"/api/admin/users/{users['dave']['id']}", json={"status": "disabled"}
            ).status_code
            == 200
        )
        fake.claims = _claims("dave", "quizdeck-admin")
        probe = TestClient(app, base_url=BASE_URL)
        assert probe.get("/auth/oidc/callback?state=expected").status_code == 403


def test_oidc_mode_disables_password_endpoints(
    oidc: tuple[FastAPI, FakeOIDC, TestClient],
) -> None:
    _, _, client = oidc
    assert client.post("/login", data={"email": "a@b.c", "password": PASSWORD}).status_code == 404
    assert client.get("/signup").status_code == 404
    assert client.post("/signup", data={"email": "a@b.c", "password": PASSWORD}).status_code == 404
