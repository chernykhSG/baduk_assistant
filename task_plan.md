# Baduk Assistant — Task Plan

Постоянный план проекта. Обновляется по ходу работы; читается в начале каждой сессии вместе с `findings.md` и `progress.md`.

## Постоянные правила (standing policies)

- **Git-ветки**: разработка каждой фазы/задачи ведётся в отдельной ветке, никогда не коммитим реализацию напрямую в `main`. Именование: `phase-N-<short-name>` для фаз roadmap ниже, `fix-<short-name>` для точечных правок. Перед началом работы — создать/переключиться на ветку и отметить задачу здесь как "in progress".
- **Восстановление контекста**: в конце каждой сессии — запись в `progress.md` (что сделано, что решено, что осталось открытым) и обновление статусов в этом файле. Новая сессия начинает с чтения этих трёх файлов, а не с расспросов заново.
- **Не начинать реализацию без явного запроса** — правило из `CLAUDE.md`: репозиторий на стадии «архитектура утверждена, реализация не начата», пока пользователь явно не попросит начать конкретную фазу.

## Где мы сейчас

**Фаза 1 (SGF viewer + KataGo-анализ, без LLM) реализована полностью — backend и frontend — и смёржена в `main`.**
- Sidecar-скелет + `EngineManager`: health-check (FastAPI, токен-аутентификация), `KataGoProfile` + шаблон `.cfg`, `EngineManager` (жизненный цикл процесса KataGo Analysis Engine, авто-restart, дренаж stdout/stderr), реальный integration-тест против локального KataGo пользователя (winrate/ownership/PV подтверждены). Финальное ревью пройдено (7 Important-находок исправлены одним fix-wave).
- API-слой: `POST /api/analyze` + `WS /api/analyze/stream` поверх единственного `EngineManager`/`asyncio.Lock` в `app.state`. 5 задач + один fix-wave на 5 Important-находок финального ревью.
- Frontend (ветка `phase-1-frontend`, 11 задач через `subagent-driven-development`): Electron+TS+Preact-приложение с нуля — scaffold, backend-connection, SGF-парсинг+дерево (`@sabaki/sgf`+`@sabaki/immutable-gametree`), типизированный IPC-клиент, GTP-координатный request-builder, позиция на доске через `@sabaki/go-board`, состояние на `@preact/signals`, доска на `@sabaki/shudan`, дерево вариаций+клавиатурная навигация, ownership heatmap+PV-стрелки+winrate/score-lead график (`uPlot`), финальная интеграция (AppShell, drag&drop SGF, ConnectionGate, error-баннеры). Финальное whole-branch ревью (opus) нашло 7 Important-находок — 5 исправлены одним fix-wave (rectangular-board SGF ронял рендер вместо явной ошибки; второй загруженный SGF не закрывал предыдущий WS-стрим, смешивая анализ двух партий; узлы вариаций вне основной линии молча показывали чужой анализ; winrate-график вероятно рисовал KataGo's SIDETOMOVE-перспективу — починено на backend через `reportAnalysisWinratesAs = BLACK`; ownership-heatmap показывал числовые подписи на всех 361 точках вместо только по hover). Реальный запуск Electron-окна вручную подтверждён скриншотом (ConnectionGate корректно рендерит error-состояние без backend).

Следующий шаг — Фаза 2 (LLM-объяснения поверх KataGo, без RAG) — **не начинать** до явного запроса пользователя (см. backlog ниже про парковенные находки Фазы 1, которые стоит учитывать в первую очередь).

## Roadmap (из `docs/ARCHITECTURE.md` → «Поэтапный MVP-roadmap»)

| # | Фаза | Статус |
|---|------|--------|
| 1 | SGF viewer + KataGo-анализ (без LLM) | **полностью в `main`** (backend + frontend) |
| 2 | LLM-объяснения поверх KataGo (без RAG) | не начата |
| 3 | RAG-база знаний | не начата |
| 4 | Паспорт игрока | не начата |
| 5 | Формализация плагинной системы | не начата |
| 6 | Кросс-платформенная валидация | не начата |

Детали каждой фазы, критические файлы и критерии проверки — см. `docs/ARCHITECTURE.md` (разделы «Поэтапный MVP-roadmap» и «Проверка»).

## Текущие задачи (current tasks)

- [x] Backend Фазы 1 (sidecar+EngineManager+API-слой) — реализован, смёржен в `main`.
- [x] Brainstorming frontend-части Фазы 1 — дизайн-спек `docs/superpowers/specs/2026-08-04-phase-1-frontend-design.md` (визуальное сравнение layout + текстовые вопросы: SQLite отложен, renderer владеет IPC напрямую, uPlot, layout-вариант B).
- [x] Детальный implementation-план frontend-части — `docs/superpowers/plans/2026-08-04-phase-1-frontend.md` (11 задач).
- [x] Выполнить план frontend-части через `subagent-driven-development` (11 задач + финальное ревью + один fix-wave на 5 из 7 Important-находок).
- [ ] Смёржить ветку `phase-1-frontend` в `main` через `superpowers:finishing-a-development-branch`.
- [ ] Ручная сквозная приёмка Фазы 1 целиком с реальным backend+KataGo (drag&drop SGF → дерево+доска → live winrate/ownership по мере прогона) — до сих пор не выполнена ни разу за всю сессию; единственная ручная проверка была для error-состояния ConnectionGate без backend.

## Будущие задачи (backlog)

- **Приоритетно перед Фазой 2**: `streamAnalysis` (frontend `ipc/client.ts`) не ловит WS `close`/`error` события — обрыв соединения (KataGo упал жёстко, sidecar вышел) оставляет `streamStatus` навсегда в `'streaming'` без баннера/повтора. Найдено финальным ревью frontend-ветки (Important), сознательно не включено в fix-wave (не load-bearing ни для одной будущей задачи, но реальная дыра в UX). Почините одним из первых при возврате к frontend-коду.
- **Приоритетно перед Фазой 2**: ни разу за всю сессию не выполнена ручная сквозная приёмка Фазы 1 целиком с реальным backend+KataGo (см. «Текущие задачи» выше) — сделать перед тем, как считать Фазу 1 действительно завершённой, не только «код смёржен».
- Проверить точечно совместимость нужных React-only библиотек (напр. shadcn/Radix) через `preact/compat`, если/когда они понадобятся во frontend-части Фазы 1 (см. `findings.md`).
- Минорные находки API-слоя (backend), осознанно отложены: дублирование полей `AnalyzeRequest`/`StreamAnalyzeRequest` (нет общего базового класса), WS-хендлер после закрытия клиентом не ловит `WebSocketDisconnect`, `turnNumbers` не ограничен сверху по длине, схемы без границ значений (`maxVisits`/`komi`/`boardXSize`/`boardYSize`), `main.py`'s `try/finally` не покрывает `_find_free_port()`/`print()` перед ним.
- Минорные находки frontend-ветки, осознанно отложены: `pnpm run lint` красный (35 ошибок/70 предупреждений — `explicit-function-return-type`/`no-explicit-any`, унаследованные scaffold-правила, но нарушаются новым кодом — стоит либо ослабить правила, либо почистить); CSS-классы `.app-shell__banner`/`.connection-gate--error`/`.app-shell__tree`/`.board-view`/`.variation-tree`/`.winrate-chart` не имеют стилей в `main.css` (ошибки рендерятся как неоформленный текст, график не резайзится); `mapSgfRules` тихо приводит нераспознанный `RU` к `chinese` без предупреждения; дублирование `GTP_COLUMNS` между `BoardView.tsx` и `gameRequestBuilder.ts`; `getConnection()` в IPC-клиенте навсегда кэширует отклонённый promise без пути повтора; `sgfError`-сигнал в `App.tsx` не экспортирован — тестам нечем его сбрасывать между тестами (скрытая ловушка, не текущий сбой).
- Уточнить, почему `uv` пропал из PATH в части сессий (Task 1 backend использовал его успешно, поздние задачи — уже нет); README backend уже документирует рабочий fallback через `.venv` напрямую.
- Фаза 2 и далее — не начинать, пока не выполнена ручная сквозная приёмка Фазы 1 (см. выше) по критериям из `docs/ARCHITECTURE.md`.
- **Связь Фазы 2 ↔ Фазы 4 (миссия проекта — не потерять).** Миссия проекта: KataGo даёт объективный анализ, но ассистент должен учить через принципы рационального мышления и выявлять повторяющиеся ошибки/привычки, а не просто разбирать «лучший ход здесь» — чтобы игрок переносил понимание на новые, ранее не встречавшиеся позиции. Текущий дизайн это поддерживает (детекторы формализованы через структурные свойства позиции, а не память конкретных ходов; LLM по `§4` ARCHITECTURE.md интерпретирует находки через принципы/RAG, не переоценивает позицию; Player Passport — Фаза 4 — как раз хранит таксономию повторяющихся ошибок и тренд по времени). Но сейчас Фаза 2 (real-time объяснение партии) и Фаза 4 (накопленный паспорт) не связаны в дизайне — объяснение конкретной находки не подмешивает релевантные паспорт-тренды игрока («это твой N-й случай слабой группы через переизбыток за месяц»). Рассмотреть при проектировании Фазы 4 (или как ретроактивное расширение Фазы 2): передавать в LLM-промпт релевантные агрегаты паспорта для конкретного игрока, чтобы объяснения были habit-aware, а не только per-game.

## Decisions log

- 2026-08-03 — Выбор стека: Electron+TS frontend / Python backend, two-process sidecar-архитектура. → `docs/ARCHITECTURE.md`
- 2026-08-03 — UI-фреймворк фронтенда: Preact для всего фронтенда (не только доски). → `docs/ARCHITECTURE.md` § Frontend/UI
- 2026-08-03 — Plugin-контракт: framework-agnostic DOM/Custom Element, единый контракт для trusted/sandboxed режимов. → `docs/ARCHITECTURE.md` § Плагинная архитектура
- 2026-08-03 — Design-system стартер: Dark Mode (OLED) по умолчанию, Fira Code/Fira Sans, cool→hot ownership heatmap с numeric-фолбэком. → `docs/ARCHITECTURE.md` § UI/UX-принципы фронтенда
- 2026-08-03 — Введён постоянный workflow: git-ветки + `task_plan.md`/`findings.md`/`progress.md` для восстановления контекста между сессиями.
- 2026-08-04 — Frontend-стек Фазы 1 конкретизирован: SQLite/библиотека партий отложены до Фазы 4 (YAGNI); renderer делает HTTP/WS-запросы к backend напрямую (не через main-процесс); `uPlot` для winrate-графика; layout-вариант «доска доминирует, график во всю ширину снизу» (выбран визуально); `@sabaki/sgf`+`@sabaki/immutable-gametree` для SGF/дерева, `@sabaki/go-board` для позиции на доске (взятия автоматически), нативные пропы Shudan (`heatMap`/`lines`) для ownership/PV вместо кастомного оверлея. → `docs/superpowers/specs/2026-08-04-phase-1-frontend-design.md`
- 2026-08-04 — KataGo analysis config теперь явно задаёт `reportAnalysisWinratesAs = BLACK` (backend), иначе действует дефолт KataGo `SIDETOMOVE` — winrate/scoreLead меняли бы перспективу каждый ход, ломая frontend-график. Найдено и исправлено на финальном ревью frontend-ветки, подтверждено по исходникам KataGo. → `backend/src/baduk_backend/config/profile.py`
