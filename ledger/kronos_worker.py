"""Isolate optional model stdout and enforce a killable inference deadline."""

import contextlib
import json
import sys
from .forecast import forecast


def main():
    payload = json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        result = forecast(payload["bars"], payload["horizon"], "kronos")
    json.dump(result, sys.stdout, allow_nan=False)


if __name__ == "__main__":
    main()
