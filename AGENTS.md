# Trade execution boundary

The public Thesis Ledger website and its research MCP are research tools. Only the separate local `thesis-ledger-trader` MCP may generate trade proposals. It cannot place orders.

When working with Robinhood's official Trading MCP for this project:

1. Handle long stocks and ETFs only. Never request options, crypto, short sales, margin, funding, or transfers.
2. Obtain a current Thesis Ledger proposal from a completed live research run. Observe its $25 per-trade and $100 per-day limits. Do not change the proposed ticker, side, or amount without a new proposal.
3. Check `get_trade_approval_setting` immediately before any order request. If approvals are not positively confirmed ON, stop. Robinhood's external-agent accounts default to approvals off.
4. Check tradability, current quote, buying power, and any existing position needed for a sell. Use `review_equity_order` on the exact proposed order and stop on blocking warnings.
5. Send an order request only when it will become a pending approval that the account holder must manually review and place in Robinhood. Never interpret a pending approval as a fill. Check order status separately.
6. Do not place a real trade as a test. Do not accept brokerage agreements, open or fund accounts, or handle login credentials for the user.

See `docs/trading.md` for the complete workflow.
