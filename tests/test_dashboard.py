from fastapi.testclient import TestClient

from ledger.api import create_app
from ledger.models import ResearchRequest
from ledger.store import Store


def test_dashboard_reuses_live_report_and_ignores_demo(tmp_path):
    store = Store(tmp_path)
    request = ResearchRequest().model_dump(mode="json")
    store.save(
        {
            "id": "demo",
            "created": "2026-01-01",
            "status": "complete",
            "request": request,
        }
    )
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/dashboard").json() is None
        store.save(
            {
                "id": "live",
                "created": "2026-01-02",
                "status": "complete",
                "request": request | {"mode": "live"},
            }
        )
        assert client.get("/api/dashboard").json()["id"] == "live"
        assert client.post("/api/dashboard").json()["id"] == "live"


def test_dashboard_lookup_is_scoped_to_selected_symbol(tmp_path):
    store = Store(tmp_path)
    request = ResearchRequest(mode="live").model_dump(mode="json")
    for ticker in ("NVDA", "AAPL"):
        store.save(
            {
                "id": ticker,
                "created": "2026-01-02",
                "status": "complete",
                "request": request | {"ticker": ticker},
            }
        )
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/dashboard?ticker=aapl").json()["id"] == "AAPL"
        assert client.get("/api/dashboard?ticker=MSFT").json() is None
