"""Favicon, icon sprite, manifest, and the chart data regression."""

import html
import json
import re

from fastapi.testclient import TestClient


def test_brand_assets_are_served(client: TestClient) -> None:
    assert client.get("/favicon.ico").status_code == 200
    assert client.get("/favicon.ico").headers["content-type"] == "image/x-icon"
    assert client.get("/static/favicon.svg").status_code == 200
    assert client.get("/static/icons.svg").status_code == 200
    manifest = client.get("/static/site.webmanifest")
    assert manifest.status_code == 200
    assert json.loads(manifest.text)["short_name"] == "QuizDeck"


def test_nav_uses_the_icon_sprite(client: TestClient) -> None:
    page = client.get("/").text

    assert 'href="/static/icons.svg#study"' in page
    assert 'rel="icon"' in page
    assert 'rel="manifest"' in page


def test_pages_need_no_inline_script_or_style(client: TestClient) -> None:
    """The strict CSP (script-src/style-src 'self') forbids anything inline."""
    for path in ("/", "/study", "/history", "/stats", "/settings"):
        page = client.get(path).text
        inline_scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", page, re.I)
        assert inline_scripts == [], f"{path} has an inline script: {inline_scripts}"
        assert "<style" not in page.lower(), f"{path} has an inline style element"
        handlers = re.findall(
            r"\son(?:click|change|submit|input|load|error|focus|blur|keyup|keydown)=", page, re.I
        )
        assert handlers == [], f"{path} has an inline event handler"
        assert "file://" not in page, f"{path} links to a file:// URL"


def test_htmx_does_not_inject_indicator_styles(client: TestClient) -> None:
    page = client.get("/").text

    assert 'name="htmx-config"' in page
    assert '"includeIndicatorStyles": false' in page


def test_stats_config_is_valid_json(client: TestClient) -> None:
    """The chart reads its data from a data attribute: it must survive escaping."""
    deck = client.post("/api/decks", json={"name": "D", "grading_scale": {"max": 10}}).json()
    card = client.post(
        "/api/cards",
        json={"deck_id": deck["id"], "question": 'A "quoted" & <tagged> question?', "answer": "A"},
    ).json()
    response = client.post(
        "/api/study/answer",
        json={
            "card_id": card["id"],
            "answer_text": "A",
            "input_method": "text",
            "response_time_ms": 1000,
            "confirmed": True,
            "rating": 9,
            "is_correct": True,
        },
    )
    assert response.status_code == 200

    page = client.get(f"/stats?deck_id={deck['id']}").text
    match = re.search(r'data-card="([^"]*)"', page)
    assert match, "stats config attribute is missing"

    data = json.loads(html.unescape(match.group(1)))

    assert data["items"][0]["label"] == 'A "quoted" & <tagged> question?'
    assert data["items"][0]["avg_normalized"] == 9.0
