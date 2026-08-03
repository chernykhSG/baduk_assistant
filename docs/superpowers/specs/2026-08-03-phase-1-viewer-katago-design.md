# Design: Фаза 1 — SGF viewer + KataGo-анализ (без LLM)

Дата: 2026-08-03
Статус: утверждён пользователем, готов к переходу в implementation-план
Ветка: `phase-1-viewer-katago`

## Контекст

Архитектура проекта Baduk Assistant полностью спроектирована и утверждена (`docs/ARCHITECTURE.md`): two-process приложение — Electron/TypeScript фронтенд + Python backend-сервис (sidecar), связанные локальным HTTP+WebSocket API. Фаза 1 — первая фаза поэтапного MVP-roadmap: SGF-вьюер с рендерингом доски и визуализацией KataGo-анализа (winrate/ownership/PV), без LLM/RAG/паспорта игрока/плагинов — они в последующих фазах.

До этого документа не были зафиксированы конкретные технические решения внутри уже заданных рамок (Electron+TS/Preact, Python backend, SQLite): библиотека доски, пакетные менеджеры, тестовые фреймворки, инструмент сборки Electron, и — специфично для этой машины — пути к уже имеющимся у пользователя KataGo-бинарнику и модели. Этот спек фиксирует все эти решения и подход к реализации Фазы 1, прежде чем переходить к implementation-плану.

## Зафиксированные решения

| Решение | Выбор | Обоснование |
|---|---|---|
| Библиотека доски | **Shudan** | Preact-компонент — нулевая цена интеграции с уже выбранным Preact-ядром фронтенда (см. `docs/ARCHITECTURE.md` § Frontend/UI и `findings.md`). WGo.js (framework-agnostic альтернатива) рассматривался, но выбор Shudan усиливает уже принятое обоснование выбора Preact, а не ослабляет его. |
| JS-пакетный менеджер | **pnpm** | Быстрее npm/yarn, экономит место, строгий режим зависимостей — подходит для Electron-проекта с native-зависимостями. |
| Python-тулинг | **uv** | Единый быстрый инструмент для venv+lockfile+установки пакетов, хорошо совместим с последующей сборкой в PyInstaller (`docs/ARCHITECTURE.md` § Упаковка). |
| Frontend-тесты | **Vitest** | Естественно сочетается с Vite-сборкой Electron-фронта, быстрый, хорошая TS-поддержка. |
| Backend-тесты | **pytest** | Стандарт для Python, без альтернатив не рассматривался. |
| Electron build-инструмент | **electron-vite** | Готовый шаблон main/preload/renderer на Vite с HMR, совместим с electron-builder (уже выбран в `docs/ARCHITECTURE.md` § Упаковка) — минимум ручной конфигурации. |
| KataGo-бинарник (dev/smoke-test) | `C:\Users\User\.katrain\katago-v1.16.0-opencl-windows-x64.exe` | Уже установлен локально (через KaTrain), GPU уже оттюнен (`opencltuning/` присутствует). |
| KataGo-модель (dev/smoke-test) | `C:\Users\User\.katrain\kata1-b28c512nbt-s12464049920-d5727206990.bin.gz` | Указана пользователем. |

Пути к KataGo-бинарнику/модели — специфичны для машины разработчика, не хардкодятся в исходном коде: читаются integration-тестами из `backend/tests/local_config.json` (git-ignored, не попадает в репозиторий; в репозитории — только `local_config.json.example` с пустыми полями-подсказками).

## Структура каталогов

```
baduk_assistant/
├── frontend/                    # Electron + TS + Preact (electron-vite, pnpm)
│   ├── electron.vite.config.ts
│   ├── package.json
│   ├── src/
│   │   ├── main/                # Electron main-процесс: окно, запуск backend-sidecar
│   │   ├── preload/             # contextBridge
│   │   └── renderer/            # Preact UI
│   │       ├── board/           # Shudan-обёртка + SGF-парсинг + дерево вариаций
│   │       ├── analysis/        # winrate-график, ownership heatmap, PV-оверлей
│   │       ├── ipc/client.ts    # HTTP+WS клиент к backend
│   │       └── theme/           # design tokens (CSS custom properties, см. ARCHITECTURE.md § UI/UX)
│   └── tests/                   # Vitest
├── backend/                     # Python (uv)
│   ├── pyproject.toml
│   ├── src/baduk_backend/
│   │   ├── main.py              # FastAPI-приложение, sidecar-старт (динамический порт + токен)
│   │   ├── engine_manager.py    # жизненный цикл процесса KataGo Analysis Engine
│   │   ├── api/                 # HTTP REST + WebSocket роуты
│   │   ├── db/                  # SQLite (app.db) — метаданные, кэш анализа
│   │   └── config/              # шаблон analysis_config.cfg + KataGo-профиль
│   └── tests/                   # pytest (unit + integration)
└── shared/schemas/               # JSON-схемы: analysis request/response, KataGo profile config
```

