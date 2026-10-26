import asyncio
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import Client

from tests.test_study import answer_payload, enable_ai_assess


def tool_data(result: Any) -> Any:
    structured = result.structured_content
    if structured is None:
        return None
    if set(structured) == {"result"}:
        return structured["result"]
    return structured


def test_all_mcp_tools_via_client(app: FastAPI, client: TestClient) -> None:
    async def exercise() -> None:
        async with Client(app.state.mcp) as mcp_client:

            async def call(name: str, arguments: dict[str, Any]) -> Any:
                return tool_data(await mcp_client.call_tool(name, arguments))

            tools = await mcp_client.list_tools()
            names = {tool.name for tool in tools}
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
            } <= names

            deck = await call("create_deck", {"name": "MCP deck", "scheduler": "sm2"})
            deck_id = deck["id"]
            assert (await call("list_decks", {}))[0]["name"] == "MCP deck"
            assert await call("get_deck", {"deck_id": deck_id}) == deck

            updated_deck = await call(
                "update_deck", {"deck_id": deck_id, "data": {"description": "updated"}}
            )
            assert updated_deck["description"] == "updated"

            card = await call(
                "create_card",
                {
                    "deck_id": deck_id,
                    "question": "MCP question",
                    "answer": "MCP answer",
                    "tags": ["agent", "test"],
                },
            )
            card_id = card["id"]
            assert await call("get_card", {"card_id": card_id}) == card
            filtered = await call("list_cards", {"deck_id": deck_id, "tag": "agent"})
            assert [item["id"] for item in filtered] == [card_id]

            updated_card = await call(
                "update_card", {"card_id": card_id, "data": {"details": "more"}}
            )
            assert updated_card["details"] == "more"
            tags = await call("list_tags", {})
            assert {tag["name"] for tag in tags} == {"agent", "test"}
            due = await call("list_due", {"deck_id": deck_id})
            assert due[0]["card"]["id"] == card_id
            assert due[0]["is_new"] is True

            enable_ai_assess(client)
            response = client.post("/api/study/answer", json=answer_payload(card_id))
            assert response.status_code == 200
            for scope, target in (("deck", str(deck_id)), ("card", str(card_id)), ("tag", "agent")):
                stats = await call("get_stats", {"scope": scope, "target": target})
                assert stats["total"] == 1
                assert stats["correct"] == 1

            await call("delete_card", {"card_id": card_id})
            assert await call("list_cards", {}) == []
            await call("delete_deck", {"deck_id": deck_id})
            assert await call("list_decks", {}) == []

    asyncio.run(exercise())
    assert client.get("/mcp/").status_code != 404
