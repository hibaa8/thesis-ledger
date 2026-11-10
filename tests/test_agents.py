import asyncio
import json
from datetime import date
import httpx
import pytest
from ledger.agents import analyze
from ledger.data import demo_snapshot, metrics
from ledger.forecast import forecast, kronos_predictor


def test_llm_citation_validation(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    import ledger.agents as module

    real_client = httpx.AsyncClient

    def mock(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "role": "technical",
                                    "stance": "bullish",
                                    "summary": "Claim",
                                    "evidence_ids": ["invented-source"],
                                    "invalidation": "Trend breaks",
                                    "risks": [],
                                }
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(mock), **kwargs),
    )
    with pytest.raises(ValueError, match="unknown evidence"):
        asyncio.run(analyze("technical", {"evidence": [{"id": "prices"}]}, "live"))


def test_kronos_adapter_contract(monkeypatch):
    import ledger.forecast as module
    import pandas as pd

    class Predictor:
        def predict(self, **kw):
            assert list(kw["df"].columns) == ["open", "high", "low", "close", "volume"]
            assert len(kw["y_timestamp"]) == kw["pred_len"]
            assert kw["sample_count"] == 1
            return pd.DataFrame({"close": [100.0] * kw["pred_len"]})

    monkeypatch.setattr(module, "kronos_predictor", lambda: Predictor())
    result = forecast(demo_snapshot("NVDA", date.today())["bars"], 5, "kronos")
    assert result["engine"] == "kronos"
    assert result["points"][0]["median"] == 100


def test_kronos_timeout_is_explicit(tmp_path, monkeypatch):
    import subprocess
    from ledger.forecast import forecast_bounded

    (tmp_path / "model").mkdir()
    (tmp_path / "model" / "__init__.py").touch()
    monkeypatch.setenv("KRONOS_PATH", str(tmp_path))

    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 180
        raise subprocess.TimeoutExpired(args[0], 180)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ValueError, match="process was stopped"):
        forecast_bounded([], 5, "kronos")
