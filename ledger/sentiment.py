import asyncio
import csv
import math
from datetime import date, timedelta
from statistics import median

import httpx

FINRA_BASE = "https://cdn.finra.org/equity/regsho/daily"
_finra_files = {}


async def finra_day(client, session):
    if session in _finra_files:
        return _finra_files[session]
    stamp = session.replace("-", "")
    url = f"{FINRA_BASE}/CNMSshvol{stamp}.txt"
    try:
        response = await client.get(url, timeout=5)
        response.raise_for_status()
    except httpx.HTTPError:
        return {}
    ratios = {}
    for row in csv.DictReader(response.text.splitlines(), delimiter="|"):
        if row.get("Date") != stamp:
            continue
        try:
            short, total = float(row["ShortVolume"]), float(row["TotalVolume"])
            if math.isfinite(total) and 0 <= short <= total and total > 0:
                ratios[row["Symbol"]] = 100 * short / total
        except (KeyError, ValueError, TypeError):
            continue
    if ratios:
        if len(_finra_files) >= 16:
            _finra_files.pop(next(iter(_finra_files)))
        _finra_files[session] = ratios
    return ratios


async def short_sale_evidence(client, ticker, dates):
    files = await asyncio.gather(*(finra_day(client, day) for day in dates))
    observations = [(day, ratios[ticker]) for day, ratios in zip(dates, files) if ticker in ratios]
    if not observations:
        return None
    latest, ratio = observations[-1]
    earlier = [value for _, value in observations[:-1]]
    comparison = (
        f" Median across the preceding {len(earlier)} available sessions: {median(earlier):.1f}% "
        f"(latest minus median: {ratio - median(earlier):+.1f} percentage points)."
        if earlier else " No prior sessions were available for comparison."
    )
    return dict(
        id="finra-short-volume",
        kind="sentiment",
        title=f"{ticker} · FINRA daily short-sale volume",
        source="FINRA",
        url=f"{FINRA_BASE}/CNMSshvol{latest.replace('-', '')}.txt",
        published=latest,
        text=(
            f"On {latest}, {ratio:.1f}% of FINRA-reported off-exchange share volume was "
            f"marked short, excluding short-exempt trades from the numerator.{comparison} "
            "This measures trade activity on covered facilities, not outstanding short interest, "
            "investor conviction, or a directional price signal. Market making and hedging can affect it."
        ),
    )


def news_tone_evidence(article, ticker, as_of, index):
    stamp = article.get("time_published", "")[:8]
    url = article.get("url") or ""
    if not url.startswith("https://"):
        return None
    try:
        published = date.fromisoformat(stamp)
    except ValueError:
        return None
    if not as_of - timedelta(days=7) <= published <= as_of:
        return None
    for item in article.get("ticker_sentiment", []):
        if item.get("ticker") != ticker:
            continue
        try:
            score = float(item["ticker_sentiment_score"])
            relevance = float(item["relevance_score"])
        except (KeyError, TypeError, ValueError):
            continue
        if -1 <= score <= 1 and 0.5 <= relevance <= 1:
            return dict(
                id=f"news-tone-{index}", kind="sentiment",
                title=article["title"], source="Alpha Vantage news tone", url=url,
                published=published.isoformat(),
                text=(
                    f"Alpha Vantage scored this article's tone about {ticker} at {score:+.2f} "
                    f"on a −1 to +1 scale, with ticker relevance {relevance:.2f}. "
                    "This measures tone in this article, not investor attitudes or positioning."
                ),
            )
    return None
