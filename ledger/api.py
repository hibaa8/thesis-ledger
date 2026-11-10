import asyncio
import hmac
import os

import httpx
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .harness import Harness
from .models import ResearchRequest, ReviewRequest
from .store import Store
from .mcp_server import create_mcp

WEB = Path(__file__).resolve().parent / "web"


from pydantic import BaseModel, Field
from .chat import Chat
from .data import snapshot
from .forecast import forecast_bounded
from .market import MarketBrief
from .quotes import Quotes, quote_interval
from .config import load_config
from .alpaca import company_news, intraday


class ChatRequest(BaseModel):
    session: str = Field(pattern=r"^[a-f0-9]{32}$")
    message: str = Field(min_length=1, max_length=4000)
    ticker: str = Field(default="NVDA", pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$")


def create_app(directory=None):
    load_config()
    store = Store(directory)
    harness = Harness(store)
    quotes = Quotes()
    market = MarketBrief(quotes)
    chat = Chat(store, harness, quotes, market)
    forecast_lock = asyncio.Lock()
    mcp = create_mcp(store, harness, quotes, market)

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    mcp_app = mcp.streamable_http_app()
    app = FastAPI(title="Thesis Ledger", lifespan=lifespan)
    allowed_hosts = os.getenv(
        "LEDGER_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"
    ).split(",")
    if render_host := os.getenv("RENDER_EXTERNAL_HOSTNAME"):
        allowed_hosts.append(render_host)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts,
    )

    @app.middleware("http")
    async def access(request: Request, call_next):
        token = os.getenv("LEDGER_API_TOKEN", "")
        if request.url.path.startswith(("/api/", "/mcp")):
            if token and not hmac.compare_digest(
                request.headers.get("authorization", ""), f"Bearer {token}"
            ):
                return JSONResponse(
                    {"detail": "Valid bearer token required"}, status_code=401
                )
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse(
                    {"detail": "Cross-origin access denied"}, status_code=403
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": "Not found"}, status_code=404)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    def alpaca_ready():
        return bool(os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY"))

    @app.get("/api/config")
    def config():
        return dict(
            alpaca_ready=alpaca_ready(),
            live_ready=bool(
                os.getenv("LLM_API_KEY")
                and os.getenv("LLM_MODEL")
                and os.getenv("ALPHAVANTAGE_API_KEY")
            ),
            chat_ready=bool(os.getenv("LLM_API_KEY")),
            quote_refresh_seconds=quote_interval(),
            kronos_configured=bool(os.getenv("KRONOS_PATH")),
            model=os.getenv("LLM_MODEL") or "Deterministic demo",
            mcp_path="/mcp/",
        )

    @app.post("/api/research")
    async def research(req: ResearchRequest):
        if harness.lock.locked():
            raise HTTPException(
                409, "Research already running. Wait for the current run to finish."
            )
        return await harness.run(req)

    @app.get("/api/market")
    async def market_overview():
        return await market.get()

    @app.get("/api/dashboard")
    def dashboard(ticker: str = "NVDA"):
        return store.latest_live_report(ResearchRequest(ticker=ticker.upper()).ticker)

    @app.post("/api/dashboard")
    async def refresh_dashboard(ticker: str = "NVDA"):
        req = ResearchRequest(ticker=ticker.upper(), mode="live")
        saved = store.latest_live_report(req.ticker)
        if (
            saved
            and saved["request"]["as_of"] == req.as_of.isoformat()
            and (
                not alpaca_ready()
                or saved.get("snapshot", {}).get("company_news_checked")
            )
        ):
            return saved
        if harness.lock.locked():
            raise HTTPException(409, "Research is already running.")
        if not config()["live_ready"]:
            raise HTTPException(
                503, "Configure OpenAI and Alpha Vantage to load live research."
            )
        return await harness.run(req)

    @app.get("/api/runs")
    def runs():
        return [
            dict(
                id=r["id"],
                created=r["created"],
                status=r["status"],
                request=r["request"],
            )
            for r in store.runs()
        ]

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        return store.get(run_id)

    @app.post("/api/runs/{run_id}/resume")
    async def resume(run_id: str):
        if harness.lock.locked():
            raise HTTPException(409, "Research already running")
        return await harness.run(resume_id=run_id)

    @app.get("/api/memories")
    def memories():
        return store.memories()

    @app.post("/api/memories/review")
    def review(req: ReviewRequest):
        return store.revise(req.memory_id, req.feedback, req.scope)

    @app.post("/api/forecast")
    async def forecast(req: ResearchRequest):
        cache_model = "kronos-small" if req.forecast == "kronos" else "bootstrap"
        key = f"{cache_model}:{req.mode}:{req.ticker}:{req.horizon}:{req.as_of}"
        cached = store.cached_forecast(key)
        if cached is not None:
            return cached
        if req.forecast == "kronos" and not os.getenv("KRONOS_PATH"):
            raise HTTPException(
                503, "Configure KRONOS_PATH and install Kronos to run this forecast."
            )
        if forecast_lock.locked():
            raise HTTPException(409, "A forecast is already running.")
        async with forecast_lock:
            try:
                market = await snapshot(req, include_research_sources=False)
                result = await asyncio.to_thread(
                    forecast_bounded, market["bars"], req.horizon, req.forecast
                )
            except (ValueError, httpx.HTTPError) as exc:
                detail = (
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "Market data request failed."
                )
                raise HTTPException(503, detail) from None
            payload = {
                "forecast": result,
                "snapshot": market,
                "request": req.model_dump(mode="json"),
            }
            store.save_forecast(key, payload)
        return payload

    @app.get("/api/intraday/{ticker}")
    async def chart_data(ticker: str):
        try:
            return await intraday(ResearchRequest(ticker=ticker.upper()).ticker)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        except httpx.HTTPError:
            raise HTTPException(
                503,
                "Alpaca could not return intraday bars. Check the feed entitlement.",
            ) from None

    @app.get("/api/news/{ticker}")
    async def ticker_news(ticker: str):
        try:
            return await company_news(ResearchRequest(ticker=ticker.upper()).ticker)
        except (ValueError, httpx.HTTPError):
            raise HTTPException(
                503, "Company headlines are currently unavailable from Alpaca."
            ) from None

    @app.get("/api/quote/{ticker}")
    async def quote(ticker: str):
        try:
            return await quotes.get(ticker)
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from None

    @app.get("/api/chat/{session}")
    def history(session: str):
        return store.chat_history(session)

    @app.post("/api/chat")
    async def chat_turn(req: ChatRequest):
        if not os.getenv("LLM_API_KEY"):
            raise HTTPException(503, "Chat requires a configured OpenAI API key.")
        if not req.message.strip():
            raise HTTPException(422, "Enter a message.")
        return StreamingResponse(
            chat.stream(req.session, req.message.strip(), req.ticker),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    app.mount("/mcp", mcp_app)
    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    return app
