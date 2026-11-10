import argparse
import os
import uvicorn


from .config import load_config


def main():
    load_config()
    parser = argparse.ArgumentParser(
        description="Thesis Ledger local research workspace"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if (
        args.host not in ["127.0.0.1", "localhost"]
        and len(os.getenv("LEDGER_API_TOKEN", "")) < 32
    ):
        parser.error(
            "Non-local hosting requires LEDGER_API_TOKEN with at least 32 characters"
        )
    uvicorn.run("ledger.api:create_app", factory=True, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
