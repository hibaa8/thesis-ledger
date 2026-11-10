import asyncio
from datetime import date

import httpx

from ledger.agents import analyze
from ledger.sentiment import news_tone_evidence, short_sale_evidence


def test_finra_activity_is_cited_without_claiming_a_direction(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    async def run():
        def upstream(request):
            stamp = request.url.path[-12:-4]
            short = 38.25 if stamp == "20261109" else 35.0
            return httpx.Response(200, text=(
                "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
                f"{stamp}|GOOGL|{short}|2|100|B,Q,N\n"
            ))

        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            evidence = await short_sale_evidence(client, "GOOGL", ["2026-11-06", "2026-11-09"])
        report = await analyze("sentiment", {"evidence": [evidence]}, "live")
        assert report["stance"] == "neutral"
        assert report["evidence_ids"] == ["finra-short-volume"]
        assert "38.2%" in report["summary"]
        assert "+3.2 percentage points" in report["summary"]
        assert "not outstanding short interest" in report["summary"]

    asyncio.run(run())


def test_news_tone_requires_a_recent_score_for_the_exact_ticker():
    article = {
        "title": "Headline", "url": "https://example.com/article", "time_published": "20261109T120000",
        "ticker_sentiment": [
            {"ticker": "GOOG", "ticker_sentiment_score": "0.8", "relevance_score": "1"},
            {"ticker": "GOOGL", "ticker_sentiment_score": "-0.4", "relevance_score": "0.8"},
        ],
    }
    evidence = news_tone_evidence(article, "GOOGL", date(2026, 11, 10), 1)
    assert "-0.40" in evidence["text"]
    assert news_tone_evidence(article, "NVDA", date(2026, 11, 10), 1) is None
    assert news_tone_evidence(article, "GOOGL", date(2026, 11, 30), 1) is None
