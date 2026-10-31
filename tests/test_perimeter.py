"""User perimeter: nobody but the owner can see or change private content.

Every HTTP route must be listed in exactly one category below; the coverage test fails
when a new route is added without deciding who may call it.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import ROUTERS
from app.models import User
from tests.conftest import make_user, new_client, response_dict, response_list
from tests.test_study import answer_payload


@dataclass(frozen=True)
class Call:
    method: str
    path: str
    json: dict[str, Any] | None = None
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class Victim:
    deck: int
    card: int
    tag: int


def _resource_calls(v: Victim) -> dict[tuple[str, str], Call]:
    """Routes acting on one resource; an outsider must get 404 for a private one."""
    answer = answer_payload(v.card)
    return {
        ("GET", "/api/decks/{deck_id}"): Call("GET", f"/api/decks/{v.deck}"),
        ("PATCH", "/api/decks/{deck_id}"): Call(
            "PATCH", f"/api/decks/{v.deck}", json={"name": "pwned"}
        ),
        ("DELETE", "/api/decks/{deck_id}"): Call("DELETE", f"/api/decks/{v.deck}"),
        ("POST", "/api/decks/{deck_id}/follow"): Call("POST", f"/api/decks/{v.deck}/follow"),
        ("DELETE", "/api/decks/{deck_id}/follow"): Call("DELETE", f"/api/decks/{v.deck}/follow"),
        ("POST", "/api/decks/{deck_id}/copy"): Call("POST", f"/api/decks/{v.deck}/copy"),
        ("POST", "/api/cards"): Call(
            "POST", "/api/cards", json={"deck_id": v.deck, "question": "Q", "answer": "A"}
        ),
        ("GET", "/api/cards/{card_id}"): Call("GET", f"/api/cards/{v.card}"),
        ("PATCH", "/api/cards/{card_id}"): Call(
            "PATCH", f"/api/cards/{v.card}", json={"answer": "pwned"}
        ),
        ("DELETE", "/api/cards/{card_id}"): Call("DELETE", f"/api/cards/{v.card}"),
        ("DELETE", "/api/tags/{tag_id}"): Call("DELETE", f"/api/tags/{v.tag}"),
        ("GET", "/api/stats"): Call("GET", f"/api/stats?scope=deck&id={v.deck}"),
        ("POST", "/api/study/answer"): Call("POST", "/api/study/answer", json=answer),
        ("POST", "/api/study/explain"): Call(
            "POST", "/api/study/explain", json={"card_id": v.card}
        ),
        ("POST", "/api/study/speak-question"): Call(
            "POST", "/api/study/speak-question", json={"card_id": v.card}
        ),
        ("POST", "/api/study/speak-explanation"): Call(
            "POST", "/api/study/speak-explanation", json={"card_id": v.card}
        ),
        ("GET", "/decks/{deck_id}"): Call("GET", f"/decks/{v.deck}"),
        ("POST", "/decks/{deck_id}/update"): Call(
            "POST", f"/decks/{v.deck}/update", data={"description": "pwned"}
        ),
        ("POST", "/decks/{deck_id}/delete"): Call("POST", f"/decks/{v.deck}/delete"),
        ("POST", "/decks/{deck_id}/follow"): Call("POST", f"/decks/{v.deck}/follow"),
        ("POST", "/decks/{deck_id}/unfollow"): Call("POST", f"/decks/{v.deck}/unfollow"),
        ("POST", "/decks/{deck_id}/copy"): Call("POST", f"/decks/{v.deck}/copy"),
        ("POST", "/decks/{deck_id}/cards"): Call(
            "POST", f"/decks/{v.deck}/cards", data={"question": "Q", "answer": "A"}
        ),
        ("POST", "/cards/{card_id}/delete"): Call(
            "POST", f"/cards/{v.card}/delete", data={"deck_id": v.deck}
        ),
        ("POST", "/cards/{card_id}/update"): Call(
            "POST",
            f"/cards/{v.card}/update",
            data={"deck_id": v.deck, "question": "Q", "answer": "A"},
        ),
    }


# Extra probes for routes whose resource is passed by query string.
EXTRA_PROBES: list[Callable[[Victim], Call]] = [
    lambda v: Call("GET", f"/api/cards?deck_id={v.deck}"),
    lambda v: Call("GET", f"/api/stats?scope=card&id={v.card}"),
    lambda v: Call("GET", f"/api/stats?scope=tag&id={v.tag}"),
    lambda v: Call("GET", f"/api/study/next?deck_id={v.deck}"),
    lambda v: Call("GET", f"/api/study/batch?deck_id={v.deck}"),
    lambda v: Call("GET", f"/api/study/tags?deck_id={v.deck}"),
    lambda v: Call("GET", f"/api/study/due?deck_id={v.deck}"),
    lambda v: Call("GET", f"/api/stats/breakdown?group=card&deck_id={v.deck}"),
    lambda v: Call("GET", f"/api/history?deck_id={v.deck}"),
    lambda v: Call("GET", f"/study?deck_id={v.deck}"),
]

# Routes scoped to the caller: they list or change only the caller's own data.
SELF_SCOPED = {
    ("GET", "/api/decks"),
    ("POST", "/api/decks"),
    ("GET", "/api/cards"),
    ("GET", "/api/tags"),
    ("GET", "/api/public/decks"),
    ("GET", "/api/study/next"),
    ("GET", "/api/study/batch"),
    ("GET", "/api/study/tags"),
    ("GET", "/api/study/due"),
    ("GET", "/api/stats/breakdown"),
    ("GET", "/api/history"),
    ("DELETE", "/api/history"),
    ("POST", "/api/study/transcribe"),
    ("POST", "/api/study/speak"),
    ("GET", "/api/settings"),
    ("PATCH", "/api/settings"),
    ("GET", "/api/settings/tokens"),
    ("POST", "/api/settings/tokens"),
    ("DELETE", "/api/settings/tokens/{token_id}"),
    ("GET", "/api/auth/me"),
    ("GET", "/"),
    ("POST", "/decks"),
    ("GET", "/explore"),
    ("GET", "/study"),
    ("GET", "/history"),
    ("POST", "/history/clear"),
    ("GET", "/stats"),
    ("GET", "/settings"),
    ("POST", "/settings"),
    ("POST", "/settings/tokens"),
    ("POST", "/settings/tokens/{token_id}/revoke"),
    ("POST", "/logout"),
}

ADMIN_ONLY = {
    ("GET", "/api/admin/users"),
    ("PATCH", "/api/admin/users/{user_id}"),
    ("DELETE", "/api/admin/users/{user_id}"),
    ("GET", "/api/admin/settings"),
    ("PATCH", "/api/admin/settings"),
    ("POST", "/api/admin/decks/{deck_id}/unpublish"),
    ("GET", "/admin"),
    ("POST", "/admin/users/{user_id}"),
    ("POST", "/admin/settings"),
    ("POST", "/admin/decks/{deck_id}/unpublish"),
    ("GET", "/admin/agents"),
    ("POST", "/admin/agents/{step}"),
}

PUBLIC = {
    ("GET", "/healthz"),
    ("GET", "/favicon.ico"),
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

ADMIN_CALLS = [
    Call("GET", "/api/admin/users"),
    Call("PATCH", "/api/admin/users/{victim}", json={"status": "disabled"}),
    Call("DELETE", "/api/admin/users/{victim}"),
    Call("GET", "/api/admin/settings"),
    Call("PATCH", "/api/admin/settings", json={"registration": "open"}),
    Call("POST", "/api/admin/decks/{deck}/unpublish"),
    Call("GET", "/admin"),
    Call("POST", "/admin/users/{victim}", data={"action": "suspend"}),
    Call(
        "POST",
        "/admin/settings",
        data={
            "registration": "open",
            "default_eval_mode": "ai_assess",
            "default_judge_language": "auto",
            "default_stt_language": "auto",
        },
    ),
    Call("POST", "/admin/decks/{deck}/unpublish"),
    Call("GET", "/admin/agents"),
    Call(
        "POST",
        "/admin/agents/judge",
        data={
            "model": "",
            "base_url": "",
            "api_key_env": "OPENROUTER_API_KEY",
            "system_prompt": "",
            "prompt_template": "Is it correct?",
        },
    ),
]


def _send(client: TestClient, call: Call) -> int:
    response = client.request(
        call.method, call.path, json=call.json, data=call.data, follow_redirects=False
    )
    return int(response.status_code)


def _all_routes() -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for router in ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or ()
        if method != "HEAD"
    } | {
        ("GET", "/openapi.json"),
        ("GET", "/docs"),
        ("GET", "/docs/oauth2-redirect"),
        ("GET", "/redoc"),
    }


@pytest.fixture
def victim(client: TestClient) -> Victim:
    """Alice's private deck, card and tag."""
    deck = response_dict(client.post("/api/decks", json={"name": "Alice private"}))
    card = response_dict(
        client.post(
            "/api/cards",
            json={"deck_id": deck["id"], "question": "Secret?", "answer": "S", "tags": ["t"]},
        )
    )
    return Victim(deck=deck["id"], card=card["id"], tag=card["tags"][0]["id"])


