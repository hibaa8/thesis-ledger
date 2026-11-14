"""Local-only trade planning tools; Robinhood's MCP handles order review and approval."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

from .config import load_config
from .harness import Harness
from .models import ResearchRequest
from .store import open_store
from .trading import TradePlanner


def create_trader_mcp(store=None):
    store = store or open_store()
    harness = Harness(store)
    planner = TradePlanner(store)
    mcp = FastMCP("Thesis Ledger Trade Planner")

    @mcp.tool()
    async def research_and_prepare_trade(ticker: str, amount_usd: float = 25) -> dict:
        """Run today's live analyst workflow and reserve a capped STOCK/ETF trade proposal. This does not place an order. If the result abstains, fails risk review, or conflicts with the forecast, it returns no proposal. Before sending any order through Robinhood MCP, confirm its Trade approvals setting is ON and review the exact order. The account holder must manually approve in Robinhood."""
        if os.getenv("LEDGER_TRADING_ENABLED") != "1":
            raise ValueError("Trading proposals are disabled. Set LEDGER_TRADING_ENABLED=1 locally.")
        request = ResearchRequest(
            ticker=ticker.upper(),
            as_of=datetime.now(ZoneInfo("America/New_York")).date(),
            mode="live",
        )
        run = await harness.run(request)
        if run["status"] != "complete":
            raise ValueError("Research did not complete; no trade proposal generated")
        return planner.prepare(run["id"], amount_usd)

    @mcp.tool()
    def prepare_trade_from_research(run_id: str, amount_usd: float = 25) -> dict:
        """Reserve a capped STOCK/ETF proposal from a completed live research run dated today. This never places an order. Robinhood's Trade approvals must be ON before any broker order request; the account holder approves in the Robinhood app."""
        return planner.prepare(run_id, amount_usd)

    return mcp


def main():
    load_config()
    create_trader_mcp().run(transport="stdio")


if __name__ == "__main__":
    main()
