# Design: HTTP/WS API-слой над EngineManager (Фаза 1, недостающий кусок)

Дата: 2026-08-03
Статус: утверждён пользователем, готов к переходу в implementation-план
Ветка: `phase-1-backend-api`

## Контекст

При планировании frontend-части Фазы 1 обнаружен пробел: backend implementation-план (`docs/superpowers/plans/2026-08-03-phase-1-backend-engine-manager.md`, уже смёржен в `main`) покрыл только шаги 1–2 vertical slice из дизайн-спека Фазы 1 (`docs/superpowers/specs/2026-08-03-phase-1-viewer-katago-design.md`) — sidecar-скелет и `EngineManager`. Шаг 3 («API поверх Engine Manager: HTTP REST-эндпоинт... WebSocket стримит прогресс анализа») реализован не был — сейчас backend отдаёт только `/health`.

Frontend-шаги 5–6 (IPC-клиент + overlay-панели + сквозная приёмка) не могут быть реализованы без этого слоя — их нечем будет кормить реальными данными. Этот спек закрывает шаг 3 отдельным небольшим планом, прежде чем frontend-работа (ветка `phase-1-frontend`, сейчас приостановлена) продолжится.

Финальное whole-branch ревью backend-плана осознанно отложило два пункта именно до появления этого HTTP-слоя (см. `docs/superpowers/plans/2026-08-03-phase-1-backend-engine-manager.md`, «Deferred Findings Triage»): отсутствие блокировки от конкурентных `analyze()` и отсутствие ресинхронизации запрос/ответ после `TimeoutError`. Оба закрываются в рамках этого дизайна, а не остаются техдолгом дальше.

## Зафиксированные решения

| Решение | Выбор | Обоснование |
|---|---|---|
| Гранулярность WS-прогресса | **Прогресс по ходам** (одно сообщение на завершённый анализ хода), не live внутри-поисковый winrate | live-прогресс через KataGo `reportDuringSearchEvery` заметно усложнил бы `EngineManager` (несколько JSON-ответов на один id) — не нужно для приёмочного критерия Фазы 1 (открыть партию → увидеть прогресс/результат по ходам). Кандидат на будущее, если понадобится Lizzie-подобный live-режим. |
| Конкурентность | **Один `asyncio.Lock` вокруг единственного `EngineManager`** | Desktop-приложение одного пользователя — пул процессов под разные модели/профили это будущая работа по ARCHITECTURE.md, не сейчас. Блокирующий `analyze()` вызывается через `asyncio.to_thread()`, чтобы не морозить event loop. |
| Формализация схемы | **Пока только Pydantic-модели в backend** | `shared/schemas/` — JSON Schema как единый источник типов для двух языков — имеет смысл заводить, когда появится реальный TS-потребитель (IPC-клиент). Сейчас это была бы спекуляция без потребителя. |

## Архитектура

- `backend/src/baduk_backend/api/__init__.py` (пустой) + `backend/src/baduk_backend/api/analysis.py` — новый пакет, соответствует уже описанной в дизайн-спеке Фазы 1 структуре каталогов (`backend/src/baduk_backend/api/`).
- Pydantic-модели запроса/ответа зеркалируют протокол KataGo Analysis Engine напрямую (`moves`, `rules`, `komi`, `boardSize`, `analyzeTurns`, `maxVisits`, `includeOwnership` → `moveInfos`/`rootInfo`/`ownership`) — без трансформации в «находки» (это feature-extraction слой Фазы 2, вне рамок этого плана).
- `APIRouter` с двумя эндпоинтами, подключается в `main.py` через `app.include_router(...)`.
- Единственный экземпляр `EngineManager` создаётся при старте приложения и живёт в `app.state.engine_manager`; `asyncio.Lock` — тоже в `app.state`.

## Компоненты

