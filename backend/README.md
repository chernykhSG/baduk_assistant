# baduk-backend

Python backend service for Baduk Assistant (Phase 1: sidecar skeleton +
KataGo Engine Manager). Exposes a token-authenticated FastAPI `/health`
endpoint and wraps the KataGo Analysis Engine subprocess for position
analysis. See `docs/ARCHITECTURE.md` at the repo root for the full design.

## Running the test suite

This project uses `uv` as its package manager (per `docs/ARCHITECTURE.md`):

```bash
uv run pytest -v
```

If `uv` isn't on your `PATH`, run the equivalent directly against the
project's `.venv` (both use the same `pyproject.toml` config and virtualenv):

```powershell
.venv\Scripts\python.exe -m pytest -v
# or activate first: .venv\Scripts\activate ; pytest -v
```

## Running the real KataGo integration test

The integration test (`-m integration`) is skipped by default. To run it
against a real local KataGo binary/model, set two environment variables
first (see `tests/local_config.json.example` for details), then run with
the `integration` marker:

```powershell
$env:BADUK_KATAGO_BINARY = "C:/path/to/katago.exe"
$env:BADUK_KATAGO_MODEL = "C:/path/to/model.bin.gz"
uv run pytest -v -m integration
```

## Running the real LLM provider integration tests

`tests/test_api_explain_integration.py` (also gated by `-m integration`) calls
the real Claude and/or Gemini APIs, or runs real local inference via
`llama-cpp-python`. Each test self-skips if its provider isn't configured:

```powershell
$env:BADUK_CLAUDE_API_KEY = "sk-ant-..."
$env:BADUK_GEMINI_API_KEY = "AIzaSy..."
$env:BADUK_LLAMA_MODEL_PATH = "C:/models/Qwen3-8B-Q4_K_M.gguf"
uv run pytest -v -m integration
```

## Setting up the local llama-cpp-python provider (optional)

This provider runs a GGUF-format model locally via `llama-cpp-python`,
avoiding cloud API costs and rate limits, at the cost of needing a
compatible GPU and a heavier install than the cloud providers.

**Recommended model:** `Qwen3-8B`, `Q4_K_M` quantization (~5 GB) —
strong Russian-language quality, fits comfortably in 8 GB VRAM. Download
`Qwen3-8B-Q4_K_M.gguf` from `unsloth/Qwen3-8B-GGUF` on Hugging Face and
place it anywhere on disk — the exact location is up to you, set it via
`BADUK_LLAMA_MODEL_PATH` (see below).

**VRAM note:** the model loads into VRAM once at backend startup and stays
there for the whole session — on the same GPU that also runs KataGo. If
you're running both on a single ≤8GB card, budget VRAM carefully (lower
`BADUK_LLAMA_N_GPU_LAYERS` from the `-1` default to offload fewer layers if
you hit out-of-memory errors — note that the OOM may surface confusingly as
a *KataGo* startup failure, since KataGo initializes second). Expect backend
startup to take tens of seconds longer than with the cloud providers while
the model loads.

**Installing `llama-cpp-python` with CUDA support (NVIDIA GPUs):** the
primary route is a prebuilt CUDA wheel:

```powershell
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

Replace `cu124` with whichever CUDA version matches your installed CUDA
Toolkit (check with `nvidia-smi`) — `cu118`, `cu121`, `cu122`, `cu123`,
`cu124`, `cu125`, `cu130`, and `cu132` are available.

If no prebuilt wheel matches your platform/Python version, `pip` falls back
to building from source. On Windows this can fail with a long-path error
(`OSError: [Errno 2] No such file or directory` under a path containing
`vendor/llama.cpp/...`) — if you hit this, enable Windows Long Path support
first (registry/group-policy steps are printed in the error itself, or see
`https://pip.pypa.io/warnings/enable-long-paths`), then retry. A source
build also requires the NVIDIA CUDA Toolkit and Visual Studio Build Tools
("Desktop development with C++" workload), with `CMAKE_ARGS="-DGGML_CUDA=on"`
and `FORCE_CMAKE=1` set before running `pip install llama-cpp-python`.

