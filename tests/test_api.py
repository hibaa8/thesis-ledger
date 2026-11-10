import csv
from datetime import date, timedelta
from io import BytesIO, StringIO
from zipfile import ZipFile

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


def test_export_downloads_the_requested_completed_report(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_API_TOKEN", "export-test-token")
    headers = {"Authorization": "Bearer export-test-token"}
    with TestClient(create_app(tmp_path)) as client:
        run = client.post(
            "/api/research",
            headers=headers,
            json={"ticker": "AAPL", "mode": "demo", "question": "=test question"},
        ).json()
        path = "/api/runs/" + run["id"] + "/export"
        assert client.get(path).status_code == 401
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert 'filename="thesis-ledger-AAPL-' in response.headers["content-disposition"]
        with ZipFile(BytesIO(response.content)) as archive:
            report = archive.read("report.md").decode()
            assert f"Run ID: {run['id']}" in report
            assert run["decision"]["summary"] in report
            assert "## Risk" in report
            forecast = list(csv.DictReader(StringIO(archive.read("forecast.csv").decode())))
            assert len(forecast) == run["request"]["horizon"]
            evidence = list(csv.DictReader(StringIO(archive.read("evidence.csv").decode())))
            assert evidence[0]["id"] == "prices"


def test_public_workspace_isolated_and_metered_across_app_restarts(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_PUBLIC", "1")
    monkeypatch.setenv("LEDGER_API_TOKEN", "owner-test-token")
    owner_headers = {"Authorization": "Bearer owner-test-token"}
    fixture = {"ticker": "NVDA", "mode": "demo"}
    app = create_app(tmp_path)
    with TestClient(app) as first, TestClient(create_app(tmp_path)) as second:
        owner = first.post("/api/research", headers=owner_headers, json=fixture).json()
        assert first.get("/api/config").json()["public_visitor"] is True
        assert first.get("/api/runs").json() == []
        assert first.get("/api/runs/" + owner["id"]).status_code == 404
        assert first.post("/mcp/", json={}).status_code == 401

        run = first.post("/api/research", json=fixture).json()
        assert run["status"] == "complete"
        assert second.get("/api/memories").json() == []
        assert second.get("/api/runs/" + run["id"] + "/export").status_code == 404
        followup = first.post("/api/research", json=fixture).json()
        assert any(memory["run_id"] == run["id"] for memory in followup["memories"])
        assert first.post("/api/research", json=fixture).status_code == 200
        cookies = dict(first.cookies)

    with TestClient(create_app(tmp_path), cookies=cookies) as restarted:
        assert len(restarted.get("/api/memories").json()) == 3
        limited = restarted.post("/api/research", json=fixture)
        assert limited.status_code == 429
        assert "daily research limit" in limited.json()["detail"]
        assert int(limited.headers["retry-after"]) > 0


def test_public_mcp_exposes_only_market_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_PUBLIC", "1")
    monkeypatch.setenv("LEDGER_API_TOKEN", "owner-test-token")
    headers = {"Accept": "application/json, text/event-stream"}
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    with TestClient(create_app(tmp_path), base_url="http://localhost:8000") as client:
        public = client.post("/mcp/public/", json=request, headers=headers)
        assert public.status_code == 200, public.text
        tools = public.json()["result"]["tools"]
        assert {tool["name"] for tool in tools} == {"market_brief", "latest_price"}
        assert all(tool["annotations"]["readOnlyHint"] for tool in tools)
        assert client.post("/mcp/", json=request, headers=headers).status_code == 401
        owner = client.post(
            "/mcp/",
            json=request,
            headers={**headers, "Authorization": "Bearer owner-test-token"},
        )
        assert "research_ticker" in {tool["name"] for tool in owner.json()["result"]["tools"]}
        monkeypatch.delenv("LEDGER_PUBLIC")
        assert client.post("/mcp/public/", json=request, headers=headers).status_code == 404


def test_account_report_reopens_after_new_session_and_is_private(tmp_path, monkeypatch):
    from ledger.auth import AccountAuth, SESSION

    monkeypatch.setenv("LEDGER_PUBLIC", "1")
    monkeypatch.setenv("LEDGER_API_TOKEN", "owner-test-token")

    async def verify(self, token):
        return {"alice": "a" * 32, "alice-again": "a" * 32, "bob": "b" * 32}.get(token)

    monkeypatch.setattr(AccountAuth, "account", verify)
    fixture = {"ticker": "NVDA", "mode": "demo"}
    with TestClient(create_app(tmp_path), cookies={SESSION: "alice"}) as alice:
        run = alice.post("/api/research", json=fixture).json()
        assert run["status"] == "complete"
    path = "/api/runs/" + run["id"]
    with TestClient(create_app(tmp_path), cookies={SESSION: "alice-again"}) as alice:
        assert alice.get("/api/memories").json()[0]["run_id"] == run["id"]
        assert alice.get(path).json()["reports"] == run["reports"]
        report = alice.get(path + "/export?format=md")
        assert report.status_code == 200
        assert "text/markdown" in report.headers["content-type"]
        assert "## Key numbers" in report.text
        assert "## Fundamentals" in report.text
        assert "## Bull" in report.text
        alice.cookies.clear()
        alice.cookies.set(SESSION, "alice-again", domain="testserver.local", path="/")
        assert alice.get(path).status_code == 200
        alice.post("/api/auth/logout")
        assert alice.get(path).status_code == 404
    for cookies in ({SESSION: "bob"}, {SESSION: "forged"}, {}):
        with TestClient(create_app(tmp_path), cookies=cookies) as other:
            assert other.get("/api/memories").json() == []
            assert other.get(path).status_code == 404
            assert other.get(path + "/export?format=md").status_code == 404


def test_background_research_returns_saved_id_before_work_finishes(tmp_path, monkeypatch):
    import asyncio
    from ledger.harness import Harness

    monkeypatch.delenv("LEDGER_API_TOKEN", raising=False)
    monkeypatch.delenv("LEDGER_PUBLIC", raising=False)
    released = False

    async def slow_run(self, request=None, resume_id=None):
        nonlocal released
        state = self.store.get(resume_id)
        assert state["status"] == "running"
        await asyncio.sleep(0.1)
        state["status"] = "complete"
        self.store.save(state)
        released = True
        return state

    monkeypatch.setattr(Harness, "run", slow_run)
    with TestClient(create_app(tmp_path)) as client:
        started = client.post("/api/research?background=true", json={"mode": "demo"})
        assert started.status_code == 202
        assert not released
        path = "/api/runs/" + started.json()["id"]
        progress = client.get(path + "?status_only=true")
        assert progress.status_code == 200
        assert progress.json()["status"] == "running"
        assert client.post("/api/research?background=true", json={"mode": "demo"}).status_code == 409
        import time
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if client.get(path).json()["status"] == "complete":
                break
            time.sleep(0.02)
        assert released
        assert client.get(path).json()["status"] == "complete"
