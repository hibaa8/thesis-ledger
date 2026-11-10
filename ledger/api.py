import asyncio
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .harness import Harness
from .models import ResearchRequest, ReviewRequest
from .store import Store
from .mcp_server import create_mcp

WEB = Path(__file__).resolve().parent / "web"


def create_app(directory=None):
    store = Store(directory)
    harness = Harness(store)
    mcp = create_mcp(store, harness)

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    mcp_app = mcp.streamable_http_app()
    app = FastAPI(title="Thesis Ledger", lifespan=lifespan)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=os.getenv(
            "LEDGER_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"
        ).split(","),
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

    @app.get("/api/config")
    def config():
        return dict(
            live_ready=bool(
                os.getenv("LLM_API_KEY")
                and os.getenv("LLM_MODEL")
                and os.getenv("ALPHAVANTAGE_API_KEY")
            ),
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

    app.mount("/mcp", mcp_app)
    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    return app