**Installing `llama-cpp-python` with Vulkan support (no CUDA Toolkit
needed):** if the CUDA wheel fails to load — the `Llama(...)` constructor
raises a DLL-load error, which typically means the machine has the NVIDIA
driver but not the separate CUDA Toolkit — a prebuilt Vulkan wheel is a
working alternative:

```powershell
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/vulkan
```

Vulkan only needs the GPU driver's own Vulkan runtime (`vulkan-1.dll` on
Windows, installed automatically with any modern GPU driver), not the CUDA
Toolkit. Verified in this project (2026-08-11, RTX 5060 Ti, no CUDA
Toolkit installed): with the default `n_gpu_layers=-1`, the load log showed
`load_tensors: offloaded 37/37 layers to GPU` on device `Vulkan1`, and
`nvidia-smi` confirmed real usage during inference (VRAM rising to ~5.4 GB,
GPU utilization up to 95%) at ~30 tokens/sec — versus ~2 tokens/sec (123s
for a comparable response) on the CPU-only wheel.

## Running the backend service

`baduk-backend` (the `run()` entry point in `main.py`) requires
`BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` (see above) plus configuration
for whichever LLM provider is active — it fails fast at startup if either
is missing, since `/api/explain` calls that provider.

`BADUK_LLM_PROVIDER` selects the active provider: `"claude"`, `"gemini"`,
or `"llama"` (defaults to `"llama"` if unset). Depending on the value:
- `claude` — requires `BADUK_CLAUDE_API_KEY`. `BADUK_CLAUDE_MODEL` is
  optional and overrides the default model.
- `gemini` — requires `BADUK_GEMINI_API_KEY`. `BADUK_GEMINI_MODEL` is
  optional and overrides the default model.
- `llama` — requires `BADUK_LLAMA_MODEL_PATH` (absolute path to a `.gguf`
  model file — see "Setting up the local llama-cpp-python provider" above).
  `BADUK_LLAMA_N_GPU_LAYERS` is optional (defaults to `-1`, offloading all
  layers to GPU) — lower it if the model doesn't fit in your VRAM.

Any other `BADUK_LLM_PROVIDER` value fails fast at startup with an error
naming the invalid value.

## Running the RAG knowledge-base ingestion pipeline (optional)

This builds the Chroma vector store (`backend/rag_store/`) that
`baduk_backend.rag.retrieval.retrieve_knowledge()` queries. It requires the
`rag` optional-dependency group (`pyyaml`, `sentence-transformers`,
`chromadb`):

```powershell
.venv\Scripts\python.exe -m pip install -e ".[rag]"
```

Set `BADUK_KNOWLEDGE_BASE_PATH` to point at the root of a local checkout of
the `Baduk-knowledge-base` repo (a separate repo holding the markdown cards
under `knowledge-base/wiki/{principles,mistakes,exercises}/*.md`):

```powershell
$env:BADUK_KNOWLEDGE_BASE_PATH = "C:/path/to/your/Baduk-knowledge-base/checkout"
```

Then run ingestion from within `backend/`:

```powershell
.venv\Scripts\python.exe -m baduk_backend.rag.ingest
```

This is a manual, on-demand script — the backend service does not run it
automatically — and every run does a full rebuild of `backend/rag_store/`
(it is not incremental).

## API

- `POST /api/analyze` — анализ одной позиции. Тело запроса и ответ — см.
  `backend/src/baduk_backend/api/schemas.py` (`AnalyzeRequest`/`AnalyzeResponse`).
  Требует заголовок `X-Auth-Token`. `503`, если процесс KataGo упал.
- `WS /api/analyze/stream?token=...` — потоковый анализ партии, прогресс по
  ходам (`StreamAnalyzeRequest` на входе, `progress`/`done`/`error` сообщения
  на выходе). Неверный/отсутствующий токен → закрытие соединения кодом `1008`.
- `POST /api/explain` — LLM-объяснение находки (`weak_group`) через активный
  провайдер (`BADUK_LLM_PROVIDER` — `claude`, `gemini` или `llama`). Тело
  запроса и ответ — см. `ExplainRequest`/`ExplainResponse` в том же файле.
  Требует заголовок `X-Auth-Token`. `503`, если вызов провайдера завершился
  ошибкой.
