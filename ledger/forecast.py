import os
import sys
from functools import lru_cache
from pathlib import Path
import numpy as np
import pandas as pd
from .data import future_sessions


@lru_cache(maxsize=1)
def kronos_predictor():
    root = os.getenv("KRONOS_PATH")
    if not root or not (Path(root) / "model" / "__init__.py").exists():
        raise ValueError(
            "Kronos is not installed. Set KRONOS_PATH to the upstream checkout and install its requirements; no silent baseline substitution occurs."
        )
    sys.path.insert(0, str(Path(root).resolve()))
    from model import Kronos, KronosTokenizer, KronosPredictor

    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    return KronosPredictor(
        model, tokenizer, device=os.getenv("KRONOS_DEVICE", "cpu"), max_context=512
    )


def forecast(bars, horizon, engine="bootstrap"):
    days = future_sessions(bars[-1]["date"], horizon)
    closes = np.array([b["close"] for b in bars])
    if engine == "kronos":
        predictor = kronos_predictor()
        df = pd.DataFrame(bars).tail(512)
        # Independent sampled trajectories, not quantiles of an averaged prediction.
        paths = []
        for _ in range(20):
            pred = predictor.predict(
                df=df[["open", "high", "low", "close", "volume"]],
                x_timestamp=pd.to_datetime(df["date"]),
                y_timestamp=pd.Series(pd.to_datetime(days)),
                pred_len=horizon,
                T=1.0,
                top_p=0.9,
                sample_count=1,
            )
            paths.append(pred["close"].to_numpy())
        paths = np.asarray(paths)
        label = "Kronos-small · 20 sampled paths"
    else:
        rng = np.random.default_rng(42)
        returns = np.diff(np.log(closes))[-60:]
        paths = closes[-1] * np.exp(
            np.cumsum(rng.choice(returns, size=(500, horizon)), axis=1)
        )
        label = "Historical-return bootstrap · 500 paths"
    if paths.shape[1] != horizon or not np.isfinite(paths).all() or (paths <= 0).any():
        raise ValueError("Forecast returned invalid prices")
    q = np.quantile(paths, [0.1, 0.5, 0.9], axis=0)
    points = [
        dict(date=d, low=float(q[0, i]), median=float(q[1, i]), high=float(q[2, i]))
        for i, d in enumerate(days)
    ]
    return dict(
        engine=engine,
        label=label,
        points=points,
        expected_return=float((q[1, -1] / closes[-1] - 1) * 100),
        disclaimer="10–90% sampled scenario range, not a calibrated confidence interval. No proven trading edge.",
    )


def walk_forward(bars, horizon=5):
    errors = []
    naive = []
    covered = []
    for split in range(40, len(bars) - horizon + 1, 5):
        f = forecast(bars[:split], horizon)["points"][-1]
        actual = bars[split + horizon - 1]["close"]
        last = bars[split - 1]["close"]
        errors.append(abs(f["median"] - actual) / actual * 100)
        naive.append(abs(last - actual) / actual * 100)
        covered.append(f["low"] <= actual <= f["high"])
    return dict(
        windows=len(errors),
        bootstrap_mape=float(np.mean(errors)),
        naive_mape=float(np.mean(naive)),
        scenario_coverage=float(np.mean(covered)) * 100,
        note="Rolling origin, price-only diagnostic. Not a strategy backtest; no returns, costs, or alpha claim.",
    )


def forecast_bounded(bars, horizon, engine="bootstrap"):
    """Kronos runs in a child process so logs cannot corrupt stdio MCP."""
    if engine != "kronos":
        return forecast(bars, horizon, engine)
    import json
    import subprocess

    root = os.getenv("KRONOS_PATH")
    if not root or not (Path(root) / "model" / "__init__.py").exists():
        raise ValueError(
            "Kronos is not installed. Configure KRONOS_PATH and its dependencies."
        )
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ledger.kronos_worker"],
            input=json.dumps({"bars": bars, "horizon": horizon}),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(
            "Kronos exceeded its 180-second inference budget; the model process was stopped. Try a shorter horizon or GPU."
        ) from exc
    if result.returncode:
        raise ValueError(
            "Kronos inference failed. Check upstream dependencies, model download access, and KRONOS_DEVICE. No baseline was substituted."
        )
    return json.loads(result.stdout)
