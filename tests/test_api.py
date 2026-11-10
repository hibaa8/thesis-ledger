from datetime import date, timedelta

import httpx
from fastapi.testclient import TestClient
from ledger.api import create_app
from ledger.data import demo_snapshot


def test_ui_api_and_mcp(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://localhost:8000") as client:
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/health").json()["status"] == "ok"
        run = client.post("/api/research", json={"ticker": "AAPL", "mode": "demo"}).json()
        assert run["status"] == "complete", run
        assert client.get("/api/runs/" + run["id"]).json()["id"] == run["id"]
        assert len(client.get("/api/memories").json()) == 1
        assert client.get("/api/runs/missing").status_code == 404
        assert (
            client.post("/api/research", json={"ticker": "BAD/TICKER"}).status_code
            == 422
        )
        headers = {"Accept": "application/json, text/event-stream"}
        r = client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["result"]["serverInfo"]["name"] == "Thesis Ledger"
        r = client.post(
            "/mcp/",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert "latest_price" in {
            tool["name"] for tool in r.json()["result"]["tools"]
        }, r.text
        r = client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_research", "arguments": {"run_id": run["id"]}},
            },
        )
        assert not r.json()["result"].get("isError"), r.text


def test_auth_and_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_API_TOKEN", "x" * 40)
    with TestClient(create_app(tmp_path), base_url="http://localhost:8000") as client:
        assert client.get("/api/runs").status_code == 401
        assert client.post("/mcp/", json={}).status_code == 401
        headers = {"Authorization": "Bearer " + "x" * 40}
        assert client.get("/api/runs", headers=headers).status_code == 200
        assert (
            client.post(
                "/api/research",
                headers={**headers, "Origin": "https://evil.example"},
                json={},
            ).status_code
            == 403
        )
        assert (
            client.get("/health", headers={"Host": "evil.example"}).status_code == 400
        )


def test_forecast_uses_alpaca_daily_bars_when_alpha_vantage_is_throttled(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-alpha-key")
    monkeypatch.setenv("APCA_API_KEY_ID", "test-alpaca-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test-alpaca-secret")
    monkeypatch.setenv("LEDGER_ALPACA_FEED", "iex")
    as_of = date.today() - timedelta(days=2)
    bars = demo_snapshot("NVDA", as_of)["bars"]

    def upstream(request):
        if request.url.host == "www.alphavantage.co":
            return httpx.Response(200, json={"Note": "Quota exceeded"})
        assert request.url.host == "data.alpaca.markets"
        assert request.url.params["symbols"] == "NVDA"
        assert request.url.params["timeframe"] == "1Day"
        assert request.url.params["feed"] == "iex"
        return httpx.Response(
            200,
            json={
                "bars": {
                    "NVDA": [
                        dict(
                            t=bar["date"] + "T05:00:00Z",
                            o=bar["open"],
                            h=bar["high"],
                            l=bar["low"],
                            c=bar["close"],
                            v=bar["volume"],
                        )
                        for bar in bars[-60:]
                    ]
                }
            },
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **opts: real_client(transport=httpx.MockTransport(upstream), **opts),
    )
    with TestClient(create_app(tmp_path)) as client:
        response = client.post(
            "/api/forecast",
            json={"ticker": "NVDA", "mode": "live", "as_of": as_of.isoformat()},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["snapshot"]["provider"] == "Alpaca IEX"
        assert result["snapshot"]["bars"][-1]["date"] == bars[-1]["date"]
        assert len(result["forecast"]["points"]) == 5
