import asyncio
import json
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

from ledger.api import create_app


def test_chat_streams_tool_grounded_answer_and_saves_history(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    requests = []

    def sse(delta):
        return httpx.Response(
            200,
            text=(
                "data: " + json.dumps({"choices": [{"delta": delta}]}) + "\n\n"
                "data: [DONE]\n\n"
            ),
        )

    def upstream(request):
        if request.url.host == "www.alphavantage.co":
            assert "entitlement" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "Global Quote": {
                        "05. price": "123.45",
                        "07. latest trading day": "2026-11-09",
                    }
                },
            )
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            return sse(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_1",
                            "function": {
                                "name": "latest_price",
                                "arguments": '{"ticker":"NVDA"}',
                            },
                        }
                    ]
                }
            )
        quote = json.loads(payload["messages"][-1]["content"])
        assert quote["price"] == 123.45
        assert quote["freshness"] == "End-of-day quote"
        return sse({"content": "NVDA closed at $123.45."})

    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-market-key")
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **opts: real_client(transport=httpx.MockTransport(upstream), **opts),
    )
    session = "a" * 32
    with TestClient(create_app(tmp_path)) as client:
        response = client.post(
            "/api/chat", json={"session": session, "message": "NVDA price?"}
        )
        events = [json.loads(line) for line in response.text.splitlines()]
        assert [e["type"] for e in events] == ["status", "delta", "done"]
        assert (
            client.get("/api/chat/" + session).json()[-1]["content"]
            == "NVDA closed at $123.45."
        )
        assert client.get("/api/chat/" + "b" * 32).json() == []



def test_stock_snapshot_keeps_company_evidence_when_prices_are_unavailable(monkeypatch):
    from ledger.chat import Chat

    async def company_snapshot(request, *, require_bars, include_sentiment):
        assert request.ticker == "GOOGL"
        assert require_bars is False
        assert include_sentiment is False
        return {
            "bars": [],
            "warnings": ["Daily price history was unavailable."],
            "evidence": [
                {"id": "fundamentals", "kind": "fundamentals", "url": "https://www.sec.gov/filing"},
                {"id": "company-news-1", "kind": "news", "published": "2026-11-10"},
                {"id": "market-news-2", "kind": "news", "published": "2026-11-10"},
            ],
        }

    async def unavailable_quote(ticker):
        raise ValueError("Quote unavailable")

    monkeypatch.setattr("ledger.chat.snapshot", company_snapshot)
    chat = Chat(None, None, SimpleNamespace(get=unavailable_quote), None)
    result = asyncio.run(chat.execute("stock_snapshot", {"ticker": "googl"}))
    assert result["quote"] is None
    assert "daily_technicals" not in result
    assert [item["id"] for item in result["evidence"]] == ["fundamentals", "company-news-1"]
    assert "Latest quote unavailable." in result["warnings"]
