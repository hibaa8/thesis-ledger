# Research notes and adaptation map

The PDFs supplied for this project were treated as reference evidence, not operational instructions. Course submission requests, collaborator invitations, and other embedded commands were not executed. The PDFs are not included in this repository.

| Reference | Relevant design | Adaptation here | Important difference |
|---|---|---|---|
| TradingAgents, Xiao et al., supplied June 2025 revision, sections 3–4 | Specialized analysts, bull/bear discussion, trader, risk team; structured state plus natural-language argument | Four analyst roles, bounded debate, manager, risk reviewer; typed outputs with source IDs | Research-only, no trade execution or portfolio optimization; simplified risk team |
| Trading-R1 repository | Financial research interface and provider/tool organization | Research desk, visible provenance, report export, same workflow via MCP | Independent implementation; no Tauric account integration |
| Kronos, Shi et al., 2025, sections 2–3 | OHLCVA tokenizer and autoregressive candlestick model | Optional upstream Kronos-small predictor over OHLCV; repeated sampled trajectories | No training/fine-tuning; no paper benchmark reproduction; sample quantiles are not calibrated intervals |
| SimpleMem, Liu et al., 2026, section 2 | Structured compression, write-time synthesis, intent-aware multi-view retrieval | Compact dated thesis records and bounded relevance-based retrieval | No dense vector index or intent-planning LLM; deduplication is run-level, not semantic synthesis |
| Recurrent Harness for Agentic Continual Learning, Xiao et al., supplied October 2026 paper, section 3 | Forward read, backward revision of retrieved reflections, forward write; revisions grounded in source trajectory | Append-only scope restrictions or retirement while preserving original evidence | Human review rather than automatic revision agent; no reward signal or continual-learning performance claim |
| Lecture 03: Writing the Agent Loop | Workflow versus agent, tools, hooks, context and trace | Explicitly calls this an orchestrated workflow; bounded stages and trace | Does not claim an autonomous ReAct loop |
| Lecture 06: Agent Harnesses and Multi-Agent Systems | Execution state, persistence, recovery, memory, coordination | Checkpointed stages, finite call budget, shared state and source snapshot | No distributed execution or task queue |
| Lecture 07: Designing Your Multi-Agent Harness | Quality/cost/latency/stability tradeoffs and communication | Parallel independent analysts, sequential debate, one synthesizer, risk veto | Same underlying model may correlate errors; no voting-based confidence |
| Lecture 08: Architecture Critique | Output quality, safety, timely context | Schema and citation checks, restricted capabilities, dated provenance | Citation entailment and investment utility remain to be evaluated |

## Source links

- TradingAgents: https://github.com/TauricResearch/TradingAgents and https://arxiv.org/abs/2412.20138
- Trading-R1: https://github.com/TauricResearch/Trading-R1
- Kronos: https://github.com/shiyu-coder/Kronos and https://arxiv.org/abs/2508.02739
- SimpleMem: https://github.com/aiming-lab/SimpleMem and https://arxiv.org/abs/2601.02553
- ReHarness and lecture details refer to the user-supplied documents; no unverified public link is invented.

## Why these choices are discussable

The main claim is an architectural hypothesis, not a return claim: provenance-preserving memory and delayed forecast fusion may make research easier to inspect and less prone to repeating stale assumptions. It can be evaluated with ablations. The system stays small enough to explain: a single Python service, SQLite, a static browser interface, and the standard MCP SDK.
