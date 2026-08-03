# Baduk Assistant — Task Plan

Постоянный план проекта. Обновляется по ходу работы; читается в начале каждой сессии вместе с `findings.md` и `progress.md`.

## Постоянные правила (standing policies)

- **Git-ветки**: разработка каждой фазы/задачи ведётся в отдельной ветке, никогда не коммитим реализацию напрямую в `main`. Именование: `phase-N-<short-name>` для фаз roadmap ниже, `fix-<short-name>` для точечных правок. Перед началом работы — создать/переключиться на ветку и отметить задачу здесь как "in progress".
- **Восстановление контекста**: в конце каждой сессии — запись в `progress.md` (что сделано, что решено, что осталось открытым) и обновление статусов в этом файле. Новая сессия начинает с чтения этих трёх файлов, а не с расспросов заново.
- **Не начинать реализацию без явного запроса** — правило из `CLAUDE.md`: репозиторий на стадии «архитектура утверждена, реализация не начата», пока пользователь явно не попросит начать конкретную фазу.

## Где мы сейчас

Фаза 1 — **backend-часть готова** (ветка `phase-1-viewer-katago`, ещё не смёржена в `main`). Реализованы: sidecar-скелет + health-check (FastAPI, токен-аутентификация), `KataGoProfile` + шаблон `.cfg`, `EngineManager` (жизненный цикл процесса KataGo Analysis Engine, авто-restart, дренаж stdout/stderr), реальный integration-тест против локального KataGo пользователя (winrate/ownership/PV подтверждены). Financial-review пройден (7 Important-находок исправлены одним fix-wave, ре-ревью чистое). Frontend (Shudan/SGF/overlay-панели) — отдельный будущий план, ещё не начат.

## Roadmap (из `docs/ARCHITECTURE.md` → «Поэтапный MVP-roadmap»)

| # | Фаза | Статус |
|---|------|--------|
| 1 | SGF viewer + KataGo-анализ (без LLM) | **backend готов**, frontend не начат (ветка `phase-1-viewer-katago`) |
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
- [ ] Решить, что дальше с веткой `phase-1-viewer-katago`: смёржить в `main` или продолжать в ней же frontend-часть (`superpowers:finishing-a-development-branch` даст варианты).
- [ ] Написать implementation-план frontend-части Фазы 1 (board+SGF, затем IPC-клиент+overlay-панели+сквозная приёмка) — отдельный план(ы), пока не начат(ы).

## Будущие задачи (backlog)

- Проверить точечно совместимость нужных React-only библиотек (напр. shadcn/Radix) через `preact/compat`, если/когда они понадобятся во frontend-части Фазы 1 (см. `findings.md`).
- API-слой поверх EngineManager (следующая фаза работы над backend) должен явно закрыть два отложенных при финальном ревью пункта: пересинхронизация запрос/ответ после `TimeoutError` и блокировка от конкурентных `analyze()` — оба станут реальными багами, как только появятся конкурентные HTTP-запросы.
- Уточнить, почему `uv` пропал из PATH в части сессий (Task 1 использовал его успешно, поздние задачи — уже нет); README backend уже документирует рабочий fallback через `.venv` напрямую.
- Фаза 2 и далее — не начинать, пока Фаза 1 не завершена целиком (backend+frontend) и не проверена по критериям из `docs/ARCHITECTURE.md`.

## Decisions log

- 2026-08-03 — Выбор стека: Electron+TS frontend / Python backend, two-process sidecar-архитектура. → `docs/ARCHITECTURE.md`
- 2026-08-03 — UI-фреймворк фронтенда: Preact для всего фронтенда (не только доски). → `docs/ARCHITECTURE.md` § Frontend/UI
- 2026-08-03 — Plugin-контракт: framework-agnostic DOM/Custom Element, единый контракт для trusted/sandboxed режимов. → `docs/ARCHITECTURE.md` § Плагинная архитектура
- 2026-08-03 — Design-system стартер: Dark Mode (OLED) по умолчанию, Fira Code/Fira Sans, cool→hot ownership heatmap с numeric-фолбэком. → `docs/ARCHITECTURE.md` § UI/UX-принципы фронтенда
- 2026-08-03 — Введён постоянный workflow: git-ветки + `task_plan.md`/`findings.md`/`progress.md` для восстановления контекста между сессиями.
