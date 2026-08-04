# Design: Frontend Фазы 1 — доска+SGF, IPC-клиент, overlay-панели (шаги 4–6 vertical slice)

Дата: 2026-08-04
Статус: утверждён пользователем, готов к переходу в implementation-план
Ветка: `phase-1-frontend`

## Контекст

Backend Фазы 1 полностью реализован и смёржен в `main`: FastAPI sidecar печатает `{"port": N, "token": "..."}` в stdout при старте (`baduk_backend.main.run()`); `POST /api/analyze` (заголовок `X-Auth-Token`, тело `AnalyzeRequest`, ответ `AnalyzeResponse` — 401/502/503 на ошибки); `WS /api/analyze/stream?token=...` (вход `StreamAnalyzeRequest` с `turnNumbers`, сервер шлёт `progress`-сообщение на каждый завершённый ход, затем `done` или `error`+закрытие). Полные схемы — `backend/src/baduk_backend/api/schemas.py`.

Исходный дизайн-спек Фазы 1 (`docs/superpowers/specs/2026-08-03-phase-1-viewer-katago-design.md`) уже зафиксировал стек (Electron+TS+Preact, Shudan, pnpm, electron-vite, Vitest) и разбил работу на vertical-slice шаги; шаги 1–3 (backend) выполнены, шаги 4–6 (доска+SGF, overlay-панели+IPC, сквозная приёмка) — предмет этого документа. `ARCHITECTURE.md` уже зафиксировал design-tokens/dark-mode стартер (§ UI/UX-принципы фронтенда) и framework-agnostic DOM/Custom Element контракт для будущих плагинов (не затрагивается в Фазе 1).

Брейнсторминг для этой части был начат в предыдущей сессии и прерван обнаружением пробела в backend (отсутствие HTTP/WS API-слоя) — пробел закрыт, брейнсторминг продолжен в этой сессии с уже конкретными backend-интерфейсами вместо гипотетических.

## Зафиксированные решения

| Решение | Выбор | Обоснование |
|---|---|---|
| Библиотека партий/SQLite в Фазе 1 | **Отложить** | Критерий приёмки Фазы 1 — просто «открыть SGF → увидеть дерево+доску» и «live winrate/ownership»; персистентность не тестируется до Фазы 4 (Player Passport), где появится реальный потребитель. SGF открывается заново через drag&drop каждую сессию. |
| Владелец IPC-вызовов | **Renderer делает запросы напрямую** | Preload/contextBridge отдаёт только `{port, token}`; `fetch()`/`WebSocket()` — в renderer'е. Простой стандартный Electron-паттерн, соответствует уже описанному в `ARCHITECTURE.md` месту `frontend/src/ipc/client.ts`. Проксирование всех запросов через main добавило бы дублирующий слой (особенно для WS-стрима) ради модели угроз, которая не актуальна в Фазе 1 (нет стороннего/удалённого кода в renderer'е). |
| Charting-библиотека | **uPlot** | ~45KB, canvas-based, framework-agnostic, быстрый на живых обновлениях по WS-прогрессу. Простой императивный API, легко обернуть в Preact-компонент без `preact/compat`. |
| Layout | **Вариант B: доска доминирует, график во всю ширину снизу** | Дерево — узкая сворачиваемая полоса слева, доска занимает почти всё доступное место, winrate/score-lead график растянут по горизонтали на всю ширину снизу — лучше видно, на каком ходу упал winrate, особенно на длинных партиях. Выбран пользователем визуально из 3 вариантов (mockup-сессия). |
| SGF-парсинг | **`@sabaki/sgf`** | Зрелая, широко используемая в Go-экосистеме библиотека того же автора, что и Sabaki (уже фигурировал при сравнении опенсорсных решений в `ARCHITECTURE.md`). |
| Модель дерева вариаций | **`@sabaki/immutable-gametree`** | Компаньон-библиотека `@sabaki/sgf`, иммутабельное дерево со structural sharing — не пишем свою модель дерева с нуля, связка уже проверена в реальном используемом софте. |
| Ownership heatmap / PV-стрелки | **Нативные пропы Shudan (`heatMap`, `lines`/`markerMap`)**, не свой SVG-слой | Shudan спроектирован именно для этого — меньше кастомного кода. Точные имена пропов сверяются с текущей версией библиотеки на этапе реализации. |
| Состояние приложения | **`@preact/signals`** | Уже выбрано в `ARCHITECTURE.md` под потоковые данные (WS-прогресс анализа). |

## Архитектура: структура каталогов

Без изменений относительно исходного дизайн-спека Фазы 1:

