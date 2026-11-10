# Research foundations

I built Thesis Ledger around four ideas: separate analyst roles, opposing research cases, a numerical forecast that enters after debate, and memory that can be revised with its provenance intact.

| Reference | What I adopted | How I adapted it |
|---|---|---|
| [TradingAgents](https://arxiv.org/abs/2412.20138) | Specialized analysts, bull/bear debate, synthesis, and risk review | I use a bounded research workflow with cited reports and explicit abstention. The sentiment role calls out missing social evidence. |
| [Kronos](https://arxiv.org/abs/2508.02739) | Candlestick forecasting | I added an optional Kronos-small adapter and summarize sampled paths as scenarios. The manager sees them after the debate. |
| [SimpleMem](https://arxiv.org/abs/2601.02553) | Compact, relevant long-term memory | I store structured theses in SQLite and filter by ticker, mode, and availability date before ranking by lexical overlap. |
| [ReHarness](https://arxiv.org/abs/2610.12668) | Forward retrieval and backward revision | I let people narrow or retire a thesis through append-only reviews. The original thesis and source snapshot remain available for audit. |

The [Trading-R1 project](https://github.com/TauricResearch/Trading-R1) also informed the research interface. I use the same research workflow in the browser and over MCP so that the interaction surface does not change how evidence is gathered and reviewed.
