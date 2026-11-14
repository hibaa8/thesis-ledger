"""Conservative, local-only order proposals from completed research runs."""

import os
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .store import now

EASTERN = ZoneInfo("America/New_York")


def _cents(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Amount must be a valid dollar value") from exc
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
        raise ValueError("Amount must be positive dollars and cents")
    return int(amount * 100)


class TradePlanner:
    """Prepare a bounded trade request; Robinhood and the user handle execution."""

    def __init__(self, store, *, max_trade_usd=25, max_daily_usd=100):
        self.store = store
        self.max_trade_cents = _cents(max_trade_usd)
        self.max_daily_cents = _cents(max_daily_usd)

    def prepare(self, run_id: str, amount_usd=25, *, current_time=None):
        if os.getenv("LEDGER_TRADING_ENABLED") != "1":
            raise ValueError("Trading proposals are disabled. Set LEDGER_TRADING_ENABLED=1 locally.")
        if not run_id or len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
            raise ValueError("Invalid research run ID")
        amount_cents = _cents(amount_usd)
        if amount_cents > self.max_trade_cents:
            raise ValueError("Amount exceeds the per-trade proposal limit")
        run = self.store.get(run_id)
        request = run.get("request", {})
        decision = run.get("decision", {})
        current_time = current_time or datetime.now(EASTERN)
        day = current_time.astimezone(EASTERN).date().isoformat()
        if run.get("status") != "complete" or request.get("mode") != "live":
            raise ValueError("Only completed live research can produce a trade proposal")
        if request.get("as_of") != day:
            raise ValueError("Research must be rerun today before proposing a trade")
        if any("STALE" in str(w).upper() for w in run.get("snapshot", {}).get("warnings", [])):
            raise ValueError("Research contains a stale-data warning")
        if run.get("disagreement"):
            raise ValueError("Research and forecast disagree; no trade proposal generated")
        if run.get("reports", {}).get("risk", {}).get("stance") == "abstain":
            raise ValueError("Risk review abstained; no trade proposal generated")
        stance = decision.get("stance")
        if stance not in ("bullish", "bearish") or not decision.get("evidence_ids"):
            raise ValueError("Research has no evidence-backed directional decision")
        risk_stance = run["reports"]["risk"].get("stance")
        if risk_stance in ("bullish", "bearish") and risk_stance != stance:
            raise ValueError("Risk review conflicts with the directional decision")
        side = "buy" if stance == "bullish" else "sell"
        proposal = {
            "id": uuid.uuid4().hex,
            "run_id": run_id,
            "created": now(),
            "trade_date": day,
            "ticker": request["ticker"],
            "asset_class": "equity_or_etf",
            "side": side,
            "notional_cents": amount_cents,
            "amount_usd": f"{Decimal(amount_cents) / 100:.2f}",
            "status": "proposal_only",
            "thesis": decision["summary"],
            "invalidation": decision["invalidation"],
            "risk_review": run["reports"]["risk"]["summary"],
            "evidence_ids": decision["evidence_ids"],
            "broker_steps": [
                "Confirm Robinhood MCP trade approvals are ON. Stop if OFF or unavailable.",
                "Confirm ticker is a tradable stock or ETF; do not use options or crypto.",
                "Check current quote, buying power, and position if selling.",
                "Review the exact order with Robinhood before sending its approval request.",
                "The account holder must manually approve and place it in the Robinhood app.",
            ],
        }
        return self.store.reserve_trade_proposal(proposal, self.max_daily_cents)
