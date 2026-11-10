from datetime import date

from ledger.sec import filing_evidence


def test_sec_fundamentals_use_one_filing_and_respect_as_of():
    filing = {
        "start": "2026-04-01",
        "end": "2026-06-30",
        "filed": "2026-08-01",
        "accn": "0000001234-26-000001",
        "form": "10-Q",
        "val": 2000,
    }
    restatement = dict(filing, filed="2026-09-01", accn="0000001234-26-000002", val=9000)
    year_to_date = dict(filing, start="2026-01-01", val=5000)
    data = {
        "entityName": "Example Corp",
        "facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [restatement, year_to_date, filing]}},
        }},
    }
    evidence = filing_evidence(data, 1234, date(2026, 8, 15))
    assert evidence["published"] == "2026-08-01"
    assert "Revenue: USD 2,000" in evidence["text"]
    assert evidence["url"].endswith("/000000123426000001/0000001234-26-000001-index.html")
