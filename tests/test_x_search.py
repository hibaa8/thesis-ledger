import asyncio
import json
from datetime import date

import httpx

from ledger.x_search import x_post_evidence


def test_x_search_returns_only_recent_cited_posts(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    original = "https://x.com/Company/status/100"
    second = "https://twitter.com/Industry/status/200"
    third = "https://x.com/Other/status/300"
    stale = "https://x.com/Company/status/99"
    uncited = "https://x.com/Company/status/400"

    def provider(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/responses"
        assert body["tools"] == [{
            "type": "x_search", "from_date": "2026-11-07", "to_date": "2026-11-11",
        }]
        text = "\n".join([
            f"2026-11-10 Uncited claim [[1]]({uncited})",
            f"2026-11-06 Earlier update [[2]]({stale})",
            f"2026-11-10 Company update [[3]]({original})",
            f"2026-11-10 Duplicate company update [[3]]({original})",
            f"2026-11-09 Industry commentary [[4]]({second})",
            f"2026-11-09 Third result [[5]]({third})",
        ])
        return httpx.Response(200, json={"output": [{
            "type": "message",
            "content": [{
                "type": "output_text",
                "text": text,
                "annotations": [
                    {"type": "url_citation", "url": url}
                    for url in (stale, original, second, third)
                ],
            }],
        }]})

    async def fetch():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
            return await x_post_evidence(client, "NVDA", date(2026, 11, 10))

    result = asyncio.run(fetch())
    assert [item["url"] for item in result] == [original, "https://x.com/Industry/status/200"]
    assert all(item["kind"] == "sentiment" for item in result)
    assert result[0]["text"].endswith("Company update")
