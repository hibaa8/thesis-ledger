import asyncio
from datetime import date, timedelta
import pytest
from ledger.models import ResearchRequest
from ledger.store import Store
from ledger.harness import Harness
from ledger.data import demo_snapshot, validate_bars, future_sessions
from ledger.forecast import forecast, walk_forward


def test_fixture_and_forecast_are_reproducible():
    bars = demo_snapshot("NVDA", date(2026, 10, 30))["bars"]
    a = forecast(bars, 5)
    b = forecast(bars, 5)
    assert a == b
    assert all(p["low"] <= p["median"] <= p["high"] for p in a["points"])
    assert all(p["date"] > bars[-1]["date"] for p in a["points"])
    assert walk_forward(bars)["windows"] > 5


def test_market_calendar_excludes_holidays():
    assert future_sessions("2026-11-25", 2) == ["2026-11-27", "2026-11-30"]


def test_invalid_ohlc_and_future_bars():
    bars = demo_snapshot("AAPL", date(2026, 10, 30))["bars"]
    assert all(b["date"] <= "2026-10-20" for b in validate_bars(bars, "2026-10-20"))
    bars[0]["high"] = 0
    with pytest.raises(ValueError):
        validate_bars(bars, "2026-10-30")


def test_end_to_end_memory_and_immutable_revision(tmp_path):
    store = Store(tmp_path)
    h = Harness(store)
    r = asyncio.run(h.run(ResearchRequest()))
    assert r["status"] == "complete", r.get("error")
    assert r["decision"]["stance"] == "abstain"
    assert len(r["reports"]) == 8
    memories = store.memories()
    assert len(memories) == 1
    original = memories[0]["body"]
    mid = memories[0]["id"]
    store.revise(mid, "Do not generalize this single snapshot.", "source_snapshot_only")
    assert store.memories()[0]["body"] == original
    assert len(store.memories()[0]["revisions"]) == 1
    store.revise(
        mid, "Retire because the original scope is no longer useful.", "retire"
    )
    assert store.memories("NVDA", "demo", str(date.today())) == []
    assert store.get(r["id"])["decision"] == r["decision"]


def test_historical_memory_does_not_leak(tmp_path):
    store = Store(tmp_path)
    r = asyncio.run(Harness(store).run(ResearchRequest(as_of=date(2026, 10, 1))))
    assert r["status"] == "complete"
    assert (
        store.memories("NVDA", "demo", "2026-10-02") == []
    )  # written today, not backdated
    assert store.memories("NVDA", "live", str(date.today())) == []
    assert len(store.memories("NVDA", "demo", str(date.today()))) == 1


def test_resume_reuses_completed_checkpoints(tmp_path, monkeypatch):
    import ledger.harness as module

    original = module.analyze

    async def fail_bear(role, context, mode):
        if role == "bear":
            raise ValueError("Deliberate test failure")
        return await original(role, context, mode)

    monkeypatch.setattr(module, "analyze", fail_bear)
    h = Harness(Store(tmp_path))
    r = asyncio.run(h.run(ResearchRequest()))
    assert r["status"] == "failed"
    assert len(r["reports"]) == 5
    before = r["snapshot"]
    monkeypatch.setattr(module, "analyze", original)
    resumed = asyncio.run(h.run(resume_id=r["id"]))
    assert resumed["status"] == "complete"
    assert resumed["snapshot"] == before
    assert resumed["calls"] == 9
    again = asyncio.run(h.run(resume_id=r["id"]))
    assert again["calls"] == 9
    assert len(h.store.memories()) == 1


def test_no_silent_kronos_fallback(monkeypatch):
    monkeypatch.delenv("KRONOS_PATH", raising=False)
    from ledger.forecast import kronos_predictor

    kronos_predictor.cache_clear()
    with pytest.raises(ValueError, match="Kronos is not installed"):
        forecast(demo_snapshot("NVDA", date.today())["bars"], 5, "kronos")


def test_live_requires_credentials(tmp_path, monkeypatch):
    for key in ("ALPHAVANTAGE_API_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    r = asyncio.run(Harness(Store(tmp_path)).run(ResearchRequest(mode="live")))
    assert r["status"] == "failed"
    assert "Neither Alpha Vantage nor Alpaca" in r["error"]
    assert "decision" not in r


def test_request_boundaries():
    for kwargs in [
        {"ticker": "../secret"},
        {"horizon": 21},
        {"rounds": 3},
        {"as_of": date.today() + timedelta(days=1)},
    ]:
        with pytest.raises(ValueError):
            ResearchRequest(**kwargs)
