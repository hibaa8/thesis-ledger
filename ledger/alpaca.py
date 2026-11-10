import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx


def alpaca_headers():
    key = os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise ValueError("Configure Alpaca market data credentials first.")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


async def daily_bars(ticker, cutoff):
    market_tz = ZoneInfo("America/New_York")
    feed = os.getenv("LEDGER_ALPACA_FEED", "iex")
    if feed not in {"iex", "sip"}:
        raise ValueError("Unsupported Alpaca feed.")
    async with httpx.AsyncClient(timeout=10, headers=alpaca_headers()) as client:
        response = await client.get(
            "https://data.alpaca.markets/v2/stocks/bars",
            params={
                "symbols": ticker,
                "timeframe": "1Day",
                "feed": feed,
                "start": (cutoff - timedelta(days=160)).isoformat(),
                "end": datetime.combine(
                    cutoff, datetime.max.time(), market_tz
                ).isoformat(),
                "limit": 1000,
                "adjustment": "raw",
            },
        )
        response.raise_for_status()
        rows = (response.json().get("bars") or {}).get(ticker) or []
    return [
        dict(
            date=datetime.fromisoformat(row["t"]).astimezone(market_tz).date().isoformat(),
            open=float(row["o"]),
            high=float(row["h"]),
            low=float(row["l"]),
            close=float(row["c"]),
            volume=float(row["v"]),
        )
        for row in rows
    ], f"Alpaca {feed.upper()}"


async def intraday(ticker):
    from .data import CAL

    now = datetime.now(timezone.utc)
    latest = CAL.date_to_session(now.date(), direction="previous")
    sessions = CAL.sessions_window(latest, -2)
    feed = os.getenv("LEDGER_ALPACA_FEED", "iex")
    if feed not in {"iex", "sip"}:
        raise ValueError("Unsupported Alpaca feed.")
    async with httpx.AsyncClient(timeout=10, headers=alpaca_headers()) as client:
        for session in reversed(sessions):
            opened = CAL.session_open(session).to_pydatetime()
            closed = CAL.session_close(session).to_pydatetime()
            if now <= opened:
                continue
            response = await client.get(
                "https://data.alpaca.markets/v2/stocks/bars",
                params={
                    "symbols": ticker,
                    "timeframe": "5Min",
                    "feed": feed,
                    "start": opened.isoformat(),
                    "end": min(now, closed).isoformat(),
                    "limit": 100,
                },
            )
            response.raise_for_status()
            rows = (response.json().get("bars") or {}).get(ticker) or []
            rows = [row for row in rows if datetime.fromisoformat(row["t"]) < closed]
            if rows:
                return {
                    "ticker": ticker,
                    "feed": feed.upper(),
                    "session": str(session.date()),
                    "open": opened.isoformat(),
                    "close": closed.isoformat(),
                    "bars": rows,
                }
    raise ValueError("No recent regular-session bars are available for this symbol.")


async def company_news(ticker):
    async with httpx.AsyncClient(timeout=8, headers=alpaca_headers()) as client:
        response = await client.get(
            "https://data.alpaca.markets/v1beta1/news",
            params={"symbols": ticker, "sort": "desc", "limit": 10},
        )
        response.raise_for_status()
    return [
        {
            "title": item["headline"],
            "url": item["url"],
            "published": item["created_at"],
            "source": item["source"],
            "summary": (item.get("summary") or "")[:1800],
        }
        for item in response.json().get("news", [])
        if ticker in item.get("symbols", [])
        and item.get("url", "").startswith("https://")
    ]
