import asyncio
import hashlib
import math
import os
from datetime import date, datetime, timedelta, timezone
import httpx
import numpy as np
import pandas as pd
import exchange_calendars as xcals

CAL = xcals.get_calendar("XNYS")


def sessions(start, end):
    return [d.strftime("%Y-%m-%d") for d in CAL.sessions_in_range(str(start), str(end))]


def future_sessions(last, count):
    start = date.fromisoformat(last) + timedelta(days=1)
    return sessions(start, start + timedelta(days=count * 3 + 15))[:count]


def validate_bars(bars, as_of):
    clean = [b for b in bars if b["date"] <= str(as_of)]
    clean.sort(key=lambda b: b["date"])
    if len(clean) < 35 or len({b["date"] for b in clean}) != len(clean):
        raise ValueError("At least 35 unique daily bars are required")
    for b in clean:
        if not all(
            math.isfinite(float(b[k]))
            for k in ["open", "high", "low", "close", "volume"]
        ):
            raise ValueError("Non-finite market data")
        if min(b[k] for k in ["open", "high", "low", "close"]) <= 0 or b["volume"] < 0:
            raise ValueError("Invalid price or volume")
        if b["high"] < max(b["open"], b["close"]) or b["low"] > min(
            b["open"], b["close"]
        ):
            raise ValueError("Inconsistent OHLC bar")
    return clean


def demo_snapshot(ticker, as_of):
    # Synthetic, reproducible fixtures. Never passed off as exchange data.
    seed = int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    days = sessions(as_of - timedelta(days=180), as_of)[-100:]
    price = {"NVDA": 120.0, "AAPL": 185.0, "MSFT": 390.0, "SPY": 510.0}.get(
        ticker, 100.0
    )
    bars = []
    for d in days:
        o = price
        price = o * np.exp(rng.normal(0.0012, 0.016))
        spread = abs(rng.normal(0.008, 0.004))
        bars.append(
            dict(
                date=d,
                open=round(o, 4),
                high=round(max(o, price) * (1 + spread), 4),
                low=round(min(o, price) * (1 - spread), 4),
                close=round(price, 4),
                volume=int(rng.integers(12_000_000, 80_000_000)),
            )
        )
    evidence = [
        dict(
            id="prices",
            kind="market",
            title="Synthetic daily OHLCV fixture",
            url=None,
            published=days[-1],
            text="Illustrative generated prices; not real market history.",
        ),
        dict(
            id="fundamentals",
            kind="fundamentals",
            title="Illustrative company fundamentals",
            url=None,
            published=days[-1],
            text="Synthetic fixture: revenue growth 18%, operating margin 27%, forward P/E 32. These are invented demonstration values.",
        ),
        dict(
            id="news",
            kind="news",
            title="Illustrative demand and concentration scenario",
            url=None,
            published=days[-1],
            text="Invented scenario: demand is growing, but customer concentration and supply constraints remain material risks. No real news is represented.",
        ),
    ]
    return dict(
        bars=bars,
        evidence=evidence,
        provider="Synthetic demo",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        warnings=[
            "All demo prices, company facts, and analyst narratives are illustrative."
        ],
    )


