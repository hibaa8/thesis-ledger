import asyncio
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from weakref import WeakKeyDictionary

import httpx

from .alpaca import alpaca_headers


MARKET_SYMBOLS = ("SPY", "QQQ", "DIA", "IWM", "AAPL", "MSFT", "NVDA")
ALPACA_EXTRA_SYMBOLS = ("AMZN", "GOOGL", "META", "TSLA", "AVGO")
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


def watch_symbol(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", value)


def discover_stocks(movers, news, now):
    pinned = set(MARKET_SYMBOLS + ALPACA_EXTRA_SYMBOLS)
    active = {}
    for side in ("gainers", "losers"):
        count = 0
        for item in movers.get(side, []):
            symbol, price, move = item.get("symbol"), item.get("price"), item.get("percent_change")
            if (
                not watch_symbol(symbol) or symbol in pinned or symbol in active
                or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0
                or not isinstance(move, (int, float)) or not math.isfinite(move) or abs(move) < 3
            ):
                continue
            active[symbol] = dict(
                ticker=symbol, price=price, change_percent=move,
                source="Alpaca SIP movers", as_of=movers.get("last_updated"),
            )
            count += 1
            if count == 2:
                break

    recent = []
    for item in news.get("news", []):
        try:
            published = datetime.fromisoformat(item.get("created_at", ""))
            if not now - timedelta(hours=24) <= published <= now:
                continue
        except (ValueError, TypeError):
            continue
        if item.get("headline") and (item.get("url") or "").startswith("https://"):
            recent.append((published, item))
    news_count = 0
    for published, item in sorted(recent, key=lambda pair: pair[0], reverse=True):
        for symbol in item.get("symbols") or []:
            if not watch_symbol(symbol) or symbol in pinned:
                continue
            if symbol not in active:
                if news_count >= 4:
                    continue
                active[symbol] = dict(ticker=symbol, price=None, change_percent=None)
                news_count += 1
            active[symbol].setdefault("headline", dict(
                title=item["headline"], url=item["url"],
                source=item.get("source") or "Alpaca News", published=published.isoformat(),
            ))
    return list(active.values())


async def market_activity():
    try:
        headers = alpaca_headers()
    except ValueError:
        return []
    async with httpx.AsyncClient(timeout=6, headers=headers) as client:
        async def get(path, params):
            try:
                response = await client.get("https://data.alpaca.markets/" + path, params=params)
                response.raise_for_status()
                return response.json()
            except (ValueError, httpx.HTTPError):
                return {}

        movers, news = await asyncio.gather(
            get("v1beta1/screener/stocks/movers", {"top": 15}),
            get("v1beta1/news", {"limit": 30, "sort": "desc"}),
        )
        activity = discover_stocks(movers, news, datetime.now(timezone.utc))
        headline_symbols = [item["ticker"] for item in activity if item["price"] is None]
        snapshots = {}
        feed = os.getenv("LEDGER_ALPACA_FEED", "iex")
        if headline_symbols:
            snapshots = await get("v2/stocks/snapshots", {
                "symbols": ",".join(headline_symbols), "feed": feed,
            })
        stocks = []
        for item in activity:
            if item["price"] is None:
                stock = snapshots.get(item["ticker"])
                if not stock:
                    continue
                trade = stock.get("latestTrade") or {}
                price = trade.get("p")
                previous = (stock.get("prevDailyBar") or {}).get("c")
                item.update(
                    price=price, as_of=trade.get("t"), source=f"Alpaca {feed.upper()}",
                    change_percent=(price / previous - 1) * 100 if price and previous else None,
                )
            stocks.append(item)
        return stocks


class MarketBrief:
    def __init__(self, quotes):
        self.quotes = quotes
        self.lock = asyncio.Lock()
        self.cached = None
        self.expires = 0
        self.news = []
        self.news_expires = 0

    async def get(self):
        async with self.lock:
            if self.cached and self.expires > time.monotonic():
                return self.cached
            (prices, errors), activity = await asyncio.gather(self.get_prices(), market_activity())
            if self.news_expires <= time.monotonic():
                feeds = await news_sources()
                for source, result in feeds.items():
                    if not isinstance(result, Exception) and result:
                        self.news = [
                            item for item in self.news if item["source"] != source
                        ] + result[:4]
                self.news.sort(key=lambda item: item["published"], reverse=True)
                self.news_expires = time.monotonic() + 900
            refresh = 60 if any(p["refresh_seconds"] for p in prices) else 900
            self.cached = dict(
                quotes=prices,
                headlines=self.news[:10],
                warnings=errors,
                activity=activity,
                refresh_seconds=refresh,
            )
            self.expires = time.monotonic() + refresh
            return self.cached

    async def get_prices(self):
        prices, errors = [], []
        symbols = MARKET_SYMBOLS
        if os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY"):
            symbols += ALPACA_EXTRA_SYMBOLS
        for symbol in symbols:
            try:
                prices.append(await self.quotes.get(symbol))
            except ValueError:
                errors.append(symbol)
        return prices, [f"Quotes unavailable: {', '.join(errors)}."] if errors else []
