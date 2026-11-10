# Real Kronos inference

The baseline runs without PyTorch. Selecting Kronos without installing it produces an explicit configuration error.

From the project directory:

```sh
mkdir -p vendor
git clone https://github.com/shiyu-coder/Kronos.git vendor/Kronos
uv pip install torch einops huggingface-hub tqdm safetensors
export KRONOS_PATH="$PWD/vendor/Kronos"
export KRONOS_DEVICE=cpu
uv run --no-sync thesis-ledger
```

If using a virtual environment with pip, substitute `.venv/bin/pip install torch einops huggingface-hub tqdm safetensors`. Record the upstream commit with `git -C vendor/Kronos rev-parse HEAD` for reproducible experiments. The upstream checkout is ignored by Git and not redistributed.

Open **Forecast**, select **Kronos-small** as the model, and click **Run forecast**. The default **Historical returns** model resamples recent daily returns and runs without model weights. The same engine is available in the Research desk. First use downloads `NeoQuasar/Kronos-Tokenizer-base` and `NeoQuasar/Kronos-small` from Hugging Face. Network access and several hundred MB of disk/memory may be needed. Set `KRONOS_DEVICE=cuda:0` for a compatible GPU. CPU latency may exceed the orchestration deadline for long horizons.

The adapter follows upstream `KronosPredictor.predict`: up to 512 historical OHLCV bars, known future NYSE session timestamps, temperature 1.0, top-p 0.9, one sample per call. Twenty independent calls yield a sample distribution. The median and 10th/90th percentiles summarize that distribution; they are not calibrated probabilities. Amount is omitted rather than falsely supplied as measured turnover; upstream fills optional missing columns.

The adapter contract is unit-tested with a predictor double. A successful mocked test does not establish real model quality. Evaluate downloaded weights on your own point-in-time data, compare against no-change/bootstrapped paths, and record model revision, seed, sample count, forecast horizon, and corporate-action adjustments.

Inference runs in an isolated child process with a 180-second hard timeout. Model stdout cannot corrupt MCP stdio messages. Each run cold-loads the model; a persistent GPU worker is a future optimization.
