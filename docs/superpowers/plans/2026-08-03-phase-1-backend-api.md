# HTTP/WS API-слой над EngineManager — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить HTTP `POST /api/analyze` и WebSocket `WS /api/analyze/stream` поверх уже смёрженного в `main` `EngineManager`, закрыв vertical-slice шаг 3 из дизайн-спека Фазы 1.

**Architecture:** Pydantic-модели зеркалируют протокол KataGo Analysis Engine напрямую (без трансформации в «находки»). Единственный `EngineManager` + `asyncio.Lock` живут в `app.state`, создаются в `main.run()` при старте sidecar-процесса (не через FastAPI-lifespan — тесты подключают свой fake `EngineManager` напрямую в `app.state`, минуя реальный запуск KataGo). `analyze()` вызывается под локом через `asyncio.to_thread()`.

**Tech Stack:** FastAPI 0.141.1, Pydantic 2.13.4 (v2 API — `model_dump()`, `model_validate()`, `Field(min_length=..., max_length=...)`), pytest 9.1.1, httpx 0.28.1 / `fastapi.testclient.TestClient` (включая `websocket_connect`).

## Global Constraints

- WS-гранулярность прогресса: одно сообщение на завершённый ход (`{"type": "progress", "turnNumber": N, "total": M, "result": {...}}`), не live внутри-поисковый прогресс.
- Конкурентность: один `asyncio.Lock` вокруг единственного `EngineManager` в `app.state`; блокирующий `EngineManager.analyze()` вызывается через `asyncio.to_thread()`.
- Схемы: пока только Pydantic-модели в backend (`backend/src/baduk_backend/api/schemas.py`), без `shared/schemas/`.
- `EngineManager.analyze()` в текущей реализации читает ровно одну строку ответа на один запрос (см. комментарий в `engine_manager.py:112-115`) — значит каждый вызов `analyze()` должен нести ровно один номер хода в `analyzeTurns`. `POST /api/analyze` валидирует это через Pydantic (`analyzeTurns` — список длины ровно 1); WS-эндпоинт сам итерирует `turnNumbers` и вызывает `analyze()` по одному ходу за раз.
- Обработка ошибок: `KataGoCrashError` → HTTP `503` с `{"detail": "..."}"`; на WS — `{"type": "error", "detail": "..."}"`, затем штатное закрытие. Некорректный/невалидный JSON во входящем WS-сообщении → `{"type": "error", "detail": "invalid request"}"`, затем закрытие.
- WS-аутентификация: токен как query-параметр `?token=...` (тот же `AUTH_TOKEN`, что и HTTP). Сервер сперва принимает соединение (`accept()`), затем при неверном/отсутствующем токене немедленно закрывает его кодом `1008` — так клиент фактически получает код закрытия (rejecting до `accept()` не гарантирует это в браузерных WS-клиентах).
- HTTP-аутентификация: тот же механизм, что уже использует `/health` — заголовок `X-Auth-Token`, сверяется через `secrets.compare_digest`, `401` при отсутствии/несовпадении.
- Единственный `EngineManager`/`asyncio.Lock` создаются в `main.run()` (реальный sidecar-запуск), не в FastAPI lifespan — тесты не должны требовать реального KataGo или env vars, поэтому вайринг `app.state` для тестов происходит напрямую в фикстурах, а не через жизненный цикл приложения.
- Не расширять область: без `shared/schemas/`, без live-прогресса внутри поиска, без пула процессов под несколько моделей — см. дизайн-спек, раздел «Вне рамок этого плана».

---

## File Structure

```
backend/src/baduk_backend/
├── auth.py                    # NEW — AUTH_TOKEN, verify_token(), require_valid_token() (HTTP deps)
├── main.py                    # MODIFY — импортирует auth.AUTH_TOKEN, подключает api.analysis router,
│                               #          _build_engine_manager(), реальный wiring в run()
├── engine_manager.py           # MODIFY — analyze() дренирует стейл-очередь перед отправкой запроса
└── api/
    ├── __init__.py             # NEW — пустой, делает `api` пакетом
    ├── schemas.py               # NEW — Pydantic-модели запроса/ответа (HTTP + WS)
    └── analysis.py              # NEW — APIRouter: POST /api/analyze + WS /api/analyze/stream

backend/tests/
├── conftest.py                 # MODIFY — добавляет fake_engine_client / fake_engine_client_crash фикстуры
├── test_schemas.py              # NEW — валидация Pydantic-моделей
├── test_engine_manager.py       # MODIFY — регрессионный тест на drain стейл-очереди
├── test_api_analyze.py          # NEW — route-level тесты POST /api/analyze (fake KataGo)
├── test_api_analyze_stream.py   # NEW — route-level тесты WS /api/analyze/stream (fake KataGo)
└── test_api_analyze_integration.py  # NEW — реальный KataGo через HTTP-слой (@pytest.mark.integration)
```