```
frontend/
├── electron.vite.config.ts
├── package.json
├── src/
│   ├── main/                # Electron main: окно, spawn backend-sidecar, парсинг stdout {port,token}
│   ├── preload/              # contextBridge: window.baduk.getBackendConnection()
│   └── renderer/             # Preact UI
│       ├── board/            # Shudan-обёртка + SGF-парсинг + дерево вариаций
│       ├── analysis/         # winrate-график (uPlot), ownership heatmap, PV-оверлей
│       ├── ipc/client.ts     # HTTP+WS клиент к backend (типы зеркалируют backend/api/schemas.py)
│       └── theme/            # design tokens (CSS custom properties)
└── tests/                    # Vitest
```

**Явно вне рамок этого документа**: Settings UI, SQLite/библиотека партий, LLM-панель, Player Passport UI, формализация Frontend Plugin Host — не нужны для критерия приёмки Фазы 1 либо зависят от ещё не реализованных backend-возможностей (переключение KataGo-профилей, паспорт).

## IPC-клиент

- **Main → renderer передача port+token**: main спавнит sidecar (`baduk-backend`), парсит первую строку stdout как JSON `{"port": N, "token": "..."}`, хранит в памяти main-процесса (внутренний pending-promise, если sidecar ещё не отрапортовал). Preload экспонирует через `contextBridge`:
  ```ts
  // preload
  contextBridge.exposeInMainWorld('baduk', {
    getBackendConnection: () => ipcRenderer.invoke('backend:get-connection'),
  });
  ```
  ```ts
  // main
  ipcMain.handle('backend:get-connection', () => backendConnectionPromise);
  // backendConnectionPromise резолвится при парсинге строки stdout,
  // реджектится, если процесс завершился раньше, чем успел её напечатать.
  ```
- **`frontend/src/ipc/client.ts`** (renderer) — тонкая типизированная обёртка, без бизнес-логики:
  ```ts
  interface AnalyzeRequest {
    moves: string[][];
    rules: string;
    komi: number;
    boardXSize: number;
    boardYSize: number;
    analyzeTurns: [number];       // ровно один элемент — ограничение EngineManager
    maxVisits: number;
    includeOwnership: boolean;
  }
  interface MoveInfo { move: string; winrate: number; scoreLead: number; visits: number; prior: number; pv: string[] }
  interface RootInfo { winrate: number; scoreLead: number; visits: number }
  interface AnalyzeResponse {
    id: string;
    turnNumber?: number;
    moveInfos: MoveInfo[];
    rootInfo: RootInfo;
    ownership?: number[];
  }
  interface StreamAnalyzeRequest extends Omit<AnalyzeRequest, 'analyzeTurns'> { turnNumbers: number[] }
  type ProgressMessage = { type: 'progress'; turnNumber: number; total: number; result: AnalyzeResponse };
  type DoneMessage = { type: 'done' };
  type ErrorMessage = { type: 'error'; detail: string };

  async function analyzePosition(request: AnalyzeRequest): Promise<AnalyzeResponse>;
  function streamAnalysis(
    request: StreamAnalyzeRequest,
    handlers: { onProgress(msg: ProgressMessage): void; onDone(): void; onError(msg: ErrorMessage): void }
  ): () => void;  // возвращает функцию закрытия WS
  ```
  Типы вручную написаны как TS-интерфейсы, зеркалящие `backend/src/baduk_backend/api/schemas.py` 1:1 — то же решение, что и на backend (`shared/schemas/` — спекуляция без второго потребителя, откладывается, см. `docs/superpowers/specs/2026-08-03-phase-1-backend-api-design.md`). `X-Auth-Token`/`?token=` берутся из `getBackendConnection()`, вызывается один раз при старте рендерера, кешируется в модуле `ipc/client.ts`.

## Доска + SGF

- `board/sgfLoader.ts` — drag&drop файла → `@sabaki/sgf` парсинг → `@sabaki/immutable-gametree` дерево. Чистая функция, тестируется на fixture-SGF без Electron-рантайма. Некорректный/повреждённый SGF → явная ошибка, обрабатываемая выше по стеку как видимое состояние ошибки (не тихий сбой).
- `board/BoardView.tsx` — обёртка над Shudan; принимает текущую позицию (камни, вычисленные проигрыванием ходов от корня дерева до текущего узла — чистая функция от `(tree, nodeId)`) + `heatMap`/`lines` пропы для overlay-данных.
- `board/VariationTree.tsx` — рендер дерева вариаций, клавиатурная навигация (стрелки — шаг по текущей ветке, зафиксировано в `ARCHITECTURE.md` § UI/UX-принципы фронтенда).

## Overlay-панели и состояние