def test_every_route_has_an_access_category() -> None:
    resource = set(_resource_calls(Victim(1, 1, 1)))
    categories = [resource, SELF_SCOPED, ADMIN_ONLY, PUBLIC]
    routes = _all_routes()
    classified = set().union(*categories)
    assert routes - classified == set(), "Unclassified routes: add them to test_perimeter"
    assert classified - routes == set(), "Stale entries in test_perimeter"
    assert sum(len(c) for c in categories) == len(classified), "Route in two categories"


@pytest.mark.parametrize("who", ["bob", "admin"])
def test_outsiders_get_404_on_private_resources(
    app: FastAPI, client: TestClient, victim: Victim, who: str
) -> None:
    outsider = new_client(
        app, make_user(app, f"{who}@example.com", role="admin" if who == "admin" else "user").email
    )
    calls = list(_resource_calls(victim).values()) + [probe(victim) for probe in EXTRA_PROBES]
    failures = {
        f"{call.method} {call.path}": status
        for call in calls
        if (status := _send(outsider, call)) != 404
    }
    assert failures == {}

    # Nothing leaked into the outsider's own listings.
    assert response_list(outsider.get("/api/decks")) == []
    assert response_list(outsider.get("/api/cards")) == []
    assert response_list(outsider.get("/api/tags")) == []
    assert response_list(outsider.get("/api/public/decks")) == []
    assert outsider.get("/api/study/next").json() is None
    assert "Secret?" not in outsider.get("/").text
    assert "Alice private" not in outsider.get("/study").text

    # Alice's data is intact.
    assert response_dict(client.get(f"/api/decks/{victim.deck}"))["name"] == "Alice private"
    assert response_dict(client.get(f"/api/cards/{victim.card}"))["answer"] == "S"
    assert [tag["id"] for tag in response_list(client.get("/api/tags"))] == [victim.tag]