---

### Task 1: Pydantic-схемы запроса/ответа

**Files:**
- Create: `backend/src/baduk_backend/api/__init__.py`
- Create: `backend/src/baduk_backend/api/schemas.py`
- Test: `backend/tests/test_schemas.py`

**Interfaces:**
- Produces: `AnalyzeRequest` (поля: `moves: list[list[str]]`, `rules: str`, `komi: float`, `boardXSize: int`, `boardYSize: int`, `analyzeTurns: list[int]` длиной ровно 1, `maxVisits: int`, `includeOwnership: bool = False`), `MoveInfo`, `RootInfo`, `AnalyzeResponse` (`id: str`, `turnNumber: int | None`, `moveInfos: list[MoveInfo]`, `rootInfo: RootInfo`, `ownership: list[float] | None`), `StreamAnalyzeRequest` (как `AnalyzeRequest`, но вместо `analyzeTurns` — `turnNumbers: list[int]` длиной минимум 1), `ProgressMessage`, `DoneMessage`, `ErrorMessage`. Все классы экспортируются из `baduk_backend.api.schemas`, используются в Task 3 и Task 4.

- [ ] **Step 1: Создать пустой `api/__init__.py`**

```python
```

(Файл существует и пуст — делает `backend/src/baduk_backend/api/` пакетом.)

- [ ] **Step 2: Написать `backend/tests/test_schemas.py` (падающие тесты)**

```python
import pytest
from pydantic import ValidationError

from baduk_backend.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    DoneMessage,
    ErrorMessage,
    MoveInfo,
    ProgressMessage,
    RootInfo,
    StreamAnalyzeRequest,
)


def _base_fields() -> dict:
    return {
        "moves": [],
        "rules": "chinese",
        "komi": 7.5,
        "boardXSize": 19,
        "boardYSize": 19,
        "maxVisits": 50,
        "includeOwnership": True,
    }


def test_analyze_request_accepts_single_analyze_turn():
    request = AnalyzeRequest(analyzeTurns=[0], **_base_fields())
    assert request.analyzeTurns == [0]


def test_analyze_request_rejects_multiple_analyze_turns():
    with pytest.raises(ValidationError):
        AnalyzeRequest(analyzeTurns=[0, 1], **_base_fields())


def test_analyze_request_rejects_empty_analyze_turns():
    with pytest.raises(ValidationError):
        AnalyzeRequest(analyzeTurns=[], **_base_fields())


def test_stream_request_accepts_multiple_turn_numbers():
    request = StreamAnalyzeRequest(turnNumbers=[0, 1, 2], **_base_fields())
    assert request.turnNumbers == [0, 1, 2]


def test_stream_request_rejects_empty_turn_numbers():
    with pytest.raises(ValidationError):
        StreamAnalyzeRequest(turnNumbers=[], **_base_fields())


def test_analyze_response_parses_katago_style_payload():
    response = AnalyzeResponse.model_validate(
        {
            "id": "test-1",
            "turnNumber": 0,
            "moveInfos": [
                {
                    "move": "Q4",
                    "winrate": 0.55,
                    "scoreLead": 1.2,
                    "visits": 50,
                    "prior": 0.3,
                    "pv": ["Q4", "D4"],
                }
            ],
            "rootInfo": {"winrate": 0.55, "scoreLead": 1.2, "visits": 50},
            "ownership": [0.1, 0.2],
        }
    )
    assert response.moveInfos[0].move == "Q4"
    assert isinstance(response.moveInfos[0], MoveInfo)
    assert isinstance(response.rootInfo, RootInfo)


def test_progress_message_serializes_nested_result():
    message = ProgressMessage(
        turnNumber=0,
        total=3,
        result=AnalyzeResponse(
            id="test-1",
            moveInfos=[],
            rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=1),
        ),
    )
    dumped = message.model_dump()
    assert dumped["type"] == "progress"
    assert dumped["result"]["id"] == "test-1"


def test_done_message_has_fixed_type():
    assert DoneMessage().model_dump() == {"type": "done"}


def test_error_message_carries_detail():
    assert ErrorMessage(detail="boom").model_dump() == {"type": "error", "detail": "boom"}
```

