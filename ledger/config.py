import logging
import os

from dotenv import load_dotenv


def load_config():
    """Load local credentials while giving deployed environment variables precedence."""
    # Alpha Vantage authenticates in the query string. Keep URLs out of INFO logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv(".env")
    for canonical, alias in (
        ("LLM_API_KEY", "OPENAI_KEY"),
        ("LLM_API_KEY", "OPENAI_API_KEY"),
        ("ALPHAVANTAGE_API_KEY", "ALPHA_VANTAGE"),
    ):
        if not os.getenv(canonical) and os.getenv(alias):
            os.environ[canonical] = os.environ[alias]
    if os.getenv("LLM_API_KEY") and not os.getenv("LLM_MODEL"):
        os.environ["LLM_MODEL"] = "gpt-4o-mini"
