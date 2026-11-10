# Evaluation plan

## Verified invariants

The automated suite checks fixture reproducibility, finite ordered scenario quantiles, date-filtered bars, OHLC consistency, holiday-aware horizons, compact-memory creation, immutable revisions, retirement, demo/live isolation, no backdating of knowledge, checkpoint reuse, idempotent completion, explicit missing-credential failures, strict request limits, unknown citation rejection, the Kronos adapter's call contract, HTTP endpoints, MCP handshake/list/read, authentication, and cross-origin denial.

## What the dashboard diagnostic measures

Starting with 40 observed bars, forecast the requested horizon with the bootstrap baseline, advance the origin by five sessions, and compare the endpoint to its realized close. Report average absolute percentage error, no-change MAPE, and observed frequency within the scenario range. All features for each prediction use only preceding bars.

This small, overlapping-window diagnostic is neither an investment backtest nor a test of agent quality. Synthetic data cannot establish real-world performance. Kronos is not scored by this diagnostic even when selected for the forward forecast; the UI labels that distinction.

## Research experiments worth doing next

1. **Grounding:** hand-label whether every cited source supports the associated claim; measure unsupported numeric assertions and material omissions.
2. **Memory:** compare no memory, append-only memory, and reviewed memory on chronological cases. Check both retrieval quality and whether stale claims recur.
3. **Forecast anchoring:** compare early versus late forecast exposure with identical snapshots and model budgets.
4. **Risk review:** evaluate abstention on missing, stale, contradictory, and manipulated sources.
5. **Forecasts:** compare Kronos, no-change, and bootstrap on held-out chronological data; record corporate actions, model training overlap, sample variance, horizon, calibration and accuracy.
6. **Operations:** latency, failure rate, resume success, token use and cost per run. Run malformed JSON and provider rate-limit fault injection.

Only after these should strategy return testing be considered. Define decision time, next executable price, transaction costs, slippage, benchmark, survivorship bias, embargoes, and out-of-sample selection before measuring returns. Do not infer profit from forecast MAPE or persuasive prose.
