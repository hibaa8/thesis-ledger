import asyncio
import time
import uuid
from .agents import analyze
from .data import snapshot, metrics, validate_bars
from .forecast import forecast_bounded, walk_forward
from .models import ResearchRequest
from .store import open_store, now


class Harness:
    def __init__(self, store=None):
        self.store = store or open_store()
        self.lock = asyncio.Lock()

    async def run(self, request=None, resume_id=None):
        async with self.lock:
            return await self._run(request, resume_id)

    async def _run(self, request, resume_id):
        start = time.monotonic()
        if resume_id:
            state = self.store.get(resume_id)
            if state["status"] == "complete":
                return state
            req = ResearchRequest.model_validate(state["request"])
        else:
            req = request
            state = dict(
                id=uuid.uuid4().hex,
                created=now(),
                status="running",
                request=req.model_dump(mode="json"),
                reports={},
                trace=[],
                calls=0,
            )
        state["status"] = "running"
        state.pop("error", None)

        def checkpoint(stage, detail):
            state["trace"].append(dict(stage=stage, detail=detail, at=now()))
            self.store.save(state)

        async def agent(role, context, key=None):
            key = key or role
            if key in state["reports"]:
                return state["reports"][key]
            if state["calls"] >= 16:
                raise ValueError(
                    "Total model-call budget exhausted (16 attempts, including resumes)"
                )
            state["calls"] += 1
            self.store.save(state)
            report = await analyze(role, context, req.mode)
            state["reports"][key] = report
            checkpoint(role, "Validated report and evidence references")
            return report

        try:
            async with asyncio.timeout(240):
                if "snapshot" not in state:
                    state["snapshot"] = await snapshot(req)
                    state["snapshot"]["bars"] = validate_bars(
                        state["snapshot"]["bars"], req.as_of
                    )
                    state["metrics"] = metrics(state["snapshot"]["bars"])
                    state["memories"] = (
                        self.store.memories(
                            req.ticker, req.mode, str(req.as_of), req.question, 4
                        )
                        if req.use_memory
                        else []
                    )
                    checkpoint(
                        "context",
                        "Saved immutable source snapshot and date-filtered memory",
                    )
                if "forecast" not in state:
                    state["forecast"] = await asyncio.to_thread(
                        forecast_bounded,
                        state["snapshot"]["bars"],
                        req.horizon,
                        req.forecast,
                    )
                    state["evaluation"] = walk_forward(
                        state["snapshot"]["bars"], req.horizon
                    )
                    checkpoint(
                        "forecast",
                        "Saved scenario paths; evaluated bootstrap against no-change baseline",
                    )
                base = dict(
                    ticker=req.ticker,
                    as_of=str(req.as_of),
                    question=req.question,
                    metrics=state["metrics"],
                    evidence=state["snapshot"]["evidence"],
                    memories=state["memories"],
                    warnings=state["snapshot"]["warnings"],
                )
                # Analysts do not see the forecast: reduce anchoring and correlated narratives.
                async with asyncio.TaskGroup() as group:
                    for role in ["technical", "fundamentals", "news", "sentiment"]:
                        group.create_task(agent(role, base))
                context = {**base, "analysts": dict(state["reports"])}
                debate = []
                for round_ in range(req.rounds):
                    for role in ["bull", "bear"]:
                        debate.append(
                            await agent(
                                role,
                                {**context, "debate": debate},
                                f"{role}-{round_ + 1}",
                            )
                        )
                proposal = await agent(
                    "manager",
                    {**context, "debate": debate, "forecast": state["forecast"]},
                )
                risk = await agent(
                    "risk",
                    {
                        **context,
                        "debate": debate,
                        "proposal": proposal,
                        "forecast": state["forecast"],
                    },
                )
                decision = dict(proposal)
                if (
                    risk["stance"] == "abstain"
                    or req.mode == "demo"
                    or any("STALE" in w for w in state["snapshot"]["warnings"])
                ):
                    decision["stance"] = "abstain"
                state["decision"] = decision
                state["disagreement"] = proposal["stance"] not in [
                    "neutral",
                    "abstain",
                ] and (
                    (state["forecast"]["expected_return"] > 0)
                    != (proposal["stance"] == "bullish")
                )
                state["status"] = "complete"
                state["elapsed_seconds"] = round(time.monotonic() - start, 2)
                self.store.remember(state)
                checkpoint(
                    "complete", "Research saved; compact thesis written to memory"
                )
        except Exception as exc:
            state["status"] = "failed"
            # Avoid persisting provider request URLs containing API credentials.
            state["error"] = (
                str(exc)
                if isinstance(exc, ValueError)
                else f"{type(exc).__name__}: stage failed. Check provider availability and configuration; completed checkpoints are preserved."
            )
            checkpoint("failed", state["error"])
        return state