def test_anonymous_is_rejected_everywhere(
    app: FastAPI, client: TestClient, anon_client: TestClient, victim: Victim
) -> None:
    calls = list(_resource_calls(victim).values()) + [
        Call(
            method,
            path.replace("{token_id}", "1")
            .replace("{user_id}", "1")
            .replace("{deck_id}", str(victim.deck)),
        )
        for method, path in SELF_SCOPED | ADMIN_ONLY
    ]
    failures = {}
    for call in calls:
        response = anon_client.request(
            call.method, call.path, json=call.json, data=call.data, follow_redirects=False
        )
        expected = 401 if call.path.startswith("/api") else 303
        if response.status_code != expected or (
            expected == 303 and response.headers["location"] != "/login"
        ):
            failures[f"{call.method} {call.path}"] = response.status_code
    assert failures == {}


def test_admin_routes_forbidden_to_users(
    client: TestClient, client_b: TestClient, bob: User, victim: Victim
) -> None:
    client.patch(f"/api/decks/{victim.deck}", json={"visibility": "public"})
    failures = {}
    for call in ADMIN_CALLS:
        path = call.path.format(victim=bob.id, deck=victim.deck)
        status = _send(client_b, Call(call.method, path, call.json, call.data))
        if status != 403:
            failures[f"{call.method} {path}"] = status
    assert failures == {}
    assert response_dict(client.get(f"/api/decks/{victim.deck}"))["visibility"] == "public"


def test_settings_are_per_user(client: TestClient, client_b: TestClient) -> None:
    client.patch("/api/settings", json={"eval_mode": "ai_assess", "daily_new_limit": 3})
    bob_settings = response_dict(client_b.get("/api/settings"))
    assert bob_settings["eval_mode"] == "ai_preselect"
    assert bob_settings["daily_new_limit"] == 0
    assert response_dict(client.get("/api/settings"))["daily_new_limit"] == 3


def test_tags_are_per_user(client: TestClient, client_b: TestClient, victim: Victim) -> None:
    deck = response_dict(client_b.post("/api/decks", json={"name": "Bob"}))
    card = response_dict(
        client_b.post(
            "/api/cards",
            json={"deck_id": deck["id"], "question": "Q", "answer": "A", "tags": ["t"]},
        )
    )
    assert card["tags"][0]["id"] != victim.tag
    assert response_list(client_b.get("/api/cards?tag=t"))[0]["id"] == card["id"]
    assert [c["id"] for c in response_list(client.get("/api/cards?tag=t"))] == [victim.card]


def test_cannot_move_card_into_foreign_deck(
    client: TestClient, client_b: TestClient, victim: Victim
) -> None:
    deck = response_dict(client_b.post("/api/decks", json={"name": "Bob"}))
    card = response_dict(
        client_b.post("/api/cards", json={"deck_id": deck["id"], "question": "Q", "answer": "A"})
    )
    moved = client_b.patch(f"/api/cards/{card['id']}", json={"deck_id": victim.deck})
    assert moved.status_code == 404
    assert response_list(client.get(f"/api/cards?deck_id={victim.deck}"))[0]["id"] == victim.card
