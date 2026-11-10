# Thesis Ledger

An evidence-first financial research workspace: specialist analysts, bull/bear debate, independent forecast scenarios, risk review, and a thesis memory that can be revised without rewriting history.

**Local-first. Research only. No broker connection or trade execution.**

![Thesis Ledger dashboard with synthetic demo data](docs/assets/dashboard.jpg)

## Run locally

Python 3.11+ is required (3.12 recommended).

```sh
cd /Users/admin/Documents/thesis-ledger
uv sync --extra dev
uv run thesis-ledger
```

Open http://127.0.0.1:8000 and choose **Explore an NVDA demo**. Demo prices and company facts are synthetic; analyst reports are scripted. The demo exercises the same orchestration, storage, charting, and MCP paths without API credentials.

If using pip instead:

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/thesis-ledger
```

## Live research

```sh
cp .env.example .env
# Edit .env, then load it into your shell:
set -a
source .env
set +a
uv run thesis-ledger
```

Set `ALPHAVANTAGE_API_KEY`, `LLM_API_KEY`, and `LLM_MODEL`; optionally change `LLM_BASE_URL` to an OpenAI-compatible chat-completions endpoint. The provider must support JSON object output. Credentials stay on the server. The application does not automatically read `.env`; use the shell commands above.

Choose **Live providers** in the UI. Live failures are explicit: no synthetic data or scripted analyst fallback. Alpha Vantage supplies daily OHLCV, current company overview, and news when available. Account quotas and entitlements apply. Social sentiment is deliberately unavailable rather than fabricated. Daily data excludes today's potentially unfinished candle; corporate actions are not adjusted. Historical requests omit current fundamentals/news and require at least 35 bars from the provider's latest 100-bar window.

## Forecasting

- **Bootstrap baseline:** 500 reproducible sampled return paths, no model download.
- **Kronos-small:** real upstream tokenizer/model integration, 20 independent trajectories. Install separately as described in [Kronos setup](docs/kronos.md). It never silently substitutes the baseline.
- The shaded 10–90% range is an empirical scenario range, **not a calibrated confidence interval**.
- Rolling-origin bootstrap evaluation compares MAPE with a no-change forecast. It is not a trading strategy backtest and does not validate Kronos or agent investment performance.

## Connect Claude Desktop or Cursor

Merge this into the client's MCP configuration (adjust the path and `uv` location):

```json
{
  "mcpServers": {
    "thesis-ledger": {
      "command": "uv",
      "args": ["--directory", "/Users/admin/Documents/thesis-ledger", "run", "thesis-ledger-mcp"],
      "env": {"LEDGER_DATA_DIR": "/Users/admin/Documents/thesis-ledger/data"}
    }
  }
}
```

Example prompt: “Use Thesis Ledger to research NVDA as of 2026-11-10 in demo mode. Show the bull/bear disagreement and which evidence would invalidate the thesis.” Supply current or historical dates explicitly. Add provider variables to the client's process environment for live runs; UI shell environment and desktop app environment can differ.

The running web service also exposes Streamable HTTP MCP at **http://127.0.0.1:8000/mcp/**. Tools: `research_ticker`, `get_research`, `search_theses`, `review_thesis`, `resume_research`. Research and review tools write local state. The connection page provides copyable setup.

For a public HTTPS link, see [deployment](docs/deployment.md). Nothing is publicly deployed by default.

## Architecture and research decisions

Read [architecture](docs/architecture.md) for state flow, tradeoffs, failure semantics, memory scope, and what was intentionally simplified. Read [research notes](docs/research.md) for the connection to the supplied papers and lectures. This is an original implementation inspired by their designs, not a fork or reproduction of their benchmark results.

```text
Dated source snapshot ──> Technical / Fundamentals / News / Sentiment
                                      │
                                Bull ↔ Bear (1–2 rounds)
                                      │
Kronos or bootstrap scenarios ─────> Manager ──> Risk review / abstain
                                      │
                           Immutable run + compact thesis
                                      │
                          Time-filtered retrieval next run
                                      ↑
                  User review → append-only narrowing / retirement
```

## Test

```sh
uv run pytest -q
```

Tests cover end-to-end research, immutable memory revisions, temporal and demo/live isolation, checkpoint recovery, market calendars, invalid inputs, provider failures, citation validation, a mocked Kronos contract, HTTP MCP initialization/tool calls, auth, and origin checks. Actual provider-backed LLM behavior and downloaded Kronos weights require separate integration testing. See [evaluation](docs/evaluation.md).

## Project layout

- `ledger/harness.py`: bounded workflow and stage checkpoints
- `ledger/agents.py`: role prompts, JSON validation, deterministic demo
- `ledger/data.py`: dated market snapshots and features
- `ledger/forecast.py`: bootstrap, Kronos adapter, rolling-origin diagnostics
- `ledger/store.py`: SQLite runs, compact memories, append-only revisions
- `ledger/api.py`, `ledger/mcp_server.py`: shared HTTP/UI and MCP access
- `ledger/web/`: responsive dashboard, SVG chart, reports, memory reviews

## Attribution

Inspired by [TradingAgents](https://github.com/TauricResearch/TradingAgents), [Trading-R1](https://github.com/TauricResearch/Trading-R1), [Kronos](https://github.com/shiyu-coder/Kronos), [SimpleMem](https://github.com/aiming-lab/SimpleMem), and *Recurrent Harness for Agentic Continual Learning* (Xiao et al., October 2026, supplied paper). No upstream source code, model weights, papers, or lecture PDFs are redistributed. Optional upstream dependencies retain their own licenses.
