from datetime import datetime, timezone

from ledger.market import discover_stocks


def test_market_activity_keeps_pinned_symbols_separate_and_deduplicates_news():
    now = datetime(2026, 11, 10, 21, tzinfo=timezone.utc)
    movers = {
        "gainers": [
            {"symbol": "NVDA", "price": 100, "percent_change": 10},
            {"symbol": "RIVN", "price": 20, "percent_change": 8},
            {"symbol": "INTC", "price": 32, "percent_change": 2},
        ],
        "losers": [{"symbol": "SNAP", "price": 10, "percent_change": -7}],
    }
    news = {"news": [
        {"created_at": "2026-11-10T19:00:00Z", "symbols": ["RIVN", "PLTR", "NVDA"],
         "headline": "New development", "url": "https://example.com/new"},
        {"created_at": "2026-11-08T19:00:00Z", "symbols": ["INTC"],
         "headline": "Old development", "url": "https://example.com/old"},
    ]}
    activity = discover_stocks(movers, news, now)
    assert [item["ticker"] for item in activity] == ["RIVN", "SNAP", "PLTR"]
    assert activity[0]["headline"]["url"] == "https://example.com/new"
    assert activity[0]["change_percent"] == 8
    assert activity[2]["price"] is None