- [ ] **Step 3: Запустить тесты, убедиться, что падают**

Run: `.venv\Scripts\python.exe -m pytest tests/test_schemas.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'baduk_backend.api.schemas'` (или `ImportError`).

- [ ] **Step 4: Написать `backend/src/baduk_backend/api/schemas.py`**

```python
from typing import Literal

from pydantic import BaseModel, Field


class MoveInfo(BaseModel):
    move: str
    winrate: float
    scoreLead: float
    visits: int
    prior: float
    pv: list[str]


class RootInfo(BaseModel):
    winrate: float
    scoreLead: float
    visits: int


class AnalyzeRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    rules: str
    komi: float
    boardXSize: int
    boardYSize: int
    analyzeTurns: list[int] = Field(min_length=1, max_length=1)
    maxVisits: int
    includeOwnership: bool = False


class AnalyzeResponse(BaseModel):
    id: str
    turnNumber: int | None = None
    moveInfos: list[MoveInfo]
    rootInfo: RootInfo
    ownership: list[float] | None = None


class StreamAnalyzeRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    rules: str
    komi: float
    boardXSize: int
    boardYSize: int
    turnNumbers: list[int] = Field(min_length=1)
    maxVisits: int
    includeOwnership: bool = False


class ProgressMessage(BaseModel):
    type: Literal["progress"] = "progress"
    turnNumber: int
    total: int
    result: AnalyzeResponse


class DoneMessage(BaseModel):
    type: Literal["done"] = "done"


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    detail: str
```

- [ ] **Step 5: Запустить тесты, убедиться, что проходят**

