"""Point-in-time fundamentals from SEC EDGAR company facts."""

import math
import os
import re
from datetime import date
from time import monotonic

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts"
METRICS = {
    "Revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"),
    "Operating income": ("OperatingIncomeLoss",),
    "Net income": ("NetIncomeLoss", "ProfitLoss"),
    "Operating cash flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "Cash and cash equivalents": ("CashAndCashEquivalentsAtCarryingValue",),
    "Total assets": ("Assets",),
    "Total liabilities": ("Liabilities",),
}
BALANCE_SHEET = {"Cash and cash equivalents", "Total assets", "Total liabilities"}
FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A"}
_ticker_cache = (0.0, {})


def filing_evidence(data, cik, as_of):
    gaap = data.get("facts", {}).get("us-gaap", {})
    cutoff = as_of.isoformat()
    filings = {}
    for label, tags in METRICS.items():
        for tag in tags:
            for fact in gaap.get(tag, {}).get("units", {}).get("USD", []):
                filed, end, accession, form = (
                    fact.get(key, "") for key in ("filed", "end", "accn", "form")
                )
                value = fact.get("val")
                if (
                    form not in FORMS
                    or not end or not filed or not end <= filed <= cutoff
                    or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession)
                    or not isinstance(value, (int, float)) or not math.isfinite(value)
                ):
                    continue
                start = fact.get("start")
                if label in BALANCE_SHEET:
                    if start:
                        continue
                else:
                    if not start:
                        continue
                    days = (date.fromisoformat(end) - date.fromisoformat(start)).days
                    lower, upper = (60, 120) if form.startswith("10-Q") else (300, 400)
                    if not lower <= days <= upper:
                        continue
                fields = filings.setdefault((end, filed, accession, form), {})
                fields.setdefault(label, value)
    if not filings:
        raise ValueError("No usable SEC filing facts by the analysis date.")

    # Prefer the latest reporting period, then the latest filing for that period.
    end, filed, accession, form = max(filings)
    fields = filings[end, filed, accession, form]
    amounts = "; ".join(f"{label}: USD {value:,.0f}" for label, value in fields.items())
    period = "quarterly" if form.startswith("10-Q") else "annual"
    return {
        "id": "fundamentals",
        "kind": "fundamentals",
        "title": f"{data['entityName']} · SEC Form {form}",
        "source": "SEC EDGAR",
        "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{accession}-index.html",
        "published": filed,
        "text": (
            f"Filed {filed}. Reporting period ended {end}. Income and cash-flow figures are {period}; "
            f"balance-sheet figures are as of period end. {amounts}. "
            "Filing facts do not provide current valuation multiples."
        ),
    }


async def sec_fundamentals(client, ticker, as_of):
    global _ticker_cache
    headers = {
        "User-Agent": os.getenv(
            "LEDGER_SEC_USER_AGENT",
            "Thesis Ledger research (https://thesis-ledger.onrender.com/)",
        ),
        "Accept": "application/json",
    }
    expires, tickers = _ticker_cache
    if monotonic() >= expires:
        response = await client.get(TICKERS_URL, headers=headers, timeout=8)
        response.raise_for_status()
        tickers = {
            row["ticker"]: int(row["cik_str"]) for row in response.json().values()
        }
        _ticker_cache = (monotonic() + 86400, tickers)
    cik = tickers.get(ticker) or tickers.get(ticker.replace(".", "-"))
    if not cik:
        raise ValueError("Ticker has no SEC CIK mapping.")
    response = await client.get(f"{FACTS_URL}/CIK{cik:010}.json", headers=headers, timeout=10)
    response.raise_for_status()
    return filing_evidence(response.json(), cik, as_of)
