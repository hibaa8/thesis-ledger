import argparse
import os
from mcp.server.transport_security import TransportSecuritySettings
from mcp.server.fastmcp import FastMCP
from .harness import Harness
from .models import ResearchRequest, ReviewRequest
from .store import Store
from .quotes import Quotes


def create_mcp(store=None, harness=None, quotes=None):
    store = store or Store()
    harness = harness or Harness(store)
    quotes = quotes or Quotes()
    hosts = os.getenv("LEDGER_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    security = TransportSecuritySettings(
        allowed_hosts=[v for h in hosts for v in [h, h + ":*"]],
        allowed_origins=[
            v
            for h in hosts
            for v in ["http://" + h + ":*", "https://" + h, "http://" + h]
        ],
    )
    mcp = FastMCP(
        "Thesis Ledger",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=security,
    )

    @mcp.tool()
    async def research_ticker(
        ticker: str,
        as_of: str,
        horizon: int = 5,
        mode: str = "demo",
        forecast_engine: str = "bootstrap",
        question: str = "What supports or challenges this thesis?",
    ) -> dict:
        """Run bounded multi-agent research. Demo is synthetic. Live requires configured market and LLM keys. Saves a run and a thesis memory; does not execute trades."""
        return await harness.run(
            ResearchRequest(
                ticker=ticker,
                as_of=as_of,
                horizon=horizon,
                mode=mode,
                forecast=forecast_engine,
                question=question,
            )
        )

    @mcp.tool()
    def get_research(run_id: str) -> dict:
        """Read a saved research run with evidence, agent reports, forecasts and trace."""
        return store.get(run_id)

    @mcp.tool()
    def search_theses(
        ticker: str, as_of: str, mode: str = "demo", query: str = ""
    ) -> list[dict]:
        """Retrieve up to four compact memories available by a date. Demo and live memories are isolated."""
        req = ResearchRequest(ticker=ticker, as_of=as_of, mode=mode)
        return store.memories(req.ticker, req.mode, str(req.as_of), query, 4)

    @mcp.tool()
    def review_thesis(
        memory_id: str, feedback: str, scope: str = "source_snapshot_only"
    ) -> dict:
        """Record user feedback and narrow or retire a memory. Preserves original evidence and records revision time. Feedback is not a verified market outcome."""
        req = ReviewRequest(memory_id=memory_id, feedback=feedback, scope=scope)
        return store.revise(req.memory_id, req.feedback, req.scope)

    @mcp.tool()
    async def resume_research(run_id: str) -> dict:
        """Resume a failed run from persisted stages within its original total call budget."""
        return await harness.run(resume_id=run_id)

    @mcp.tool()
    async def latest_price(ticker: str) -> dict:
        """Get the latest available price with provider, observation time, and freshness."""
        return await quotes.get(ticker)

    return mcp


from .config import load_config


def main():
    load_config()
    parser = argparse.ArgumentParser()
    parser.parse_args()
    create_mcp().run(transport="stdio")


if __name__ == "__main__":
    main()
