"""Compare 60 and 504 recent returns on matched, local walk-forward tests."""

import argparse
import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import numpy as np
import pandas as pd

from ledger.alpaca import alpaca_headers
from ledger.config import load_config
from ledger.data import sessions, validate_bars
from ledger.forecast import forecast

SYMBOLS = (
    "SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "JPM",
    "GOOGL", "AMZN", "META", "TSLA", "AVGO", "XOM", "CVX", "JNJ",
    "UNH", "WMT", "COST", "PG", "KO", "CAT", "GE", "NEE",
)
ORIGINAL = {"SPY", "QQQ", "AAPL", "MSFT", "NVDA", "JPM"}
START = "2021-01-01"
PERIODS = (("2024–25", "2024-01-01", "2025-12-31"), ("2026", "2026-01-01", "2026-11-09"))
END = PERIODS[-1][-1]
LOOKBACK = 504
TZ = ZoneInfo("America/New_York")


def download_bars():
    load_config()
    params = dict(
        symbols=",".join(SYMBOLS), timeframe="1Day", feed="sip",
        start=START, end=datetime.combine(date.fromisoformat(END), time(23, 59), TZ).isoformat(),
        adjustment="split", limit=10000,
    )
    data = {ticker: [] for ticker in SYMBOLS}
    with httpx.Client(headers=alpaca_headers(), timeout=30) as client:
        while True:
            response = client.get("https://data.alpaca.markets/v2/stocks/bars", params=params)
            response.raise_for_status()
            page = response.json()
            for ticker, rows in page["bars"].items():
                data[ticker].extend(
                    dict(
                        date=datetime.fromisoformat(row["t"]).astimezone(TZ).date().isoformat(),
                        open=float(row["o"]), high=float(row["h"]), low=float(row["l"]),
                        close=float(row["c"]), volume=float(row["v"]),
                    )
                    for row in rows
                )
            if not (token := page.get("next_page_token")):
                return data
            params["page_token"] = token


def compare(data):
    calendar = {day: i for i, day in enumerate(sessions(START, END))}
    rows = []
    for ticker in SYMBOLS:
        bars = validate_bars(data[ticker], date.fromisoformat(END))
        indices = [calendar[bar["date"]] for bar in bars]
        closes = np.array([bar["close"] for bar in bars])
        log_prices = np.log(closes)
        for period, start, end in PERIODS:
            first = next(i for i, bar in enumerate(bars) if bar["date"] >= start)
            last = next((i for i, bar in enumerate(bars) if bar["date"] > end), len(bars))
            for horizon in (5, 10):
                for i in range(max(first, LOOKBACK), last - horizon, horizon):
                    target = i + horizon
                    if indices[target] - indices[i - LOOKBACK] != LOOKBACK + horizon:
                        continue
                    point = forecast(bars[i - 60:i + 1], horizon)["points"][-1]
                    if point["date"] != bars[target]["date"]:
                        raise ValueError("Target date does not match the trading calendar.")
                    returns = np.diff(log_prices[i - LOOKBACK:i + 1])
                    draws = np.random.default_rng(42).choice(returns, size=(500, horizon))
                    long = np.quantile(closes[i] * np.exp(np.cumsum(draws, axis=1)[:, -1]), (0.1, 0.5, 0.9))
                    actual, origin = closes[target], closes[i]
                    for model, (low, median, high) in (
                        ("Current 60", (point["low"], point["median"], point["high"])),
                        ("Long 504", long),
                    ):
                        miss = max(low - actual, actual - high, 0)
                        rows.append(dict(
                            ticker=ticker, universe="original" if ticker in ORIGINAL else "added",
                            period=period, horizon=horizon, model=model,
                            origin=bars[i]["date"], target=bars[target]["date"],
                            actual=actual, low=low, median=median, high=high,
                            mape=100 * abs(median - actual) / actual,
                            coverage=100 * (low <= actual <= high),
                            width=100 * (high - low) / origin,
                            interval_score=100 * (high - low + 10 * miss) / origin,
                            no_change_mape=100 * abs(origin - actual) / actual,
                        ))
    return pd.DataFrame(rows)


def summarize(windows, keys):
    groups = windows.groupby([*keys, "model"])
    return groups[["mape", "coverage", "width", "interval_score", "no_change_mape"]].mean().assign(windows=groups.size())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/bootstrap-history-study"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cache = args.output / "alpaca-sip-split-bars.json"
    if cache.exists():
        data = json.loads(cache.read_text())
    else:
        data = download_bars()
        cache.write_text(json.dumps(data))
    windows = compare(data)
    windows.to_csv(args.output / "windows.csv", index=False, float_format="%.6f")
    for label, keys in (
        ("summary", ["period", "horizon"]),
        ("by-ticker", ["period", "horizon", "ticker"]),
        ("by-universe", ["period", "horizon", "universe"]),
    ):
        summary = summarize(windows, keys)
        summary.to_csv(args.output / f"{label}.csv", float_format="%.6f")
        if label == "summary":
            print(summary.round(3).to_string())


if __name__ == "__main__":
    main()
