# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Статус проекта

"Baduk" — корейское название игры Го. Проект — это ИИ-ассистент, который позволяет просматривать партии в Го (SGF), анализирует их движком KataGo, а LLM (с опорой на RAG-базу знаний) формирует рациональные объяснения в тоне тренера для игроков кю-уровня. Также ведётся "паспорт игрока" (профиль повторяющихся сильных/слабых сторон по партиям), а архитектура с самого начала спроектирована как плагинная.

**Фаза 1 (SGF viewer + KataGo-анализ, без LLM) реализована целиком — backend и frontend — и смёржена в `main`.** Backend: FastAPI sidecar + `EngineManager` (жизненный цикл KataGo Analysis Engine) + `POST /api/analyze`/`WS /api/analyze/stream`. Frontend: Electron+TypeScript+Preact, доска на `@sabaki/shudan`, SGF/дерево вариаций на `@sabaki/sgf`+`@sabaki/immutable-gametree`, позиция на доске через `@sabaki/go-board`, состояние на `@preact/signals`, winrate/score-lead график на `uPlot`. Полная история и обоснования решений — `task_plan.md`/`findings.md`/`progress.md`. Фазы 2–6 (LLM-объяснения, RAG, паспорт игрока, формализация плагинов, кросс-платформенность) — не начаты.

**Перед тем как предлагать реализацию новой фазы, прочитайте [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).** Там — полный утверждённый дизайн: сравнение опенсорсных движков/GUI Го, приведшее к выбору стека; two-process архитектура (Electron/TypeScript фронтенд + Python backend-сервис, связанные локальным HTTP/WebSocket API); детерминированный feature-extraction слой, превращающий сырые данные KataGo в структурированные находки для LLM (и его подсистема калибровки/бэктестинга — существует специально, чтобы LLM не галлюцинировала при анализе партий); формат манифеста плагинов; модель данных паспорта игрока; поэтапный MVP-roadmap (вьюер+KataGo → LLM-объяснения → RAG → паспорт игрока → формализация плагинов → кросс-платформенность).

## Сборка, линт, тесты

**Backend** (`backend/`, Python, package-менеджер `uv`, но на этой машине он временами пропадал из PATH — рабочий fallback через `.venv` напрямую):
```powershell
cd backend
.venv\Scripts\python.exe -m pytest -v              # юнит-тесты (integration-маркер исключён по умолчанию)
.venv\Scripts\python.exe -m pytest -v -m integration  # реальный KataGo — требует BADUK_KATAGO_BINARY/BADUK_KATAGO_MODEL
                                                       # (тот же прогон также содержит три теста реальных LLM API — Claude требует BADUK_CLAUDE_API_KEY, Gemini — BADUK_GEMINI_API_KEY, llama-cpp-python — BADUK_LLAMA_MODEL_PATH, каждый самостоятельно скипается без своего требования)
```
Backend-сервис (`run()` в `main.py`) при старте требует `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` плюс конфигурацию активного LLM-провайдера (fail-fast, `RuntimeError` без неё) — используется эндпоинтом `/api/explain`. Провайдер выбирается через `BADUK_LLM_PROVIDER` (`"claude"`, `"gemini"` или `"llama"`, по умолчанию `"llama"`, если переменная не задана): для `claude` требуется `BADUK_CLAUDE_API_KEY` (опционально `BADUK_CLAUDE_MODEL` переопределяет модель), для `gemini` — `BADUK_GEMINI_API_KEY` (опционально `BADUK_GEMINI_MODEL`), для `llama` — `BADUK_LLAMA_MODEL_PATH` (опционально `BADUK_LLAMA_N_GPU_LAYERS`).

**Frontend** (`frontend/`, Electron+TS+Preact, `pnpm`):
```powershell
cd frontend
pnpm exec vitest run          # тесты (jsdom)
pnpm run typecheck:web        # typecheck renderer
pnpm run typecheck:node       # typecheck main/preload
pnpm exec electron-vite dev   # дев-сборка; требует запущенный backend-sidecar (BADUK_BACKEND_COMMAND) для реального анализа
```
`pnpm run lint` на момент последнего мержа **красный** (унаследованные от scaffold'а `@typescript-eslint` правила: `explicit-function-return-type`, `no-explicit-any` и т.п. — не критично для функциональности, зафиксировано как backlog в `task_plan.md`, не блокирует работу).

## Работа в этом репозитории

- Пользователь общается по-русски и ожидает ответов на русском по этому проекту.
- Не начинайте писать код новой фазы/подсистемы, пока пользователь явно не попросит начать её в конкретной сессии — это было явное, неоднократно повторённое требование при проектировании архитектуры, и оно применяется к каждой новой фазе, а не только к самой первой.
- Не делайте предположений о конкретных библиотеках/раскладке файлов новой фазы сверх того, что уже реализовано (Фаза 1) или зафиксировано в `docs/ARCHITECTURE.md` — раскладка внутри ещё не начатых фаз (2–6) пока открыта.
- **Конфиги/пути не коммитятся в репозиторий** — KataGo-бинарник/модель и команда запуска backend-sidecar передаются только через переменные окружения (`BADUK_KATAGO_BINARY`, `BADUK_KATAGO_MODEL`, `BADUK_BACKEND_COMMAND`), никогда не хардкодятся в исходниках/доках. Это уже нарушалось один раз в истории проекта и было исправлено отдельным ревью — не повторять.

## Планирование и восстановление контекста

В корне репозитория ведутся три постоянных файла — читайте их в начале каждой сессии, до того как расспрашивать пользователя заново:

- **`task_plan.md`** — статус фаз MVP-roadmap, текущие и будущие задачи, лог архитектурных решений.
- **`findings.md`** — обоснования уже принятых решений (сравнения стека/фреймворков, результаты дизайн-ревью и т.п.) — чтобы не пересобирать рассуждение с нуля.
- **`progress.md`** — журнал по сессиям: что сделано, что решено, с чего начинать дальше.

Обновляйте все три файла по ходу работы и обязательно — записью в `progress.md` — перед завершением сессии.

**Git-ветки**: разработка каждой фазы или задачи ведётся в отдельной ветке, никогда не коммитьте реализацию напрямую в `main`. Именование: `phase-N-<short-name>` для фаз roadmap, `fix-<short-name>` для точечных правок. Перед началом работы над кодом — создайте/переключитесь на ветку и отметьте это в `task_plan.md`.