async def snapshot(req):
    if req.mode == "demo":
        return demo_snapshot(req.ticker, req.as_of)
    key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not key:
        raise ValueError(
            "Live data requires ALPHAVANTAGE_API_KEY. Select Demo to explore without credentials."
        )
    async with httpx.AsyncClient(timeout=30) as client:
        last_request = None

        async def get(function, **params):
            nonlocal last_request
            clock = asyncio.get_running_loop()
            if last_request is not None:
                await asyncio.sleep(max(0, 1.1 - (clock.time() - last_request)))
            last_request = clock.time()
            r = await client.get(
                "https://www.alphavantage.co/query",
                params=dict(function=function, apikey=key, **params),
            )
            r.raise_for_status()
            data = r.json()
            if any(k in data for k in ["Error Message", "Note", "Information"]):
                raise ValueError(
                    "Market provider rejected the request or reached its rate limit"
                )
            return data

        prices = await get("TIME_SERIES_DAILY", symbol=req.ticker, outputsize="compact")
        rows = prices.get("Time Series (Daily)", {})
        if not rows:
            raise ValueError("Provider returned no daily bars")
        bars = [
            dict(
                date=d,
                open=float(v["1. open"]),
                high=float(v["2. high"]),
                low=float(v["3. low"]),
                close=float(v["4. close"]),
                volume=float(v["5. volume"]),
            )
            for d, v in rows.items()
        ]
        # Never use today's potentially unfinished daily candle.
        cutoff = min(req.as_of, date.today() - timedelta(days=1))
        bars = validate_bars(bars, cutoff)
        evidence = [
            dict(
                id="prices",
                kind="market",
                title=f"{req.ticker} daily unadjusted OHLCV",
                url="https://www.alphavantage.co/documentation/#daily",
                published=bars[-1]["date"],
                text=f"{len(bars)} daily bars through {bars[-1]['date']}. Unadjusted: splits can distort signals.",
            )
        ]
        warnings = [
            "Daily bars are unadjusted. Corporate actions can distort forecasts.",
            "Social sentiment is unavailable; news is not a proxy for social sentiment.",
        ]
        if req.as_of == date.today():
            for function, kind, params in [
                ("OVERVIEW", "fundamentals", dict(symbol=req.ticker)),
                (
                    "NEWS_SENTIMENT",
                    "news",
                    dict(
                        tickers=req.ticker,
                        limit=10,
                        time_to=req.as_of.strftime("%Y%m%d") + "T2359",
                    ),
                ),
            ]:
                try:
                    raw = await get(function, **params)
                    if kind == "fundamentals" and raw.get("Symbol"):
                        text = str(
                            {
                                k: raw.get(k)
                                for k in [
                                    "Name",
                                    "Sector",
                                    "MarketCapitalization",
                                    "PERatio",
                                    "ForwardPE",
                                    "OperatingMarginTTM",
                                    "QuarterlyRevenueGrowthYOY",
                                    "LatestQuarter",
                                ]
                            }
                        )
                        evidence.append(
                            dict(
                                id=kind,
                                kind=kind,
                                title="Current company overview (not point-in-time)",
                                url="https://www.alphavantage.co/documentation/#company-overview",
                                published=str(req.as_of),
                                text=text,
                            )
                        )
                    if kind == "news":
                        for i, n in enumerate(raw.get("feed", [])):
                            published = n.get("time_published", "")[:8]
                            if not published or published > req.as_of.strftime(
                                "%Y%m%d"
                            ):
                                continue
                            evidence.append(
                                dict(
                                    id=f"news-{i}",
                                    kind=kind,
                                    title=n["title"],
                                    url=n.get("url"),
                                    published=published,
                                    text=n.get("summary", "")[:1800],
                                )
                            )
                except (ValueError, httpx.HTTPError):
                    warnings.append(
                        f"{kind.title()} unavailable; research must abstain on missing evidence."
                    )
        else:
            warnings.append(
                "Historical runs exclude current fundamentals and news to avoid look-ahead leakage."
            )
    if (req.as_of - date.fromisoformat(bars[-1]["date"])).days > 5:
        warnings.append(
            "STALE: latest market bar is more than five calendar days before the analysis date."
        )
    return dict(
        bars=bars,
        evidence=evidence,
        provider="Alpha Vantage",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        warnings=warnings,
    )


def metrics(bars):
    c = np.array([b["close"] for b in bars])
    ret = np.diff(np.log(c))
    delta = np.diff(c[-15:])
    gain = np.maximum(delta, 0).mean()
    loss = np.maximum(-delta, 0).mean()
    return dict(
        last=float(c[-1]),
        change=float((c[-1] / c[-2] - 1) * 100),
        sma20=float(c[-20:].mean()),
        sma50=float(c[-50:].mean()),
        rsi=float(100 - 100 / (1 + gain / loss)) if loss else (100.0 if gain else 50.0),
        volatility=float(ret.std(ddof=1) * np.sqrt(252) * 100),
        momentum=float((c[-1] / c[-21] - 1) * 100),
        regime="uptrend" if c[-1] > c[-20:].mean() else "downtrend",
    )
