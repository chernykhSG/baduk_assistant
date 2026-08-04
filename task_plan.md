# Baduk Assistant — Task Plan

Постоянный план проекта. Обновляется по ходу работы; читается в начале каждой сессии вместе с `findings.md` и `progress.md`.

## Постоянные правила (standing policies)

- **Git-ветки**: разработка каждой фазы/задачи ведётся в отдельной ветке, никогда не коммитим реализацию напрямую в `main`. Именование: `phase-N-<short-name>` для фаз roadmap ниже, `fix-<short-name>` для точечных правок. Перед началом работы — создать/переключиться на ветку и отметить задачу здесь как "in progress".
- **Восстановление контекста**: в конце каждой сессии — запись в `progress.md` (что сделано, что решено, что осталось открытым) и обновление статусов в этом файле. Новая сессия начинает с чтения этих трёх файлов, а не с расспросов заново.
- **Не начинать реализацию без явного запроса** — правило из `CLAUDE.md`: репозиторий на стадии «архитектура утверждена, реализация не начата», пока пользователь явно не попросит начать конкретную фазу.

## Где мы сейчас

Фаза 1 — **весь backend смёржен в `main`**, vertical-slice шаги 1–3 из дизайн-спека закрыты полностью:
- Sidecar-скелет + `EngineManager` (были в ветке `phase-1-viewer-katago`, удалена после мержа): health-check (FastAPI, токен-аутентификация), `KataGoProfile` + шаблон `.cfg`, `EngineManager` (жизненный цикл процесса KataGo Analysis Engine, авто-restart, дренаж stdout/stderr), реальный integration-тест против локального KataGo пользователя (winrate/ownership/PV подтверждены). Финальное ревью пройдено (7 Important-находок исправлены одним fix-wave).
- API-слой (был в ветке `phase-1-backend-api`, удалена после fast-forward мержа): `POST /api/analyze` + `WS /api/analyze/stream` поверх единственного `EngineManager`/`asyncio.Lock` в `app.state`. 5 задач + один fix-wave на 5 Important-находок финального ревью (KataGo error-response → типизированная ошибка вместо 500/обрыва WS; `TimeoutError`/`ValueError` теперь ловятся; non-ASCII токен больше не роняет auth; `EngineManager.stop()` теперь вызывается при выключении sidecar + temp `.cfg` подчищается; добавлен regression-тест на `asyncio.Lock`).

Следующий шаг — вернуться к frontend-части (`phase-1-frontend`, приостановлена, только Electron/board-scaffolding задел).

## Roadmap (из `docs/ARCHITECTURE.md` → «Поэтапный MVP-roadmap»)

| # | Фаза | Статус |
|---|------|--------|
| 1 | SGF viewer + KataGo-анализ (без LLM) | **backend полностью в `main`** (sidecar+EngineManager+API-слой); frontend начат, приостановлен (`phase-1-frontend`) |
| 2 | LLM-объяснения поверх KataGo (без RAG) | не начата |
| 3 | RAG-база знаний | не начата |
| 4 | Паспорт игрока | не начата |
| 5 | Формализация плагинной системы | не начата |
| 6 | Кросс-платформенная валидация | не начата |

Детали каждой фазы, критические файлы и критерии проверки — см. `docs/ARCHITECTURE.md` (разделы «Поэтапный MVP-roadmap» и «Проверка»).

## Текущие задачи (current tasks)

- [x] Уточнить (brainstorming) нерешённую конкретику Фазы 1 перед кодом — см. дизайн-спек `docs/superpowers/specs/2026-08-03-phase-1-viewer-katago-design.md`: Shudan, pnpm, uv, Vitest/pytest, electron-vite, локальные пути KataGo.
- [x] Детальный implementation-план backend-части Фазы 1 — `docs/superpowers/plans/2026-08-03-phase-1-backend-engine-manager.md`.
- [x] Реализация backend-плана (5 задач + финальное ревью), ветка `phase-1-viewer-katago`.
- [x] Backend-часть (sidecar+EngineManager) смёржена в `main`, ветка `phase-1-viewer-katago` удалена.
- [x] Начата frontend-часть (ветка `phase-1-frontend`) — приостановлена, обнаружен пробел (см. выше).
- [x] Brainstorming API-слоя — дизайн-спек `docs/superpowers/specs/2026-08-03-phase-1-backend-api-design.md` (ветка `phase-1-backend-api`).
- [x] Детальный implementation-план API-слоя — `docs/superpowers/plans/2026-08-03-phase-1-backend-api.md` (5 задач: Pydantic-схемы, drain-фикс EngineManager, `POST /api/analyze`+wiring, `WS /api/analyze/stream`, real-KataGo integration-тест через HTTP).
- [x] Выполнить план API-слоя через `subagent-driven-development` (5 задач + финальное ревью + один fix-wave, всё чисто).
- [x] Ветка `phase-1-backend-api` смёржена в `main` локально (fast-forward) через `superpowers:finishing-a-development-branch`, удалена.
- [x] Ветка `phase-1-frontend` перебазирована на текущий `main` (единственный старый коммит был устаревшей правкой `task_plan.md`, полностью перекрыт — rebase дал пустой коммит, автоматически отброшен git; ветка сейчас идентична `main`).
- [ ] Brainstorming frontend-части Фазы 1 — теперь с конкретными backend-интерфейсами (`POST /api/analyze`/`WS /api/analyze/stream`, форматы схем, токен-аутентификация) вместо гипотетических.

