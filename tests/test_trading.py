from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ledger.store import Store
from ledger.trading import TradePlanner


TODAY = "2026-11-13"
CLOCK = datetime(2026, 11, 13, 14, tzinfo=ZoneInfo("America/New_York"))


def live_run(run_id, *, stance="bullish", mode="live", as_of=TODAY):
    return {
        "id": run_id,
        "created": CLOCK.isoformat(),
        "status": "complete",
        "request": {"mode": mode, "as_of": as_of, "ticker": "AAPL"},
        "decision": {"stance": stance, "summary": "Evidence-backed thesis", "invalidation": "New filing", "evidence_ids": ["filing-1"]},
        "reports": {"risk": {"stance": "neutral", "summary": "Size conservatively"}},
        "snapshot": {"warnings": []},
        "disagreement": False,
    }


def test_proposals_are_bounded_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_TRADING_ENABLED", "1")
    store = Store(tmp_path)
    planner = TradePlanner(store)
    for n in range(4):
        run = live_run(f"{n:032x}")
        store.save(run)
        proposal = planner.prepare(run["id"], 25, current_time=CLOCK)
        assert proposal["side"] == "buy"
        assert proposal["status"] == "proposal_only"
        assert planner.prepare(run["id"], 25, current_time=CLOCK) == proposal
    fifth = live_run(f"{4:032x}")
    store.save(fifth)
    with pytest.raises(ValueError, match="Daily trade proposal limit"):
        planner.prepare(fifth["id"], 25, current_time=CLOCK)
    with pytest.raises(ValueError, match="different amount"):
        planner.prepare(f"{0:032x}", 10, current_time=CLOCK)


@pytest.mark.parametrize("change", [
    {"request": {"mode": "demo", "as_of": TODAY, "ticker": "AAPL"}},
    {"request": {"mode": "live", "as_of": "2026-11-12", "ticker": "AAPL"}},
    {"decision": {"stance": "abstain", "summary": "No trade", "invalidation": "New filing", "evidence_ids": ["filing-1"]}},
    {"reports": {"risk": {"stance": "abstain", "summary": "No trade"}}},
    {"reports": {"risk": {"stance": "bearish", "summary": "Conflicting risk review"}}},
    {"snapshot": {"warnings": ["STALE market data"]}},
    {"disagreement": True},
])
def test_unsafe_research_cannot_propose(tmp_path, monkeypatch, change):
    monkeypatch.setenv("LEDGER_TRADING_ENABLED", "1")
    store = Store(tmp_path)
    run = live_run("f" * 32)
    run.update(change)
    store.save(run)
    with pytest.raises(ValueError):
        TradePlanner(store).prepare(run["id"], current_time=CLOCK)


def test_disabled_and_excess_amount_fail_closed(tmp_path, monkeypatch):
    store = Store(tmp_path)
    run = live_run("a" * 32)
    store.save(run)
    monkeypatch.delenv("LEDGER_TRADING_ENABLED", raising=False)
    with pytest.raises(ValueError, match="disabled"):
        TradePlanner(store).prepare(run["id"], current_time=CLOCK)
    monkeypatch.setenv("LEDGER_TRADING_ENABLED", "1")
    with pytest.raises(ValueError, match="per-trade"):
        TradePlanner(store).prepare(run["id"], 26, current_time=CLOCK)
    with pytest.raises(ValueError, match="positive"):
        TradePlanner(store).prepare(run["id"], 0, current_time=CLOCK)


def test_bearish_research_only_proposes_a_sell(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_TRADING_ENABLED", "1")
    store = Store(tmp_path)
    run = live_run("b" * 32, stance="bearish")
    store.save(run)
    proposal = TradePlanner(store).prepare(run["id"], 10, current_time=CLOCK)
    assert proposal["side"] == "sell"
    assert any("position" in step for step in proposal["broker_steps"])
