import asyncio
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import Client
from sqlmodel import Session

from app.models import User
from tests.conftest import FakeTeacher, mcp_call, mcp_token, mcp_tool
from tests.test_study import answer_payload, enable_ai_assess


def test_all_mcp_tools_via_http(
    app: FastAPI, client: TestClient, fake_teacher: FakeTeacher
) -> None:
    token = mcp_token(client)

    async def list_tool_names() -> set[str]:
        async with Client(app.state.mcp) as mcp_client:
            return {tool.name for tool in await mcp_client.list_tools()}

    names = asyncio.run(list_tool_names())

    def call(name: str, arguments: dict[str, Any]) -> Any:
        return mcp_tool(client, token, name, arguments)

    assert {
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
    } <= names

    deck = call(
        "create_deck",
        {"name": "MCP deck", "context": "MCP deck context", "scheduler": "sm2"},
    )
    deck_id = deck["id"]
    assert deck["context"] == "MCP deck context"
    assert (call("list_decks", {}))[0]["name"] == "MCP deck"
    assert call("get_deck", {"deck_id": deck_id}) == deck

    updated_deck = call(
        "update_deck",
        {"deck_id": deck_id, "data": {"description": "updated", "context": "ctx2"}},
    )
    assert updated_deck["description"] == "updated"
    assert updated_deck["context"] == "ctx2"

    card = call(
        "create_card",
        {
            "deck_id": deck_id,
            "question": "MCP question",
            "answer": "MCP answer",
            "context": "MCP card context",
            "tags": ["agent", "test"],
        },
    )
    card_id = card["id"]
    assert card["context"] == "MCP card context"
    assert call("get_card", {"card_id": card_id}) == card
    filtered = call("list_cards", {"deck_id": deck_id, "tag": "agent"})
    assert [item["id"] for item in filtered] == [card_id]

    updated_card = call(
        "update_card",
        {"card_id": card_id, "data": {"details": "more", "context": "ctx3"}},
    )
    assert updated_card["details"] == "more"
    assert updated_card["context"] == "ctx3"
    tags = call("list_tags", {})
    assert {tag["name"] for tag in tags} == {"agent", "test"}
    due = call("list_due", {"deck_id": deck_id})
    assert due[0]["card"]["id"] == card_id
    assert due[0]["is_new"] is True

    enable_ai_assess(client)
    response = client.post("/api/study/answer", json=answer_payload(card_id))
    assert response.status_code == 200
    for scope, target in (("deck", str(deck_id)), ("card", str(card_id)), ("tag", "agent")):
        stats = call("get_stats", {"scope": scope, "target": target})
        assert stats["total"] == 1
        assert stats["correct"] == 1

    explanation = call("explain_card", {"card_id": card_id})
    assert explanation["model"] == "fake-teacher"
    assert explanation["explanation"] == "Paris is the capital of France."
    assert fake_teacher.calls[0]["deck_context"] == "ctx2"
    assert fake_teacher.calls[0]["card_context"] == "ctx3"
    assert fake_teacher.calls[0]["user_answer"] == "Paris"

    call("delete_card", {"card_id": card_id})
    assert call("list_cards", {}) == []
    call("delete_deck", {"deck_id": deck_id})
    assert call("list_decks", {}) == []


def test_mcp_requires_valid_token(
    app: FastAPI, client: TestClient, client_b: TestClient, bob: User
) -> None:
    # The browser session cookie must not authenticate MCP calls.
    assert mcp_call(client, None, "list_decks").status_code == 401
    assert mcp_call(client, "qd_not-a-real-token", "list_decks").status_code == 401

    alice_token = mcp_token(client)
    bob_token = mcp_token(client_b)
    mcp_tool(client, alice_token, "create_deck", {"name": "Alice private"})
    assert mcp_tool(client, bob_token, "list_decks") == []
    alice_deck = mcp_tool(client, alice_token, "list_decks")[0]
    error = mcp_call(client, bob_token, "get_deck", {"deck_id": alice_deck["id"]}).json()
    assert error["result"]["isError"] is True

    tokens = client.get("/api/settings/tokens").json()
    assert all("token" not in item and "token_hash" not in item for item in tokens)
    assert client.delete(f"/api/settings/tokens/{tokens[0]['id']}").status_code == 204
    assert mcp_call(client, alice_token, "list_decks").status_code == 401
    # Bob cannot revoke Alice's tokens.
    assert client_b.delete(f"/api/settings/tokens/{tokens[0]['id']}").status_code == 404

    # Suspending a user disables their tokens without deleting them.
    with Session(app.state.engine) as session:
        user = session.get(User, bob.id)
        assert user is not None
        user.status = "disabled"
        session.add(user)
        session.commit()
    assert mcp_call(client, bob_token, "list_decks").status_code == 401
