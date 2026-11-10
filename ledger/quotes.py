import asyncio
import math
import os
import time

import httpx

from .models import ResearchRequest
from .store import now


def quote_interval():
    if os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY"):
        return 15
    return 60 if os.getenv("LEDGER_AV_REALTIME") == "1" else 0


class Quotes:
    def __init__(self):
        self.cache = {}
        self.lock = asyncio.Lock()

    async def get(self, ticker):
        ticker = ResearchRequest(ticker=ticker.upper()).ticker
        interval = quote_interval()
        async with self.lock:
            cached = self.cache.get(ticker)
            if cached and time.monotonic() - cached[0] < (interval or 900):
                return cached[1]
            try:
                quote = await self.fetch(ticker)
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "Quote unavailable. Check the provider key, feed entitlement, or request limit."
                ) from None
            if len(self.cache) >= 128:
                self.cache.pop(next(iter(self.cache)))
            self.cache[ticker] = (time.monotonic(), quote)
            return quote

    async def fetch(self, ticker):
        async with httpx.AsyncClient(timeout=10) as client:
            if os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY"):
                feed = os.getenv("LEDGER_ALPACA_FEED", "iex")
                if feed not in {"iex", "sip"}:
                    raise ValueError("Unsupported Alpaca feed")
                response = await client.get(
                    f"https://data.alpaca.markets/v2/stocks/{ticker}/trades/latest",
                    params={"feed": feed},
                    headers={
                        "APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"],
                        "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"],
                    },
                )
                response.raise_for_status()
                trade = response.json()["trade"]
                price, as_of = float(trade["p"]), trade["t"]
                source, freshness = f"Alpaca {feed.upper()}", "Latest trade"
            else:
                key = os.getenv("ALPHAVANTAGE_API_KEY")
                if not key:
                    raise ValueError("Missing market key")
                params = {"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": key}
                realtime = os.getenv("LEDGER_AV_REALTIME") == "1"
                if realtime:
                    params["entitlement"] = "realtime"
                response = await client.get(
                    "https://www.alphavantage.co/query", params=params
                )
                response.raise_for_status()
                data = response.json()["Global Quote"]
                price, as_of = float(data["05. price"]), data["07. latest trading day"]
                source = "Alpha Vantage"
                freshness = (
                    "Real-time entitlement · trading date only"
                    if realtime
                    else "End-of-day quote"
                )
        if not math.isfinite(price) or price <= 0 or not as_of:
            raise ValueError("Invalid quote")
        return dict(
            ticker=ticker,
            price=price,
            as_of=as_of,
            source=source,
            freshness=freshness,
            fetched_at=now(),
            refresh_seconds=quote_interval(),
        )