Соответствует «Критическим точкам для будущей реализации» из `docs/ARCHITECTURE.md` (backend/engine_manager.py, frontend/src/ipc/client.ts, shared/schemas/).

## Подход: vertical slice, IPC-контракт сначала

Вместо «сначала весь backend, потом весь frontend» — сначала тонкий работающий путь целиком, потом наращивание вглубь:

1. **Скелет sidecar/IPC.** Electron main-процесс поднимает Python-backend как sidecar-процесс; backend отдаёт health-check HTTP-эндпоинт и WS-echo; frontend читает динамический порт и токен аутентификации, которые backend печатает в stdout при старте. Цель — проверить сам механизм sidecar+IPC до появления какой-либо Go-специфичной логики.
2. **Engine Manager.** Оборачивает процесс KataGo Analysis Engine (используя локальный `katago-v1.16.0-opencl-windows-x64.exe` + `kata1-b28c512nbt-s12464049920-d5727206990.bin.gz`): генерирует `analysis_config.cfg` из шаблона + одного профиля, отправляет тестовую позицию по stdin, парсит JSON-ответ (moveInfos/rootInfo/ownership) из stdout. Это прямой аналог smoke-test-критерия Фазы 1 из `docs/ARCHITECTURE.md` § «Проверка», тестируется через pytest без HTTP-слоя.
3. **API поверх Engine Manager.** HTTP REST-эндпоинт принимает позицию (moves/rules/komi/boardSize), делегирует в Engine Manager, возвращает разобранный ответ; WebSocket стримит прогресс анализа.
4. **Board + SGF на фронте.** Shudan-обёртка рендерит доску; парсинг SGF (drag&drop загрузка); дерево вариаций; клавиатурная навигация (стрелки — шаг по дереву, согласно `docs/ARCHITECTURE.md` § UI/UX-принципы фронтенда). Тестируется на fixture-SGF независимо от backend.
5. **Overlay-панели анализа.** Winrate line-chart (несколько серий различаются стилем линии, не только цветом), ownership heatmap (cool→hot градиент + numeric-фолбэк по hover/клику + легенда), PV-стрелки — подключаются к IPC-клиенту, бьющему в реальный backend/Engine Manager из шага 3.
6. **Сквозная приёмка.** Открыть реальную партию (SGF), пройти по ходам, увидеть обновляющиеся live winrate/ownership от настоящего KataGo — второй критерий Фазы 1 из `docs/ARCHITECTURE.md` § «Проверка».

Шаги 2 и 4 логически независимы друг от друга и от шага 1 — можно вести параллельно, сходясь на шагах 3/5.

## Тестирование

- **Backend (pytest):**
  - Unit-тесты Engine Manager — с фейковым/стаб-процессом вместо реального katago.exe (быстро, детерминированно, без внешних зависимостей).
  - Один явный integration-тест (`@pytest.mark.integration`), который поднимает реальный `katago.exe` + модель и выполняет полный smoke-test (тестовая позиция → JSON-ответ). Пути читаются из `backend/tests/local_config.json` (см. выше) — окружение без этого файла (например, будущий CI) автоматически пропускает integration-тесты, не падает.
- **Frontend (Vitest):** SGF-парсинг, построение дерева вариаций, трансформация данных для overlay-панелей — как чистая логика без Electron-рантайма; компонентные тесты для overlay-рендеринга на fixture-данных.
- **Ручная E2E-проверка:** полный сценарий «открыть SGF → анализ → live winrate/ownership» проверяется вручную в собранном Electron-приложении — автоматизация Electron-E2E (например, Playwright) в Фазу 1 не входит (YAGNI, возможный кандидат для более поздней фазы).
- TDD — тесты пишутся до кода для unit-логики (Engine Manager, SGF-дерево, overlay-трансформы), согласно `superpowers:test-driven-development`.

## Обработка ошибок

- Падение процесса KataGo (ненулевой exit code / неожиданное закрытие stdout) → Engine Manager детектирует и перезапускает процесс; запрос, ожидавший ответа в момент падения, получает явную ошибку, а не зависает бесконечно.
- HTTP/WS-запрос без верного токена аутентификации → 401 на HTTP, отказ в установлении WS-соединения.
- Некорректный/повреждённый SGF-файл → видимое состояние ошибки в board-вьюере фронтенда (не тихий сбой, не пустой экран).

## Вне рамок Фазы 1 (явно)

LLM-объяснения, RAG, паспорт игрока, формализация плагинной системы, кросс-платформенная сборка — последующие фазы (2–6) по `docs/ARCHITECTURE.md`, не затрагиваются сейчас. Раздача KataGo конечным пользователям (загрузка/установка) — тоже позже; сейчас используются локальные пути пользователя исключительно для разработки и тестирования.

## Ссылки

- `docs/ARCHITECTURE.md` — полная утверждённая архитектура (стек, IPC-контракт, feature-extraction, плагины, UI/UX-принципы).
- `task_plan.md` — статус фаз, decisions log.
- `findings.md` — обоснования уже принятых решений (сравнение GUI/движков, UI-фреймворк, дизайн-система).