- **Ownership heatmap / PV-стрелки** — нативные пропы Shudan (`heatMap`: конверсия плоского `ownership[]` от KataGo в 2D-сетку; `lines`/`markerMap`: PV как соединённые стрелки между координатами хода). Числовой фолбэк по hover — свой обработчик через Shudan's per-vertex mouse events, точное значение рядом с курсором (accessibility-требование из дизайн-ревью, см. `findings.md`).
- **`analysis/WinrateChart.tsx`** — uPlot-инстанс в `useEffect`, обновляется через `setData()` по мере прихода `progress`-сообщений (append, не пересоздание инстанса).
- **Состояние — `@preact/signals`**:
  - `currentTree`, `currentNodeId` — дерево партии и текущий узел.
  - `analysisByTurn: Signal<Map<number, AnalyzeResponse>>` — заполняется по ходу WS-стрима.
  - `streamStatus: Signal<'idle' | 'streaming' | 'done' | 'error'>`.
  - derived: `currentBoardPosition` (камни из `tree`+`nodeId`), `currentMoveAnalysis` (анализ текущего хода из `analysisByTurn`, если уже пришёл).
- **Порядок вызовов**: при загрузке SGF сразу стартует `streamAnalysis` на все ходы партии (`turnNumbers = [0..N]`) — доска/heatmap/график реактивно оживают по мере прихода прогресса, даже до того как пользователь долистает до этого хода (критерий приёмки Фазы 1). `analyzePosition` (`POST /api/analyze`) — точечно, когда пользователь создаёт новый вариант вне исходного SGF (ещё не покрыт стримом).

## Layout (вариант B)

```
AppShell
├── ConnectionGate           # ждёт getBackendConnection(); при ошибке — экран ошибки
└── (после подключения)
    ├── row 1: [VariationTreeRail (узкая, сворачиваемая) | BoardView (доминирует)]
    └── row 2: WinrateChart (full-width strip, снизу)
```
CSS Grid, design tokens из `theme/` (dark-mode стартер, `ARCHITECTURE.md` § UI/UX-принципы фронтенда).

## Обработка ошибок

- Sidecar не запустился/упал до печати `{port,token}` → main реджектит promise → `ConnectionGate` показывает явный экран ошибки, без встроенной кнопки reconnect — пользователь перезапускает приложение (YAGNI для Фазы 1, автоматический reconnect sidecar'а — не критерий приёмки).
- Некорректный SGF → видимое состояние ошибки в `BoardView`.
- `POST /api/analyze` → 502/503 (KataGo упал/затаймаутил) — inline-баннер рядом с графиком/доской, не роняет приложение целиком (backend сам перезапускает KataGo — повтор может сработать). 401 трактуется как фатальная ошибка подключения (тот же экран, что и провал sidecar — означает рассинхрон токена).
- WS-стрим: `{"type":"error"}` или разрыв → `streamStatus.value = 'error'`, inline-баннер с кнопкой "повторить" — заново стартует `streamAnalysis` на все ходы (без partial-resume — YAGNI для Фазы 1).

## Тестирование

- Vitest, jsdom-окружение (из коробки в electron-vite), `@testing-library/preact` для компонентных тестов.
- Чистая логика (TDD-first, как зафиксировано в исходном спеке): `sgfLoader.ts` на fixture-SGF, навигация по дереву (переходы `currentNodeId` по стрелкам), `ipc/client.ts` построение запросов (мокнутые `fetch`/`WebSocket`), трансформация `ownership[]` → 2D `heatMap`.
- Компонентные тесты: `BoardView` рендерит верные камни для фикстур-позиции; `WinrateChart` корректно накапливает данные по последовательности `progress`-сообщений.
- Ручная сквозная приёмка в собранном Electron-приложении — автоматизация (Playwright) не входит в Фазу 1 (решено в исходном спеке, без изменений).

## Вне рамок этого документа (явно)

Settings UI, SQLite/библиотека партий (отложено до Фазы 4), LLM-объяснения (Фаза 2), RAG (Фаза 3), Player Passport (Фаза 4), формализация Frontend Plugin Host (Фаза 5), кросс-платформенная сборка (Фаза 6).

## Ссылки

- `docs/superpowers/specs/2026-08-03-phase-1-viewer-katago-design.md` — исходный дизайн-спек всей Фазы 1 (стек, vertical-slice шаги 1–6).
- `docs/superpowers/specs/2026-08-03-phase-1-backend-api-design.md` — дизайн-спек backend API-слоя (протокол, который потребляет этот frontend).
- `backend/src/baduk_backend/api/schemas.py` — источник истины для TS-типов IPC-клиента.
- `docs/ARCHITECTURE.md` — общая архитектура (стек, design tokens, плагинный контракт).
- `task_plan.md` — backlog-пункт о связи Фазы 2↔Фазы 4 (habit-aware объяснения) — не затрагивается этим документом, зафиксирован отдельно.
