import asyncio
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from weakref import WeakKeyDictionary

import httpx


MARKET_SYMBOLS = ("SPY", "QQQ", "DIA", "IWM", "AAPL", "MSFT", "NVDA")
NEWS_FEEDS = {
    "CNBC Markets": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "Bureau of Labor Statistics": "https://www.bls.gov/feed/bls_latest.rss",
    "Federal Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
}
_alpha_gates = WeakKeyDictionary()


async def alpha_query(client, function, **params):
    key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not key:
        raise ValueError("Alpha Vantage key missing.")
    loop = asyncio.get_running_loop()
    gate = _alpha_gates.setdefault(loop, [asyncio.Lock(), 0.0])
    async with gate[0]:
        await asyncio.sleep(max(0, gate[1] - loop.time()))
        gate[1] = loop.time() + 1.1
        response = await client.get(
            "https://www.alphavantage.co/query",
            params={"function": function, "apikey": key, **params},
        )
    response.raise_for_status()
    data = response.json()
    if any(k in data for k in ("Error Message", "Note", "Information")):
        raise ValueError("Alpha Vantage rejected the request or reached its quota.")
    return data


async def headlines(client, source, url):
    response = await client.get(
        url, follow_redirects=True, headers={"User-Agent": "Thesis Ledger research app"}
    )
    response.raise_for_status()
    if len(response.content) > 1_000_000:
        raise ValueError("Oversized news feed")
    articles = []
    for item in ET.fromstring(response.content).findall("./channel/item")[:8]:
        title = item.findtext("title")
        link = item.findtext("link", "")
        published = item.findtext("pubDate")
        if title and link.startswith("https://") and published:
            try:
                timestamp = parsedate_to_datetime(published)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if timestamp <= datetime.now(timezone.utc):
                articles.append(
                    dict(
                        title=title,
                        url=link,
                        source=source,
                        published=timestamp.astimezone(timezone.utc).isoformat(),
                    )
                )
    return articles


async def news_sources():
    async with httpx.AsyncClient(timeout=6) as client:
        feeds = await asyncio.gather(
            *(headlines(client, source, url) for source, url in NEWS_FEEDS.items()),
            return_exceptions=True,
        )
    return dict(zip(NEWS_FEEDS, feeds))


class MarketBrief:
    def __init__(self, quotes):
        self.quotes = quotes
        self.lock = asyncio.Lock()
        self.cached = None
        self.expires = 0
        self.news = []
        self.news_errors = []
        self.news_expires = 0

    async def get(self):
        async with self.lock:
            if self.cached and self.expires > time.monotonic():
                return self.cached
            prices, errors = await self.get_prices()
            if self.news_expires <= time.monotonic():
                feeds = await news_sources()
                self.news_errors = []
                for source, result in feeds.items():
                    if isinstance(result, Exception) or not result:
                        self.news_errors.append(f"{source} headlines unavailable.")
                    else:
                        self.news = [
                            item for item in self.news if item["source"] != source
                        ] + result[:4]
                self.news.sort(key=lambda item: item["published"], reverse=True)
                self.news_expires = time.monotonic() + 900
            refresh = 60 if any(p["refresh_seconds"] for p in prices) else 900
            self.cached = dict(
                quotes=prices,
                headlines=self.news[:10],
                warnings=errors + self.news_errors,
                refresh_seconds=refresh,
            )
            self.expires = time.monotonic() + refresh
            return self.cached

    async def get_prices(self):
        prices, errors = [], []
        for symbol in MARKET_SYMBOLS:
            try:
                prices.append(await self.quotes.get(symbol))
            except ValueError:
                errors.append(symbol)
        return prices, [f"Quotes unavailable: {', '.join(errors)}."] if errors else []