Run: `.venv\Scripts\python.exe -m pytest tests/test_schemas.py -v`
Expected: PASS (8 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/src/baduk_backend/api/__init__.py backend/src/baduk_backend/api/schemas.py backend/tests/test_schemas.py
git commit -m "feat: add Pydantic schemas for the analysis API layer"
```

---

### Task 2: Догоняющий фикс EngineManager — drain стейл-очереди

**Files:**
- Modify: `backend/src/baduk_backend/engine_manager.py`
- Test: `backend/tests/test_engine_manager.py`

**Interfaces:**
- Consumes: ничего нового — работает с уже существующими `EngineManager.__init__`, `self._stdout_queue: queue.Queue`, `self.is_running()`, `self.start()`.
- Produces: `EngineManager._drain_stale_queue() -> None` (внутренний метод, вызывается в начале `analyze()` перед отправкой запроса в stdin). Публичное поведение `analyze()` не меняется для всех уже существующих вызывающих кодов.

- [ ] **Step 1: Написать падающий регрессионный тест**

Добавить в конец `backend/tests/test_engine_manager.py` (файл уже импортирует `json`? — нет, нужно добавить `import json` в начало файла, рядом с существующими `import sys` / `import time`):

```python
import json
import sys
import time
from pathlib import Path

import pytest

from baduk_backend.engine_manager import EngineManager, KataGoCrashError
```

И добавить тест в конец файла:

```python
def test_analyze_drains_stale_response_left_by_prior_timeout():
    # Regression test: if a prior analyze() call raised TimeoutError, its late
    # response can still land in the queue afterwards. Without draining it
    # first, the next analyze() call reads that stale line instead of its own
    # response and raises a spurious "Unexpected response id" ValueError.
    manager = EngineManager(fake_katago_command())
    try:
        manager.start()
        manager._stdout_queue.put(json.dumps({"id": "stale-response", "moveInfos": []}))
        response = manager.analyze({"id": "fresh-request", "moves": []})
        assert response["id"] == "fresh-request"
    finally:
        manager.stop()
```

- [ ] **Step 2: Запустить тест, убедиться, что падает**

Run: `.venv\Scripts\python.exe -m pytest tests/test_engine_manager.py::test_analyze_drains_stale_response_left_by_prior_timeout -v`
Expected: FAIL с `ValueError: Unexpected response id 'stale-response', expected 'fresh-request'`

- [ ] **Step 3: Реализовать `_drain_stale_queue()` и вызвать его в `analyze()`**

В `backend/src/baduk_backend/engine_manager.py`, добавить метод в класс `EngineManager` (после `stop()`, перед `analyze()`):

```python
    def _drain_stale_queue(self) -> None:
        # A prior call that hit TimeoutError may still have its late response
        # sitting in the queue; drop it so it can't be mistaken for the
        # answer to the next, unrelated request.
        while True:
            try:
                self._stdout_queue.get_nowait()
            except queue.Empty:
                break
```

И изменить начало `analyze()` (было: `if not self.is_running(): self.start()` сразу за строкой `def analyze(...)`, добавить дренаж сразу после):

```python
    def analyze(self, request: dict, timeout: float = 30.0) -> dict:
        if not self.is_running():
            self.start()
        self._drain_stale_queue()
        assert self._process is not None
        assert self._process.stdin is not None
        request_id = request["id"]
```

(Остальная часть `analyze()` не меняется.)

- [ ] **Step 4: Запустить тест, убедиться, что проходит**

Run: `.venv\Scripts\python.exe -m pytest tests/test_engine_manager.py -v`
Expected: PASS (все тесты файла, включая новый)

- [ ] **Step 5: Commit**

```bash
git add backend/src/baduk_backend/engine_manager.py backend/tests/test_engine_manager.py
git commit -m "fix: drain stale response queue before each EngineManager.analyze() call"
```

---

### Task 3: `auth.py` + `POST /api/analyze` + wiring в `main.py`

**Files:**
- Create: `backend/src/baduk_backend/auth.py`
- Create: `backend/src/baduk_backend/api/analysis.py` (создаётся здесь с HTTP-роутом; WS-роут добавляется в Task 4)
- Modify: `backend/src/baduk_backend/main.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_api_analyze.py`

**Interfaces:**
- Consumes: `AnalyzeRequest`/`AnalyzeResponse` из Task 1 (`baduk_backend.api.schemas`); `EngineManager`, `KataGoCrashError`, `build_katago_command` из `baduk_backend.engine_manager`; `KataGoProfile`, `render_analysis_config` из `baduk_backend.config.profile`.
- Produces: `baduk_backend.auth.AUTH_TOKEN: str`, `baduk_backend.auth.verify_token(token: str | None) -> None` (raises `HTTPException(401)`), `baduk_backend.auth.require_valid_token(x_auth_token: str | None = Header(default=None)) -> None` (FastAPI-зависимость, вызывает `verify_token`). `baduk_backend.api.analysis.router: APIRouter` с маршрутом `POST /api/analyze`. `baduk_backend.api.analysis.get_engine_manager(request: Request) -> EngineManager` и `get_engine_lock(request: Request) -> asyncio.Lock` (FastAPI-зависимости, читают `request.app.state.engine_manager`/`.engine_lock` — используются также в Task 4). `baduk_backend.main._build_engine_manager() -> EngineManager` (читает `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` из окружения, рендерит `.cfg` во временный файл, возвращает готовый `EngineManager`). Тестовые фикстуры `fake_engine_client` и `fake_engine_client_crash` в `conftest.py` — используются также в Task 4.

- [ ] **Step 1: Создать `backend/src/baduk_backend/auth.py`**

```python
import secrets

from fastapi import Header, HTTPException

AUTH_TOKEN = secrets.token_urlsafe(32)


def verify_token(token: str | None) -> None:
    if token is None or not secrets.compare_digest(token, AUTH_TOKEN):
        raise HTTPException(status_code=401, detail="invalid token")


def require_valid_token(x_auth_token: str | None = Header(default=None)) -> None:
    verify_token(x_auth_token)
```

- [ ] **Step 2: Обновить `backend/src/baduk_backend/main.py`**

Заменить содержимое файла целиком на:

```python
import asyncio
import json
import os
import socket
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI

from baduk_backend.api import analysis
from baduk_backend.auth import AUTH_TOKEN, require_valid_token
from baduk_backend.config.profile import KataGoProfile, render_analysis_config
from baduk_backend.engine_manager import EngineManager, build_katago_command

app = FastAPI()
app.include_router(analysis.router)

_DEFAULT_PROFILE = KataGoProfile(
    model_id="phase1-default",
    display_name="Phase 1 default profile",
    rules="chinese",
    board_size=19,
    komi=7.5,
    max_visits=500,
    num_analysis_threads=4,
)


@app.get("/health", dependencies=[Depends(require_valid_token)])
def health() -> dict:
    return {"status": "ok"}


def build_startup_message(port: int, token: str) -> str:
    return json.dumps({"port": port, "token": token})


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _build_engine_manager() -> EngineManager:
    katago_binary = os.environ.get("BADUK_KATAGO_BINARY")
    katago_model = os.environ.get("BADUK_KATAGO_MODEL")
    if not katago_binary or not katago_model:
        raise RuntimeError(
            "BADUK_KATAGO_BINARY and BADUK_KATAGO_MODEL env vars must be set "
            "to run the backend against a real KataGo installation"
        )
    home_data_dir = str(Path(katago_binary).parent)
    config_text = render_analysis_config(_DEFAULT_PROFILE, home_data_dir_override=home_data_dir)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as config_file:
        config_file.write(config_text)
        config_path = config_file.name
    command = build_katago_command(
        katago_binary=katago_binary,
        config_path=config_path,
        model_path=katago_model,
    )
    return EngineManager(command)


def run() -> None:
    import uvicorn

    app.state.engine_manager = _build_engine_manager()
    app.state.engine_lock = asyncio.Lock()

    port = _find_free_port()
    print(build_startup_message(port, AUTH_TOKEN), flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    run()
```

Важно: `AUTH_TOKEN` теперь определён в `auth.py`, но импортирован в `main.py` через `from baduk_backend.auth import AUTH_TOKEN` — это делает `AUTH_TOKEN` атрибутом модуля `baduk_backend.main` тоже, так что существующий `backend/tests/test_main.py` (`from baduk_backend.main import AUTH_TOKEN, _find_free_port, app, build_startup_message`) продолжает работать без изменений — не трогайте `test_main.py` в этой задаче.

- [ ] **Step 3: Создать `backend/src/baduk_backend/api/analysis.py` (пока только HTTP-роут)**

```python
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from baduk_backend.api.schemas import AnalyzeRequest, AnalyzeResponse
from baduk_backend.auth import require_valid_token
from baduk_backend.engine_manager import EngineManager, KataGoCrashError

router = APIRouter()


def get_engine_manager(request: Request) -> EngineManager:
    return request.app.state.engine_manager


def get_engine_lock(request: Request) -> asyncio.Lock:
    return request.app.state.engine_lock


@router.post(
    "/api/analyze",
    response_model=AnalyzeResponse,
    dependencies=[Depends(require_valid_token)],
)
async def analyze(
    body: AnalyzeRequest,
    engine_manager: EngineManager = Depends(get_engine_manager),
    lock: asyncio.Lock = Depends(get_engine_lock),
) -> AnalyzeResponse:
    request_dict = body.model_dump()
    request_dict["id"] = str(uuid.uuid4())
    async with lock:
        try:
            response = await asyncio.to_thread(engine_manager.analyze, request_dict)
        except KataGoCrashError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AnalyzeResponse.model_validate(response)
```

- [ ] **Step 4: Добавить тестовые фикстуры в `backend/tests/conftest.py`**

Заменить содержимое файла целиком на (сохраняет уже существующую `local_katago_config`, добавляет новые):

```python
import asyncio
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from baduk_backend.engine_manager import EngineManager
from baduk_backend.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def local_katago_config():
    katago_binary = os.environ.get("BADUK_KATAGO_BINARY")
    katago_model = os.environ.get("BADUK_KATAGO_MODEL")
    if not katago_binary or not katago_model:
        pytest.skip(
            "BADUK_KATAGO_BINARY and BADUK_KATAGO_MODEL env vars not set; "
            "see tests/local_config.json.example"
        )
    return {"katago_binary": katago_binary, "katago_model": katago_model}


def _wire_app_state(command: list[str]):
    manager = EngineManager(command)
    app.state.engine_manager = manager
    app.state.engine_lock = asyncio.Lock()
    return manager


@pytest.fixture
def fake_engine_client():
    manager = _wire_app_state([sys.executable, str(FIXTURES_DIR / "fake_katago.py")])
    try:
        yield TestClient(app)
    finally:
        manager.stop()
        del app.state.engine_manager
        del app.state.engine_lock


@pytest.fixture
def fake_engine_client_crash():
    manager = _wire_app_state([sys.executable, str(FIXTURES_DIR / "fake_katago_crash.py")])
    try:
        yield TestClient(app)
    finally:
        manager.stop()
        del app.state.engine_manager
        del app.state.engine_lock
```

- [ ] **Step 5: Написать `backend/tests/test_api_analyze.py`**

```python
from baduk_backend.auth import AUTH_TOKEN


def _payload(analyze_turns=None):
    return {
        "moves": [],
        "rules": "chinese",
        "komi": 7.5,
        "boardXSize": 19,
        "boardYSize": 19,
        "analyzeTurns": analyze_turns if analyze_turns is not None else [0],
        "maxVisits": 50,
        "includeOwnership": True,
    }


def test_analyze_returns_move_infos_and_ownership(fake_engine_client):
    response = fake_engine_client.post(
        "/api/analyze",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["moveInfos"][0]["move"] == "Q4"
    assert body["rootInfo"]["winrate"] == 0.55
    assert len(body["ownership"]) == 361


def test_analyze_without_token_returns_401(fake_engine_client):
    response = fake_engine_client.post("/api/analyze", json=_payload())
    assert response.status_code == 401


def test_analyze_with_wrong_token_returns_401(fake_engine_client):
    response = fake_engine_client.post(
        "/api/analyze",
        headers={"X-Auth-Token": "wrong-token"},
        json=_payload(),
    )
    assert response.status_code == 401


def test_analyze_rejects_multiple_analyze_turns(fake_engine_client):
    response = fake_engine_client.post(
        "/api/analyze",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(analyze_turns=[0, 1]),
    )
    assert response.status_code == 422


def test_analyze_rejects_empty_analyze_turns(fake_engine_client):
    response = fake_engine_client.post(
        "/api/analyze",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(analyze_turns=[]),
    )
    assert response.status_code == 422


def test_analyze_returns_503_when_katago_process_crashes(fake_engine_client_crash):
    response = fake_engine_client_crash.post(
        "/api/analyze",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(),
    )
    assert response.status_code == 503
```

- [ ] **Step 6: Запустить тесты, убедиться, что падают (перед реализацией — но реализация уже написана в Step 2/3 выше; вместо этого запустить сейчас, чтобы поймать опечатки)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api_analyze.py -v`
Expected на первой попытке (до Step 2-3): FAIL с `ModuleNotFoundError`. После применения Step 2-3: все тесты должны пройти. Если что-то падает — проверить, что `main.py` действительно подключает `analysis.router` (`app.include_router(analysis.router)`) и что `conftest.py` фикстуры настраивают `app.state` до создания `TestClient`.

- [ ] **Step 7: Запустить тесты, убедиться, что проходят**

Run: `.venv\Scripts\python.exe -m pytest tests/ -v`
Expected: PASS для всех неинтеграционных тестов (включая уже существующие `test_main.py`, `test_engine_manager.py`, `test_profile.py`, `test_schemas.py` — ни один не должен был сломаться).

- [ ] **Step 8: Обновить `backend/README.md`**

Добавить в конец файла новый раздел:

```markdown

## API

- `POST /api/analyze` — анализ одной позиции. Тело запроса и ответ — см.
  `backend/src/baduk_backend/api/schemas.py` (`AnalyzeRequest`/`AnalyzeResponse`).
  Требует заголовок `X-Auth-Token`. `503`, если процесс KataGo упал.
- `WS /api/analyze/stream?token=...` — потоковый анализ партии, прогресс по
  ходам (`StreamAnalyzeRequest` на входе, `progress`/`done`/`error` сообщения
  на выходе). Неверный/отсутствующий токен → закрытие соединения кодом `1008`.
```

- [ ] **Step 9: Commit**

```bash
git add backend/src/baduk_backend/auth.py backend/src/baduk_backend/main.py backend/src/baduk_backend/api/analysis.py backend/tests/conftest.py backend/tests/test_api_analyze.py backend/README.md
git commit -m "feat: add POST /api/analyze endpoint over EngineManager"
```

---

### Task 4: `WS /api/analyze/stream`

**Files:**
- Modify: `backend/src/baduk_backend/api/analysis.py`
- Test: `backend/tests/test_api_analyze_stream.py`

**Interfaces:**
- Consumes: `StreamAnalyzeRequest`, `ProgressMessage`, `DoneMessage`, `ErrorMessage` из Task 1; `AUTH_TOKEN` из `baduk_backend.auth`; `get_engine_manager`/`get_engine_lock` понятие из Task 3 (для WS используется прямой доступ через `websocket.app.state`, без `Depends`, — FastAPI websocket-роуты не используют HTTP-style `Depends` для `Request`-объекта таким же образом); `fake_engine_client`/`fake_engine_client_crash` фикстуры из Task 3.
- Produces: WS-маршрут `/api/analyze/stream`, публично зафиксированный протокол сообщений (см. Global Constraints).

- [ ] **Step 1: Написать падающий тест `backend/tests/test_api_analyze_stream.py`**

```python
from starlette.websockets import WebSocketDisconnect

from baduk_backend.auth import AUTH_TOKEN


def _stream_payload(turn_numbers):
    return {
        "moves": [],
        "rules": "chinese",
        "komi": 7.5,
        "boardXSize": 19,
        "boardYSize": 19,
        "turnNumbers": turn_numbers,
        "maxVisits": 50,
        "includeOwnership": True,
    }


def test_stream_rejects_missing_token(fake_engine_client):
    with fake_engine_client.websocket_connect("/api/analyze/stream") as ws:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
    assert exc_info.value.code == 1008


def test_stream_rejects_wrong_token(fake_engine_client):
    with fake_engine_client.websocket_connect("/api/analyze/stream?token=wrong") as ws:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
    assert exc_info.value.code == 1008


def test_stream_sends_progress_per_turn_then_done(fake_engine_client):
    with fake_engine_client.websocket_connect(f"/api/analyze/stream?token={AUTH_TOKEN}") as ws:
        ws.send_json(_stream_payload([0, 1]))

        first = ws.receive_json()
        assert first["type"] == "progress"
        assert first["turnNumber"] == 0
        assert first["total"] == 2
        assert first["result"]["moveInfos"][0]["move"] == "Q4"

        second = ws.receive_json()
        assert second["type"] == "progress"
        assert second["turnNumber"] == 1
        assert second["total"] == 2

        done = ws.receive_json()
        assert done == {"type": "done"}


def test_stream_sends_error_for_invalid_message(fake_engine_client):
    with fake_engine_client.websocket_connect(f"/api/analyze/stream?token={AUTH_TOKEN}") as ws:
        ws.send_json({"not": "a valid stream request"})
        message = ws.receive_json()
        assert message == {"type": "error", "detail": "invalid request"}


def test_stream_sends_error_when_katago_crashes(fake_engine_client_crash):
    with fake_engine_client_crash.websocket_connect(f"/api/analyze/stream?token={AUTH_TOKEN}") as ws:
        ws.send_json(_stream_payload([0]))
        message = ws.receive_json()
        assert message["type"] == "error"
```

Добавить `import pytest` в начало файла (использован в `pytest.raises`).

- [ ] **Step 2: Запустить тест, убедиться, что падает**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api_analyze_stream.py -v`
Expected: FAIL — маршрут `/api/analyze/stream` ещё не существует (404 / `WebSocketDisconnect` с неожиданным кодом).

- [ ] **Step 3: Добавить WS-маршрут в `backend/src/baduk_backend/api/analysis.py`**

Добавить в начало файла импорты `secrets`, `WebSocket`, `ValidationError`, и новые схемы:

```python
import asyncio
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from pydantic import ValidationError

from baduk_backend.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    DoneMessage,
    ErrorMessage,
    ProgressMessage,
    StreamAnalyzeRequest,
)
from baduk_backend.auth import AUTH_TOKEN, require_valid_token
from baduk_backend.engine_manager import EngineManager, KataGoCrashError
```

(Это заменяет прежний блок импортов Task 3 — добавлены `secrets`, `WebSocket`, `ValidationError`, `DoneMessage`, `ErrorMessage`, `ProgressMessage`, `StreamAnalyzeRequest`, `AUTH_TOKEN`.)

И добавить в конец файла, после существующего `analyze()`:

```python
@router.websocket("/api/analyze/stream")
async def analyze_stream(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    await websocket.accept()
    if token is None or not secrets.compare_digest(token, AUTH_TOKEN):
        await websocket.close(code=1008)
        return

    engine_manager: EngineManager = websocket.app.state.engine_manager
    lock: asyncio.Lock = websocket.app.state.engine_lock

    try:
        raw = await websocket.receive_json()
        stream_request = StreamAnalyzeRequest.model_validate(raw)
    except (ValidationError, ValueError):
        await websocket.send_json(ErrorMessage(detail="invalid request").model_dump())
        await websocket.close()
        return

    base_request = stream_request.model_dump(exclude={"turnNumbers"})
    total = len(stream_request.turnNumbers)

    for turn_number in stream_request.turnNumbers:
        request_dict = dict(base_request)
        request_dict["id"] = str(uuid.uuid4())
        request_dict["analyzeTurns"] = [turn_number]
        try:
            async with lock:
                response = await asyncio.to_thread(engine_manager.analyze, request_dict)
        except KataGoCrashError as exc:
            await websocket.send_json(ErrorMessage(detail=str(exc)).model_dump())
            await websocket.close()
            return
        message = ProgressMessage(
            turnNumber=turn_number,
            total=total,
            result=AnalyzeResponse.model_validate(response),
        )
        await websocket.send_json(message.model_dump())

    await websocket.send_json(DoneMessage().model_dump())
    await websocket.close()
```

- [ ] **Step 4: Запустить тест, убедиться, что проходит**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api_analyze_stream.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Запустить весь неинтеграционный набор тестов**

Run: `.venv\Scripts\python.exe -m pytest tests/ -v`
Expected: PASS для всех (никаких регрессий в предыдущих задачах).

- [ ] **Step 6: Commit**

```bash
git add backend/src/baduk_backend/api/analysis.py backend/tests/test_api_analyze_stream.py
git commit -m "feat: add WS /api/analyze/stream endpoint with per-turn progress"
```

---

### Task 5: Реальный integration-тест через HTTP-слой

**Files:**
- Test: `backend/tests/test_api_analyze_integration.py`

**Interfaces:**
- Consumes: `local_katago_config` фикстура (уже существует в `conftest.py`), `KataGoProfile`/`render_analysis_config` из `baduk_backend.config.profile`, `EngineManager`/`build_katago_command` из `baduk_backend.engine_manager`, `AUTH_TOKEN` из `baduk_backend.auth`, `app` из `baduk_backend.main`.
- Produces: ничего для других задач — терминальный acceptance-тест этого плана.

- [ ] **Step 1: Написать `backend/tests/test_api_analyze_integration.py`**

```python
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from baduk_backend.auth import AUTH_TOKEN
from baduk_backend.config.profile import KataGoProfile, render_analysis_config
from baduk_backend.engine_manager import EngineManager, build_katago_command
from baduk_backend.main import app

pytestmark = pytest.mark.integration


def test_real_katago_analyze_endpoint_returns_winrate_and_ownership(local_katago_config, tmp_path):
    profile = KataGoProfile(
        model_id="integration-test",
        display_name="Integration test profile",
        rules="chinese",
        board_size=19,
        komi=7.5,
        max_visits=50,
        num_analysis_threads=2,
    )
    katago_binary_dir = str(Path(local_katago_config["katago_binary"]).parent)
    config_path = tmp_path / "analysis_config.cfg"
    config_path.write_text(render_analysis_config(profile, home_data_dir_override=katago_binary_dir))

    command = build_katago_command(
        katago_binary=local_katago_config["katago_binary"],
        config_path=str(config_path),
        model_path=local_katago_config["katago_model"],
    )
    manager = EngineManager(command)
    app.state.engine_manager = manager
    app.state.engine_lock = asyncio.Lock()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/analyze",
            headers={"X-Auth-Token": AUTH_TOKEN},
            json={
                "moves": [],
                "rules": profile.rules,
                "komi": profile.komi,
                "boardXSize": profile.board_size,
                "boardYSize": profile.board_size,
                "analyzeTurns": [0],
                "maxVisits": profile.max_visits,
                "includeOwnership": True,
            },
            timeout=60.0,
        )
    finally:
        manager.stop()
        del app.state.engine_manager
        del app.state.engine_lock

    assert response.status_code == 200
    body = response.json()
    assert len(body["moveInfos"]) > 0
    assert "winrate" in body["moveInfos"][0]
    assert "pv" in body["moveInfos"][0]
    assert body["ownership"] is not None
    assert len(body["ownership"]) == profile.board_size * profile.board_size
```

- [ ] **Step 2: Запустить тест против реального локального KataGo**

Run (PowerShell, с уже установленными `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL`):

```powershell
.venv\Scripts\python.exe -m pytest tests/test_api_analyze_integration.py -v -m integration
```

Expected: PASS, ответ содержит реальные `winrate`/`pv`/`ownership` от KataGo (аналогично уже существующему `test_engine_manager_integration.py`, но через HTTP-слой).

- [ ] **Step 3: Запустить полный набор (unit + integration) для финальной проверки**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v -m integration
.venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: PASS для обоих запусков (интеграционные и неинтеграционные тесты отдельно, как и раньше).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_api_analyze_integration.py
git commit -m "test: add real-KataGo integration test for POST /api/analyze"
```

---

## Definition of Done

- `POST /api/analyze` и `WS /api/analyze/stream` реализованы поверх единственного `EngineManager` в `app.state`, защищённого `asyncio.Lock`.
- Оба отложенных при финальном ревью backend-плана пункта закрыты: drain стейл-очереди (Task 2) и блокировка от конкурентных `analyze()` (Task 3/4).
- Весь неинтеграционный набор (`pytest` без `-m integration`) проходит зелёным после каждой задачи.
- Integration-тест (Task 5) подтверждает, что весь HTTP-путь (не только `EngineManager` напрямую) отдаёт настоящие winrate/ownership/PV от локального KataGo.
- `backend/README.md` документирует новые эндпоинты.
- Ни один существующий тест (`test_main.py`, `test_engine_manager.py`, `test_profile.py`, `test_engine_manager_integration.py`) не сломан.