## Будущие задачи (backlog)

- Проверить точечно совместимость нужных React-only библиотек (напр. shadcn/Radix) через `preact/compat`, если/когда они понадобятся во frontend-части Фазы 1 (см. `findings.md`).
- Минорные находки API-слоя, осознанно отложены (см. историю ветки `phase-1-backend-api` в git-логе): дублирование полей `AnalyzeRequest`/`StreamAnalyzeRequest` (нет общего базового класса), WS-хендлер после закрытия клиентом не ловит `WebSocketDisconnect` (не воспроизводит проблему, просто необработанное исключение в логах), `turnNumbers` не ограничен сверху по длине, схемы без границ значений (`maxVisits`/`komi`/`boardXSize`/`boardYSize`), `main.py`'s `try/finally` не покрывает `_find_free_port()`/`print()` перед ним (не воспроизводит утечку процесса).
- Уточнить, почему `uv` пропал из PATH в части сессий (Task 1 использовал его успешно, поздние задачи — уже нет); README backend уже документирует рабочий fallback через `.venv` напрямую.
- Фаза 2 и далее — не начинать, пока Фаза 1 не завершена целиком (backend+frontend) и не проверена по критериям из `docs/ARCHITECTURE.md`.
- **Связь Фазы 2 ↔ Фазы 4 (миссия проекта — не потерять).** Миссия проекта: KataGo даёт объективный анализ, но ассистент должен учить через принципы рационального мышления и выявлять повторяющиеся ошибки/привычки, а не просто разбирать «лучший ход здесь» — чтобы игрок переносил понимание на новые, ранее не встречавшиеся позиции. Текущий дизайн это поддерживает (детекторы формализованы через структурные свойства позиции, а не память конкретных ходов; LLM по `§4` ARCHITECTURE.md интерпретирует находки через принципы/RAG, не переоценивает позицию; Player Passport — Фаза 4 — как раз хранит таксономию повторяющихся ошибок и тренд по времени). Но сейчас Фаза 2 (real-time объяснение партии) и Фаза 4 (накопленный паспорт) не связаны в дизайне — объяснение конкретной находки не подмешивает релевантные паспорт-тренды игрока («это твой N-й случай слабой группы через переизбыток за месяц»). Рассмотреть при проектировании Фазы 4 (или как ретроактивное расширение Фазы 2): передавать в LLM-промпт релевантные агрегаты паспорта для конкретного игрока, чтобы объяснения были habit-aware, а не только per-game.

## Decisions log

- 2026-08-03 — Выбор стека: Electron+TS frontend / Python backend, two-process sidecar-архитектура. → `docs/ARCHITECTURE.md`
- 2026-08-03 — UI-фреймворк фронтенда: Preact для всего фронтенда (не только доски). → `docs/ARCHITECTURE.md` § Frontend/UI
- 2026-08-03 — Plugin-контракт: framework-agnostic DOM/Custom Element, единый контракт для trusted/sandboxed режимов. → `docs/ARCHITECTURE.md` § Плагинная архитектура
- 2026-08-03 — Design-system стартер: Dark Mode (OLED) по умолчанию, Fira Code/Fira Sans, cool→hot ownership heatmap с numeric-фолбэком. → `docs/ARCHITECTURE.md` § UI/UX-принципы фронтенда
- 2026-08-03 — Введён постоянный workflow: git-ветки + `task_plan.md`/`findings.md`/`progress.md` для восстановления контекста между сессиями.
