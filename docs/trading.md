# Approval-gated trade planning

Thesis Ledger can produce a small stock or ETF trade proposal from a fresh, completed live research run. It does **not** place brokerage orders or trade from the public website. The local trade planner runs as a separate MCP server alongside Robinhood's [official Trading MCP](https://robinhood.com/us/en/support/articles/onboarding-an-external-agent/). Robinhood receives an order request only after its own trade approvals setting has been verified as on; the account holder must then manually review and place the proposed order in the Robinhood app.

## Scope and limits

- Long stocks and ETFs only. No options, crypto, short selling, margin, or account transfers.
- Maximum proposed notional: **$25 per trade** and **$100 per New York calendar day**. Proposals reserve this budget even if later declined, so the limit fails conservatively. Reusing a run returns its existing proposal; changing the amount requires a new research run.
- The research run must be **live, completed, and dated today**. Demo runs, abstentions, stale-data warnings, and research/forecast disagreement cannot produce proposals.
- A bearish finding can only become a sell proposal. Before requesting any sell order, check the account holds enough shares. The planner never authorizes short sales.
- The local proposal ledger is stored in SQLite on the machine running the trader MCP. Do not run multiple trader MCP hosts against the same Robinhood account until a shared budget ledger is implemented.

## Connect

1. Open a dedicated Robinhood MCP account and authenticate the official Robinhood Trading MCP. Account opening and funding are completed by the account holder in Robinhood. Robinhood says the agent can trade only in that dedicated account.
2. In the Robinhood app, go to the **MCP account → Agent Settings → Safety Controls** and turn **Trade approvals** on. Robinhood says this setting is off by default for external-agent MCP accounts.
3. Install this project locally with `uv sync --extra dev` and keep a private `.env` with the research provider credentials. Set `LEDGER_TRADING_ENABLED=1` in that private `.env` to enable proposal generation. It does not enable order submission.
4. Connect this local tool in Codex with `codex mcp add thesis-ledger-trader --env LEDGER_TRADING_ENABLED=1 -- uv --directory /path/to/thesis-ledger run python -m ledger.trader_mcp`. Connect Robinhood with `codex mcp add robinhood-trading --url https://agent.robinhood.com/mcp/trading` and complete its OAuth flow. Restart Codex or open a new session after adding MCP servers so their tools become available.

## Review sequence

1. Ask Thesis Ledger's `research_and_prepare_trade` tool to analyze one ticker. The response contains the run ID, decision, risk review, side, amount, and evidence IDs. Read the full research report before proceeding.
2. Ask Robinhood `get_trade_approval_setting`. **Stop if it is off or cannot be read.**
3. Check Robinhood tradability, current quote, buying power, and existing position for a sell. Confirm the asset is a stock or ETF.
4. Ask Robinhood `review_equity_order` with the exact proposed side and amount. Stop on any blocking warning or if the quote/order differs materially from the reviewed proposal.
5. Only then call `place_equity_order` to create Robinhood's pending approval request. The account holder reviews and manually places it in the Robinhood app. Do not treat a pending approval as a fill. Reconcile through Robinhood order history.

The [TradingAgents paper](https://arxiv.org/abs/2412.20138) inspired the analyst/debate/manager/risk sequence. Thesis Ledger adds a separate human approval boundary. Research and forecast outputs are not validated trading signals; paper performance does not establish expected returns for this implementation.
