import json

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