**`POST /api/analyze`** — синхронный запрос одной позиции, делегирует в `EngineManager.analyze()` (под локом, через `to_thread`), возвращает разобранный JSON-ответ напрямую. Для интерактивной навигации по дереву вариаций (пересчитать анализ текущего хода).

**`WS /api/analyze/stream`** — принимает список ходов партии (весь набор `analyzeTurns` разом, в одном сообщении на входе), сервер по очереди вызывает `EngineManager.analyze()` на каждый ход (под тем же локом — конкурентных вызовов не бывает по построению), шлёт клиенту:
- `{"type": "progress", "turnNumber": N, "total": M, "result": {...}}` — на каждый завершённый ход;
- `{"type": "done"}` — по завершении всех ходов;
- `{"type": "error", "detail": "..."}` — при сбое, затем закрытие соединения.

## Догоняющий фикс EngineManager

`analyze()` (в уже смёрженном `backend/src/baduk_backend/engine_manager.py`) получает шаг в начале: нерасширяющий drain внутренней очереди (`while not self._stdout_queue.empty(): self._stdout_queue.get_nowait()`) перед отправкой нового запроса в stdin. С введённым выше локом единственный способ появления «зависшей» строки в очереди — предыдущий вызов поймал `TimeoutError`, и его запоздавший ответ всё же пришёл. Drain перед следующим вызовом гарантированно выкидывает такую строку, не давая ей desync'нуть ответ на следующий, не связанный с ней запрос.

## Обработка ошибок

- `KataGoCrashError` из `EngineManager` → `POST /api/analyze` отвечает `503 Service Unavailable` с телом `{"detail": "..."}"`.
- На WS — сообщение `{"type": "error", "detail": "..."}`, затем штатное закрытие соединения (не обрыв).
- Некорректный JSON во входящем WS-сообщении → `{"type": "error", "detail": "invalid request"}`, закрытие.

## Тестирование

- Route-level тесты через `fastapi.testclient.TestClient` (уже используется в проекте), включая `client.websocket_connect(...)` для WS — против уже существующего fake-katago фикстура (`backend/tests/fixtures/fake_katago.py`), без реального движка.
- Отдельный unit-тест на догоняющий фикс `EngineManager`: искусственно заполнить очередь «зависшей» строкой, вызвать `analyze()` с новым id, убедиться, что стейл-строка не всплывает в ответе.
- Реальный integration-тест против локального KataGo (по аналогии с Task 5 backend-плана, тот же `local_katago_config` fixture, `@pytest.mark.integration`) — один тест на `POST /api/analyze` через реальный движок, подтверждающий, что весь HTTP-путь (не только `EngineManager` напрямую) отдаёт настоящие winrate/ownership/PV.

## Вне рамок этого плана (явно)

Формализация `shared/schemas/`, feature-extraction слой (находки), live внутри-поисковый прогресс, пул процессов под несколько моделей/профилей одновременно. Frontend/Electron-код по-прежнему не в этом плане.

**WS-аутентификация:** тот же токен, что и `/health` (`AUTH_TOKEN`), передаётся как query-параметр — `WS /api/analyze/stream?token=...` (WebSocket API браузера/клиента не позволяет произвольные заголовки при установлении соединения, поэтому query-параметр — стандартный паттерн для WS-аутентификации, а не первое сообщение). Неверный/отсутствующий токен → сервер закрывает соединение сразу после handshake с кодом `1008` (policy violation).

## Ссылки

- `docs/superpowers/specs/2026-08-03-phase-1-viewer-katago-design.md` — исходный дизайн-спек всей Фазы 1.
- `docs/superpowers/plans/2026-08-03-phase-1-backend-engine-manager.md` — уже выполненный backend-план (sidecar+EngineManager), включая «Deferred Findings Triage» с двумя пунктами, которые закрывает этот план.
- `docs/ARCHITECTURE.md` — общая архитектура (`backend/src/baduk_backend/api/`, `shared/schemas/`).
