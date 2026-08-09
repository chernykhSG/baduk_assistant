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
the real Claude and/or Gemini APIs. Each test self-skips if its provider's
API key isn't set:

```powershell
$env:BADUK_CLAUDE_API_KEY = "sk-ant-..."
$env:BADUK_GEMINI_API_KEY = "AIzaSy..."
uv run pytest -v -m integration
```

## Running the backend service

`baduk-backend` (the `run()` entry point in `main.py`) requires
`BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` (see above) plus an API key for
whichever LLM provider is active — it fails fast at startup if either is
missing, since `/api/explain` calls that provider's API.

`BADUK_LLM_PROVIDER` selects the active provider: `"claude"` or `"gemini"`
(defaults to `"gemini"` if unset). Depending on the value:
- `claude` — requires `BADUK_CLAUDE_API_KEY`. `BADUK_CLAUDE_MODEL` is
  optional and overrides the default model.
- `gemini` — requires `BADUK_GEMINI_API_KEY`. `BADUK_GEMINI_MODEL` is
  optional and overrides the default model.

Any other `BADUK_LLM_PROVIDER` value fails fast at startup with an error
naming the invalid value.

## API

- `POST /api/analyze` — анализ одной позиции. Тело запроса и ответ — см.
  `backend/src/baduk_backend/api/schemas.py` (`AnalyzeRequest`/`AnalyzeResponse`).
  Требует заголовок `X-Auth-Token`. `503`, если процесс KataGo упал.
- `WS /api/analyze/stream?token=...` — потоковый анализ партии, прогресс по
  ходам (`StreamAnalyzeRequest` на входе, `progress`/`done`/`error` сообщения
  на выходе). Неверный/отсутствующий токен → закрытие соединения кодом `1008`.
- `POST /api/explain` — LLM-объяснение находки (`weak_group`) через активный
  провайдер (`BADUK_LLM_PROVIDER` — `claude` или `gemini`). Тело запроса и
  ответ — см. `ExplainRequest`/`ExplainResponse` в том же файле. Требует
  заголовок `X-Auth-Token`. `503`, если вызов провайдера завершился ошибкой.
