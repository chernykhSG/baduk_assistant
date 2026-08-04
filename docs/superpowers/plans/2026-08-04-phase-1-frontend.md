# Frontend Фазы 1 (доска+SGF, IPC-клиент, overlay-панели) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать frontend-часть Фазы 1 (шаги 4–6 vertical slice): Electron+Preact-приложение, которое открывает SGF, показывает доску и дерево вариаций, стримит реальный анализ KataGo через уже готовый backend и визуализирует winrate/ownership/PV.

**Architecture:** Electron main спавнит backend-sidecar и передаёт `{port, token}` в renderer через `contextBridge`. Renderer сам делает HTTP/WS-запросы к backend (`fetch`/`WebSocket`), без прокси через main. Состояние — `@preact/signals`: дерево партии, текущий узел, накопленный по ходам анализ. Доска — `@sabaki/shudan`, позиция вычисляется через `@sabaki/go-board` (обрабатывает взятия автоматически), SGF/дерево — `@sabaki/sgf` + `@sabaki/immutable-gametree`, график — `uPlot`.

**Tech Stack:** Electron + TypeScript + Preact, `electron-vite` (сборка), `pnpm`, Vitest + `@testing-library/preact` (тесты), `@sabaki/sgf` + `@sabaki/immutable-gametree` + `@sabaki/go-board` + `@sabaki/shudan` (SGF/дерево/доска), `uPlot` (график), `@preact/signals` (состояние).

## Global Constraints

- Renderer делает HTTP/WS-запросы к backend напрямую; preload/`contextBridge` отдаёт только `{port, token}` через `window.baduk.getBackendConnection()`.
- TS-типы IPC-запросов/ответов зеркалируют `backend/src/baduk_backend/api/schemas.py` 1:1, без `shared/schemas/` (та же логика, что и на backend — см. `docs/superpowers/specs/2026-08-03-phase-1-backend-api-design.md`).
- `EngineManager.analyze()` читает ровно одну строку ответа на запрос — `AnalyzeRequest.analyzeTurns` всегда массив длины 1; `POST /api/analyze` — 401/502/503 на ошибки (см. `backend/src/baduk_backend/api/analysis.py`).
- Никаких хардкод-путей к машинно-специфичным ресурсам (это уже установленное правило проекта из `CLAUDE.md`) — команда запуска backend-sidecar берётся из `BADUK_BACKEND_COMMAND` (опционально, дефолт — бинарник `baduk-backend` из `PATH`, что работает при активированном backend-venv).
- SQLite/библиотека партий — вне рамок (отложено до Фазы 4). Settings UI, LLM-панель, Player Passport, формализация Plugin Host — вне рамок.
- Прямоугольные доски (SGF `SZ=W:H`) — не поддерживаются в Фазе 1, явная ошибка вместо тихого некорректного рендера.
- Тестирование — Vitest, jsdom-окружение, `@testing-library/preact` для компонентных тестов; чистая логика тестируется без Electron-рантайма (TDD-first).
- Ручная сквозная приёмка в собранном Electron-приложении — Playwright/автоматизация E2E не входит в Фазу 1.

---

## File Structure

```
frontend/
├── electron.vite.config.ts
├── package.json
├── vitest.config.ts
├── src/
│   ├── main/
│   │   ├── index.ts                       # Electron main entry (создаётся scaffold'ом, дополняется)
│   │   └── backendConnection.ts           # NEW — spawn sidecar, парсинг {port,token}
│   ├── preload/
│   │   └── index.ts                        # дополняется: contextBridge
│   └── renderer/
│       ├── index.html
│       └── src/
│           ├── main.tsx                    # bootstrap (создаётся scaffold'ом, дополняется)
│           ├── App.tsx                     # AppShell — layout, ConnectionGate, SGF loading
│           ├── global.d.ts                 # NEW — типы window.baduk
│           ├── ipc/
│           │   └── client.ts               # NEW — типы + analyzePosition/streamAnalysis
│           ├── state/
│           │   └── appState.ts             # NEW — @preact/signals состояние
│           ├── board/
│           │   ├── sgfLoader.ts            # NEW — парсинг SGF → GameTree, movesFromRootToNode
│           │   ├── gameRequestBuilder.ts   # NEW — GameTree → AnalyzeRequest/StreamAnalyzeRequest
│           │   ├── boardPosition.ts        # NEW — GameTree → signMap (через @sabaki/go-board)
│           │   ├── BoardView.tsx           # NEW — обёртка Shudan + heatMap/lines
│           │   └── VariationTree.tsx       # NEW — дерево вариаций + клавиатурная навигация
│           └── analysis/
│               └── WinrateChart.tsx        # NEW — uPlot winrate/score-lead график
└── tests/
    ├── fixtures/
    │   ├── simple-game.sgf
    │   └── backend/
    │       ├── fake-backend.mjs
    │       └── fake-backend-crash.mjs
    ├── main/
    │   └── backendConnection.test.ts
    └── renderer/
        ├── ipc/client.test.ts
        ├── board/sgfLoader.test.ts
        ├── board/gameRequestBuilder.test.ts
        ├── board/boardPosition.test.ts
        ├── state/appState.test.ts
        └── components/
            ├── BoardView.test.tsx
            ├── VariationTree.test.tsx
            └── WinrateChart.test.tsx
```

---

### Task 1: Scaffold — electron-vite + Preact + TypeScript + Vitest

**Files:**
- Create: `frontend/` (весь проект через scaffold-команду)
- Modify: `frontend/electron.vite.config.ts`
- Modify: renderer tsconfig (jsx-настройки — какой именно файл, см. Step 5)
- Create: `frontend/vitest.config.ts`
- Test: `frontend/tests/sanity.test.tsx`

**Interfaces:**
- Produces: рабочий toolchain (`pnpm install`, `pnpm exec vitest run`, `pnpm exec electron-vite dev` все работают) — все последующие задачи полагаются на то, что Preact+TS+Vitest уже настроены и компилируются.

- [ ] **Step 1: Scaffold проекта**

Из корня репозитория:

```bash
pnpm create @quick-start/electron@latest frontend -- --template vanilla-ts
cd frontend
pnpm install
```

`vanilla-ts` — без React/Vue-специфичного кода, который пришлось бы вырезать (Preact-шаблона у `@quick-start/electron` нет).

- [ ] **Step 2: Установить Preact + сборочный плагин**

```bash
pnpm add preact @preact/signals
pnpm add -D @preact/preset-vite
```

- [ ] **Step 3: Подключить Preact-плагин в `electron.vite.config.ts`**

Найти блок `renderer: { ... plugins: [...] }` (сгенерирован scaffold'ом) и добавить `preact()`:

```ts
import preact from '@preact/preset-vite'
// ...внутри renderer: { plugins: [preact()], ... }
```

- [ ] **Step 4: Написать `frontend/vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config'
import preact from '@preact/preset-vite'
import path from 'node:path'

export default defineConfig({
  plugins: [preact()],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.{ts,tsx}'],
  },
  resolve: {
    alias: {
      '@renderer': path.resolve(__dirname, 'src/renderer/src'),
    },
  },
})
```

```bash
pnpm add -D vitest @testing-library/preact jsdom @testing-library/jest-dom
```

- [ ] **Step 5: Настроить JSX для Preact в TypeScript**

Scaffold `vanilla-ts` генерирует конфиг(и) TypeScript для renderer-исходников — обычно `tsconfig.web.json` в корне `frontend/` (общий паттерн electron-vite для vanilla/react/vue-ts шаблонов). Открыть его (если файл называется иначе — применить те же настройки к тому файлу, который `include`-ит `src/renderer/**`) и убедиться, что в `compilerOptions` стоит:

```json
{
  "compilerOptions": {
    "jsx": "react-jsx",
    "jsxImportSource": "preact"
  }
}
```

- [ ] **Step 6: Написать sanity-тест**

`frontend/tests/sanity.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/preact'

function Hello() {
  return <p>hello baduk</p>
}

describe('toolchain sanity', () => {
  it('renders a Preact component under Vitest+jsdom', () => {
    const { getByText } = render(<Hello />)
    expect(getByText('hello baduk')).toBeTruthy()
  })
})
```

- [ ] **Step 7: Запустить тест, убедиться, что проходит**

Run (из `frontend/`): `pnpm exec vitest run`
Expected: PASS (1 passed) — подтверждает, что JSX/Preact/jsdom работают вместе.

- [ ] **Step 8: Убедиться, что дев-сборка стартует**

Run: `pnpm exec electron-vite dev`
Expected: открывается пустое Electron-окно без ошибок в консоли main/renderer. Остановить процесс (Ctrl+C) после проверки — это не автоматизированный тест, а ручная проверка тулчейна.

- [ ] **Step 9: Commit**

```bash
git add frontend/
git commit -m "chore: scaffold Electron+Preact+TS frontend with Vitest"
```

---

### Task 2: Backend-подключение (main спавн + preload bridge)

**Files:**
- Create: `frontend/src/main/backendConnection.ts`
- Modify: `frontend/src/main/index.ts`
- Modify: `frontend/src/preload/index.ts`
- Create: `frontend/src/renderer/src/global.d.ts`
- Test: `frontend/tests/main/backendConnection.test.ts`
- Test fixtures: `frontend/tests/fixtures/backend/fake-backend.mjs`, `frontend/tests/fixtures/backend/fake-backend-crash.mjs`

**Interfaces:**
- Produces: `startBackend(command?: string): Promise<{ port: number; token: string }>` (из `backendConnection.ts`), IPC-канал `backend:get-connection`, `window.baduk.getBackendConnection(): Promise<{port, token}>` (глобальный тип в `global.d.ts`, реально экспонирован через preload) — используется в Task 4 (`ipc/client.ts`).

- [ ] **Step 1: Написать фейковые backend-фикстуры**

`frontend/tests/fixtures/backend/fake-backend.mjs`:

```js
console.log(JSON.stringify({ port: 54321, token: 'fake-token' }))
setInterval(() => {}, 1000) // держим процесс живым, как настоящий sidecar
```

`frontend/tests/fixtures/backend/fake-backend-crash.mjs`:

```js
process.exit(1)
```

- [ ] **Step 2: Написать падающий тест**

`frontend/tests/main/backendConnection.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { startBackend } from '../../src/main/backendConnection'

const fixturesDir = path.join(path.dirname(fileURLToPath(import.meta.url)), '../fixtures/backend')

describe('startBackend', () => {
  it('resolves with port and token parsed from the first JSON stdout line', async () => {
    const command = `node "${path.join(fixturesDir, 'fake-backend.mjs')}"`
    const connection = await startBackend(command)
    expect(connection).toEqual({ port: 54321, token: 'fake-token' })
  })

  it('rejects if the process exits before printing a connection line', async () => {
    const command = `node "${path.join(fixturesDir, 'fake-backend-crash.mjs')}"`
    await expect(startBackend(command)).rejects.toThrow(/exited with code 1/)
  })
})
```

- [ ] **Step 3: Запустить тест, убедиться, что падает**

Run: `pnpm exec vitest run tests/main/backendConnection.test.ts`
Expected: FAIL — `startBackend` ещё не существует (`Cannot find module`).

- [ ] **Step 4: Реализовать `backendConnection.ts`**

```ts
import { spawn, type ChildProcess } from 'node:child_process'
import * as readline from 'node:readline'

export interface BackendConnection {
  port: number
  token: string
}

export function startBackend(
  command: string = process.env.BADUK_BACKEND_COMMAND ?? 'baduk-backend'
): Promise<BackendConnection> {
  return new Promise((resolve, reject) => {
    const child: ChildProcess = spawn(command, [], { shell: true })
    let settled = false

    if (!child.stdout) {
      reject(new Error('Backend process has no stdout stream'))
      return
    }

    const rl = readline.createInterface({ input: child.stdout })

    rl.on('line', (line) => {
      if (settled) return
      try {
        const parsed = JSON.parse(line)
        if (typeof parsed.port === 'number' && typeof parsed.token === 'string') {
          settled = true
          rl.close()
          resolve({ port: parsed.port, token: parsed.token })
        }
      } catch {
        // строка до старт-сообщения (backend может логировать что-то ещё раньше) — игнорируем
      }
    })

    child.on('exit', (code) => {
      if (!settled) {
        settled = true
        reject(new Error(`Backend process exited with code ${code} before reporting a connection`))
      }
    })

    child.on('error', (err) => {
      if (!settled) {
        settled = true
        reject(err)
      }
    })
  })
}
```

- [ ] **Step 5: Запустить тест, убедиться, что проходит**

Run: `pnpm exec vitest run tests/main/backendConnection.test.ts`
Expected: PASS (2 passed)

- [ ] **Step 6: Подключить в `frontend/src/main/index.ts`**

Добавить к уже сгенерированному scaffold'ом содержимому (обычно там уже есть `app.whenReady().then(() => { createWindow() })` — не удалять существующую логику окна, добавить рядом):

```ts
import { ipcMain } from 'electron'
import { startBackend, type BackendConnection } from './backendConnection'

let backendConnectionPromise: Promise<BackendConnection> | null = null

function getBackendConnection(): Promise<BackendConnection> {
  if (!backendConnectionPromise) {
    backendConnectionPromise = startBackend()
  }
  return backendConnectionPromise
}

ipcMain.handle('backend:get-connection', () => getBackendConnection())
```

- [ ] **Step 7: Экспонировать через preload**

В `frontend/src/preload/index.ts` (дополнить, не заменять существующий `electronAPI`-boilerplate, если он есть):

```ts
import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('baduk', {
  getBackendConnection: () => ipcRenderer.invoke('backend:get-connection'),
})
```

- [ ] **Step 8: Типы для renderer**

`frontend/src/renderer/src/global.d.ts`:

```ts
export interface BackendConnection {
  port: number
  token: string
}

declare global {
  interface Window {
    baduk: {
      getBackendConnection(): Promise<BackendConnection>
    }
  }
}
```

- [ ] **Step 9: Запустить полный набор тестов**

Run: `pnpm exec vitest run`
Expected: PASS (все тесты, включая Task 1's sanity-тест)

- [ ] **Step 10: Commit**

```bash
git add frontend/src/main frontend/src/preload frontend/src/renderer/src/global.d.ts frontend/tests/main frontend/tests/fixtures/backend
git commit -m "feat: spawn backend sidecar from main and expose connection via preload"
```

---

### Task 3: SGF-парсинг + дерево вариаций

**Files:**
- Create: `frontend/src/renderer/src/board/sgfLoader.ts`
- Test: `frontend/tests/renderer/board/sgfLoader.test.ts`
- Test fixture: `frontend/tests/fixtures/simple-game.sgf`

**Interfaces:**
- Produces: `parseSgf(content: string): GameTree`, `class SgfParseError extends Error`, `getBoardSize(tree: GameTree): number`, `findMainLineLeaf(tree: GameTree): NodeObject`, `movesFromRootToNode(tree: GameTree, nodeId: number): { color: 'B' | 'W'; sgfCoord: string | null }[]` (`sgfCoord: null` — пропуск хода). Используется в Task 5 (`gameRequestBuilder.ts`), Task 6 (`boardPosition.ts`), Task 9 (`VariationTree.tsx`).

- [ ] **Step 1: Установить зависимости**

```bash
pnpm add @sabaki/sgf @sabaki/immutable-gametree
```

- [ ] **Step 2: Создать fixture-SGF**

`frontend/tests/fixtures/simple-game.sgf`:

```
(;GM[1]FF[4]SZ[19]KM[7.5]RU[Chinese];B[qd];W[dc];B[oq])
```

Три хода: B на `qd`, W на `dc`, B на `oq` (SGF-координаты, 19×19, комі 7.5, правила Chinese).

- [ ] **Step 3: Написать падающий тест**

`frontend/tests/renderer/board/sgfLoader.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseSgf, SgfParseError, getBoardSize, findMainLineLeaf, movesFromRootToNode } from '@renderer/board/sgfLoader'

const fixturePath = path.join(path.dirname(fileURLToPath(import.meta.url)), '../../fixtures/simple-game.sgf')
const fixtureContent = fs.readFileSync(fixturePath, 'utf-8')

describe('parseSgf', () => {
  it('parses a valid SGF into a GameTree with the expected root properties', () => {
    const tree = parseSgf(fixtureContent)
    expect(tree.root.data.SZ).toEqual(['19'])
    expect(tree.root.data.KM).toEqual(['7.5'])
    expect(tree.root.children.length).toBe(1)
  })

  it('throws SgfParseError on malformed content', () => {
    expect(() => parseSgf('not valid sgf (((')).toThrow(SgfParseError)
  })

  it('throws SgfParseError when the file has no game trees', () => {
    expect(() => parseSgf('')).toThrow(SgfParseError)
  })
})

describe('getBoardSize', () => {
  it('reads SZ from the root node', () => {
    const tree = parseSgf(fixtureContent)
    expect(getBoardSize(tree)).toBe(19)
  })

  it('defaults to 19 when SZ is absent', () => {
    const tree = parseSgf('(;GM[1]FF[4];B[qd])')
    expect(getBoardSize(tree)).toBe(19)
  })

  it('throws on rectangular boards', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[19:13];B[qd])')
    expect(() => getBoardSize(tree)).toThrow(/Rectangular boards/)
  })
})

describe('findMainLineLeaf + movesFromRootToNode', () => {
  it('walks the first-child line to the final leaf and lists moves in SGF coordinates', () => {
    const tree = parseSgf(fixtureContent)
    const leaf = findMainLineLeaf(tree)
    const moves = movesFromRootToNode(tree, leaf.id)
    expect(moves).toEqual([
      { color: 'B', sgfCoord: 'qd' },
      { color: 'W', sgfCoord: 'dc' },
      { color: 'B', sgfCoord: 'oq' },
    ])
  })

  it('returns an empty list for the root node itself', () => {
    const tree = parseSgf(fixtureContent)
    expect(movesFromRootToNode(tree, tree.root.id)).toEqual([])
  })
})
```

- [ ] **Step 4: Запустить тест, убедиться, что падает**

Run: `pnpm exec vitest run tests/renderer/board/sgfLoader.test.ts`
Expected: FAIL — модуль `sgfLoader` не существует.

- [ ] **Step 5: Реализовать `sgfLoader.ts`**

```ts
import * as sgf from '@sabaki/sgf'
import GameTree from '@sabaki/immutable-gametree'

export class SgfParseError extends Error {}

let idCounter = 0
function getId(): number {
  return idCounter++
}

export function parseSgf(content: string): GameTree {
  idCounter = 0
  let rootNodes: any[]
  try {
    rootNodes = sgf.parse(content, { getId })
  } catch (err) {
    throw new SgfParseError(`Failed to parse SGF: ${(err as Error).message}`)
  }
  if (!rootNodes || rootNodes.length === 0) {
    throw new SgfParseError('SGF content contains no game trees')
  }
  return new GameTree({ getId, root: rootNodes[0] })
}

export function getBoardSize(tree: GameTree): number {
  const szValue = tree.root.data.SZ?.[0]
  if (!szValue) return 19
  if (szValue.includes(':')) {
    throw new Error(`Rectangular boards (SZ=${szValue}) are not supported in Phase 1`)
  }
  return parseInt(szValue, 10)
}

export function findMainLineLeaf(tree: GameTree): any {
  let node = tree.root
  while (node.children.length > 0) {
    node = node.children[0]
  }
  return node
}

export function movesFromRootToNode(
  tree: GameTree,
  nodeId: number
): { color: 'B' | 'W'; sgfCoord: string | null }[] {
  const path: any[] = []
  let current = tree.get(nodeId)
  while (current) {
    path.unshift(current)
    current = current.parentId === null || current.parentId === undefined ? null : tree.get(current.parentId)
  }

  const moves: { color: 'B' | 'W'; sgfCoord: string | null }[] = []
  for (const node of path) {
    if (node.data.B) moves.push({ color: 'B', sgfCoord: node.data.B[0] || null })
    else if (node.data.W) moves.push({ color: 'W', sgfCoord: node.data.W[0] || null })
  }
  return moves
}
```

- [ ] **Step 6: Запустить тест, убедиться, что проходит**

Run: `pnpm exec vitest run tests/renderer/board/sgfLoader.test.ts`
Expected: PASS (7 passed)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/renderer/src/board/sgfLoader.ts frontend/tests/renderer/board/sgfLoader.test.ts frontend/tests/fixtures/simple-game.sgf frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat: parse SGF into a game tree with root-to-node move listing"
```

---

### Task 4: IPC-клиент (типы + HTTP/WS)

**Files:**
- Create: `frontend/src/renderer/src/ipc/client.ts`
- Test: `frontend/tests/renderer/ipc/client.test.ts`

**Interfaces:**
- Consumes: `window.baduk.getBackendConnection()` (из Task 2).
- Produces: типы `AnalyzeRequest`, `MoveInfo`, `RootInfo`, `AnalyzeResponse`, `StreamAnalyzeRequest`, `ProgressMessage`, `DoneMessage`, `ErrorMessage`; функции `analyzePosition(request: AnalyzeRequest): Promise<AnalyzeResponse>`, `streamAnalysis(request: StreamAnalyzeRequest, handlers): () => void`. Используется в Task 5, Task 7, Task 11.

- [ ] **Step 1: Написать падающий тест**

`frontend/tests/renderer/ipc/client.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { analyzePosition, streamAnalysis } from '@renderer/ipc/client'

function fakeAnalyzeRequest() {
  return {
    moves: [] as [string, string][],
    rules: 'chinese',
    komi: 7.5,
    boardXSize: 19,
    boardYSize: 19,
    analyzeTurns: [0] as [number],
    maxVisits: 50,
    includeOwnership: true,
  }
}

beforeEach(() => {
  ;(globalThis as any).window = (globalThis as any).window ?? {}
  ;(window as any).baduk = {
    getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
  }
})

describe('analyzePosition', () => {
  it('POSTs to /api/analyze with the auth header and returns the parsed response', async () => {
    const fakeResponse = { id: 'x', moveInfos: [], rootInfo: { winrate: 0.5, scoreLead: 0, visits: 1 } }
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => fakeResponse }) as any

    const result = await analyzePosition(fakeAnalyzeRequest())

    expect(globalThis.fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:5555/api/analyze',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-Auth-Token': 'test-token' }),
      })
    )
    expect(result).toEqual(fakeResponse)
  })

  it('throws with the response detail when the request fails', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
      json: async () => ({ detail: 'engine crashed' }),
    }) as any

    await expect(analyzePosition(fakeAnalyzeRequest())).rejects.toThrow('engine crashed')
  })
})

class FakeWebSocket {
  onopen: (() => void) | null = null
  listeners: Record<string, ((event: any) => void)[]> = {}
  sent: string[] = []
  closed = false
  constructor(public url: string) {
    queueMicrotask(() => this.dispatch('open', {}))
  }
  addEventListener(type: string, cb: (event: any) => void) {
    ;(this.listeners[type] ??= []).push(cb)
  }
  send(data: string) {
    this.sent.push(data)
  }
  close() {
    this.closed = true
  }
  dispatch(type: string, event: any) {
    for (const cb of this.listeners[type] ?? []) cb(event)
  }
}

describe('streamAnalysis', () => {
  it('sends the request on open and routes progress/done messages to handlers', async () => {
    let createdSocket: FakeWebSocket | undefined
    ;(globalThis as any).WebSocket = vi.fn().mockImplementation((url: string) => {
      createdSocket = new FakeWebSocket(url)
      return createdSocket
    })

    const onProgress = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    streamAnalysis(
      {
        moves: [],
        rules: 'chinese',
        komi: 7.5,
        boardXSize: 19,
        boardYSize: 19,
        turnNumbers: [0],
        maxVisits: 50,
        includeOwnership: true,
      },
      { onProgress, onDone, onError }
    )

    await vi.waitUntil(() => createdSocket !== undefined)
    await vi.waitUntil(() => createdSocket!.sent.length > 0)

    expect(createdSocket!.url).toBe('ws://127.0.0.1:5555/api/analyze/stream?token=test-token')

    createdSocket!.dispatch('message', {
      data: JSON.stringify({
        type: 'progress',
        turnNumber: 0,
        total: 1,
        result: { id: 'x', moveInfos: [], rootInfo: { winrate: 0.5, scoreLead: 0, visits: 1 } },
      }),
    })
    createdSocket!.dispatch('message', { data: JSON.stringify({ type: 'done' }) })

    expect(onProgress).toHaveBeenCalledOnce()
    expect(onDone).toHaveBeenCalledOnce()
    expect(onError).not.toHaveBeenCalled()
  })

  it('closes the socket when the returned unsubscribe function is called', async () => {
    let createdSocket: FakeWebSocket | undefined
    ;(globalThis as any).WebSocket = vi.fn().mockImplementation((url: string) => {
      createdSocket = new FakeWebSocket(url)
      return createdSocket
    })

    const close = streamAnalysis(
      {
        moves: [],
        rules: 'chinese',
        komi: 7.5,
        boardXSize: 19,
        boardYSize: 19,
        turnNumbers: [0],
        maxVisits: 50,
        includeOwnership: true,
      },
      { onProgress: vi.fn(), onDone: vi.fn(), onError: vi.fn() }
    )

    await vi.waitUntil(() => createdSocket !== undefined)
    close()
    expect(createdSocket!.closed).toBe(true)
  })
})
```

- [ ] **Step 2: Запустить тест, убедиться, что падает**

Run: `pnpm exec vitest run tests/renderer/ipc/client.test.ts`
Expected: FAIL — модуль `ipc/client` не существует.

- [ ] **Step 3: Реализовать `ipc/client.ts`**

```ts
export interface MoveInfo {
  move: string
  winrate: number
  scoreLead: number
  visits: number
  prior: number
  pv: string[]
}

export interface RootInfo {
  winrate: number
  scoreLead: number
  visits: number
}

export interface AnalyzeRequest {
  moves: [string, string][]
  rules: string
  komi: number
  boardXSize: number
  boardYSize: number
  analyzeTurns: [number]
  maxVisits: number
  includeOwnership: boolean
}

export interface AnalyzeResponse {
  id: string
  turnNumber?: number
  moveInfos: MoveInfo[]
  rootInfo: RootInfo
  ownership?: number[]
}

export interface StreamAnalyzeRequest {
  moves: [string, string][]
  rules: string
  komi: number
  boardXSize: number
  boardYSize: number
  turnNumbers: number[]
  maxVisits: number
  includeOwnership: boolean
}

export type ProgressMessage = { type: 'progress'; turnNumber: number; total: number; result: AnalyzeResponse }
export type DoneMessage = { type: 'done' }
export type ErrorMessage = { type: 'error'; detail: string }

let connectionPromise: Promise<{ port: number; token: string }> | null = null

function getConnection(): Promise<{ port: number; token: string }> {
  if (!connectionPromise) {
    connectionPromise = window.baduk.getBackendConnection()
  }
  return connectionPromise
}

export async function analyzePosition(request: AnalyzeRequest): Promise<AnalyzeResponse> {
  const { port, token } = await getConnection()
  const response = await fetch(`http://127.0.0.1:${port}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Auth-Token': token },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(`analyzePosition failed (${response.status}): ${body.detail ?? response.statusText}`)
  }
  return response.json()
}

export function streamAnalysis(
  request: StreamAnalyzeRequest,
  handlers: {
    onProgress(msg: ProgressMessage): void
    onDone(): void
    onError(msg: ErrorMessage): void
  }
): () => void {
  let closed = false
  let ws: WebSocket | null = null

  getConnection().then(({ port, token }) => {
    if (closed) return
    ws = new WebSocket(`ws://127.0.0.1:${port}/api/analyze/stream?token=${encodeURIComponent(token)}`)
    ws.addEventListener('open', () => {
      ws!.send(JSON.stringify(request))
    })
    ws.addEventListener('message', (event: any) => {
      const msg = JSON.parse(event.data as string)
      if (msg.type === 'progress') handlers.onProgress(msg)
      else if (msg.type === 'done') handlers.onDone()
      else if (msg.type === 'error') handlers.onError(msg)
    })
    ws.addEventListener('error', () => {
      handlers.onError({ type: 'error', detail: 'WebSocket connection error' })
    })
  })

  return () => {
    closed = true
    ws?.close()
  }
}
```

- [ ] **Step 4: Запустить тест, убедиться, что проходит**

Run: `pnpm exec vitest run tests/renderer/ipc/client.test.ts`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/renderer/src/ipc/client.ts frontend/tests/renderer/ipc/client.test.ts
git commit -m "feat: add typed IPC client for POST /api/analyze and the WS stream"
```

---

### Task 5: GameTree → запросы к backend (GTP-координаты)

**Files:**
- Create: `frontend/src/renderer/src/board/gameRequestBuilder.ts`
- Test: `frontend/tests/renderer/board/gameRequestBuilder.test.ts`

**Interfaces:**
- Consumes: `parseSgf`, `getBoardSize`, `findMainLineLeaf`, `movesFromRootToNode` (Task 3); `AnalyzeRequest`, `StreamAnalyzeRequest` (Task 4).
- Produces: `sgfCoordToGtp(sgfCoord: string | null, boardSize: number): string`, `mapSgfRules(ruValue: string | undefined): string`, `buildAnalyzeRequest(tree: GameTree, nodeId: number, options: { maxVisits: number }): AnalyzeRequest`, `buildStreamRequest(tree: GameTree, options: { maxVisits: number }): StreamAnalyzeRequest`. Используется в Task 11.

- [ ] **Step 1: Написать падающий тест**

`frontend/tests/renderer/board/gameRequestBuilder.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import { sgfCoordToGtp, mapSgfRules, buildAnalyzeRequest, buildStreamRequest } from '@renderer/board/gameRequestBuilder'

const fixtureContent = '(;GM[1]FF[4]SZ[19]KM[7.5]RU[Chinese];B[qd];W[dc];B[oq])'

describe('sgfCoordToGtp', () => {
  it('converts SGF coordinates to GTP coordinates on a 19x19 board', () => {
    expect(sgfCoordToGtp('qd', 19)).toBe('R16')
    expect(sgfCoordToGtp('dc', 19)).toBe('D17')
    expect(sgfCoordToGtp('oq', 19)).toBe('P3')
  })

  it('maps a null/empty coordinate to "pass"', () => {
    expect(sgfCoordToGtp(null, 19)).toBe('pass')
    expect(sgfCoordToGtp('', 19)).toBe('pass')
  })
})

describe('mapSgfRules', () => {
  it('lowercases a known ruleset name', () => {
    expect(mapSgfRules('Chinese')).toBe('chinese')
  })

  it('defaults to chinese for unknown/missing values', () => {
    expect(mapSgfRules(undefined)).toBe('chinese')
    expect(mapSgfRules('NotARuleset')).toBe('chinese')
  })
})

describe('buildAnalyzeRequest', () => {
  it('builds a single-turn request for the given node', () => {
    const tree = parseSgf(fixtureContent)
    const leaf = findMainLineLeaf(tree)
    const request = buildAnalyzeRequest(tree, leaf.id, { maxVisits: 500 })

    expect(request).toEqual({
      moves: [
        ['B', 'R16'],
        ['W', 'D17'],
        ['B', 'P3'],
      ],
      rules: 'chinese',
      komi: 7.5,
      boardXSize: 19,
      boardYSize: 19,
      analyzeTurns: [3],
      maxVisits: 500,
      includeOwnership: true,
    })
  })
})

describe('buildStreamRequest', () => {
  it('builds a request covering every turn of the main line', () => {
    const tree = parseSgf(fixtureContent)
    const request = buildStreamRequest(tree, { maxVisits: 500 })

    expect(request.moves).toEqual([
      ['B', 'R16'],
      ['W', 'D17'],
      ['B', 'P3'],
    ])
    expect(request.turnNumbers).toEqual([0, 1, 2, 3])
    expect(request.rules).toBe('chinese')
    expect(request.komi).toBe(7.5)
  })
})
```

- [ ] **Step 2: Запустить тест, убедиться, что падает**

Run: `pnpm exec vitest run tests/renderer/board/gameRequestBuilder.test.ts`
Expected: FAIL — модуль не существует.

- [ ] **Step 3: Реализовать `gameRequestBuilder.ts`**

```ts
import type GameTree from '@sabaki/immutable-gametree'
import { getBoardSize, findMainLineLeaf, movesFromRootToNode } from './sgfLoader'
import type { AnalyzeRequest, StreamAnalyzeRequest } from '../ipc/client'

const GTP_COLUMNS = 'ABCDEFGHJKLMNOPQRSTUVWXYZ'

export function sgfCoordToGtp(sgfCoord: string | null, boardSize: number): string {
  if (!sgfCoord) return 'pass'
  const colIndex = sgfCoord.charCodeAt(0) - 'a'.charCodeAt(0)
  const rowIndexFromTop = sgfCoord.charCodeAt(1) - 'a'.charCodeAt(0)
  return `${GTP_COLUMNS[colIndex]}${boardSize - rowIndexFromTop}`
}

const KNOWN_RULES = ['chinese', 'japanese', 'korean', 'aga', 'nz', 'tromp-taylor']

export function mapSgfRules(ruValue: string | undefined): string {
  const normalized = ruValue?.toLowerCase().trim()
  return normalized && KNOWN_RULES.includes(normalized) ? normalized : 'chinese'
}

function gtpMoves(tree: GameTree, nodeId: number, boardSize: number): [string, string][] {
  return movesFromRootToNode(tree, nodeId).map(({ color, sgfCoord }) => [
    color,
    sgfCoordToGtp(sgfCoord, boardSize),
  ])
}

export function buildAnalyzeRequest(
  tree: GameTree,
  nodeId: number,
  options: { maxVisits: number }
): AnalyzeRequest {
  const boardSize = getBoardSize(tree)
  const moves = gtpMoves(tree, nodeId, boardSize)
  return {
    moves,
    rules: mapSgfRules(tree.root.data.RU?.[0]),
    komi: tree.root.data.KM ? parseFloat(tree.root.data.KM[0]) : 7.5,
    boardXSize: boardSize,
    boardYSize: boardSize,
    analyzeTurns: [moves.length],
    maxVisits: options.maxVisits,
    includeOwnership: true,
  }
}

export function buildStreamRequest(tree: GameTree, options: { maxVisits: number }): StreamAnalyzeRequest {
  const boardSize = getBoardSize(tree)
  const leaf = findMainLineLeaf(tree)
  const moves = gtpMoves(tree, leaf.id, boardSize)
  return {
    moves,
    rules: mapSgfRules(tree.root.data.RU?.[0]),
    komi: tree.root.data.KM ? parseFloat(tree.root.data.KM[0]) : 7.5,
    boardXSize: boardSize,
    boardYSize: boardSize,
    turnNumbers: Array.from({ length: moves.length + 1 }, (_, i) => i),
    maxVisits: options.maxVisits,
    includeOwnership: true,
  }
}
```

- [ ] **Step 4: Запустить тест, убедиться, что проходит**

Run: `pnpm exec vitest run tests/renderer/board/gameRequestBuilder.test.ts`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/renderer/src/board/gameRequestBuilder.ts frontend/tests/renderer/board/gameRequestBuilder.test.ts
git commit -m "feat: build backend analyze requests from a game tree (SGF-to-GTP coords)"
```

---

### Task 6: Позиция на доске (взятия через `@sabaki/go-board`)

**Files:**
- Create: `frontend/src/renderer/src/board/boardPosition.ts`
- Test: `frontend/tests/renderer/board/boardPosition.test.ts`

**Interfaces:**
- Consumes: `getBoardSize`, `movesFromRootToNode` (Task 3).
- Produces: `sgfCoordToVertex(sgfCoord: string | null): [number, number] | null`, `boardPositionFromMoves(tree: GameTree, nodeId: number): { signMap: number[][]; boardSize: number }`. Используется в Task 7 (`appState.ts`).

- [ ] **Step 1: Установить зависимость**

```bash
pnpm add @sabaki/go-board
```

- [ ] **Step 2: Написать падающий тест**

`frontend/tests/renderer/board/boardPosition.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import { sgfCoordToVertex, boardPositionFromMoves } from '@renderer/board/boardPosition'

describe('sgfCoordToVertex', () => {
  it('converts SGF coordinates to zero-based [x, y] vertices', () => {
    expect(sgfCoordToVertex('dd')).toEqual([3, 3])
    expect(sgfCoordToVertex('aa')).toEqual([0, 0])
  })

  it('maps a null/empty coordinate to null (pass)', () => {
    expect(sgfCoordToVertex(null)).toBeNull()
    expect(sgfCoordToVertex('')).toBeNull()
  })
})

describe('boardPositionFromMoves', () => {
  it('replays moves onto an empty board and returns the resulting signMap', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[ec])')
    const leaf = findMainLineLeaf(tree)
    const { signMap, boardSize } = boardPositionFromMoves(tree, leaf.id)

    expect(boardSize).toBe(9)
    expect(signMap[4][4]).toBe(1) // 'ee' -> [4,4], black
    expect(signMap[2][4]).toBe(-1) // 'ec' -> [4,2], white
    expect(signMap[0][0]).toBe(0)
  })

  it('applies captures automatically (surrounded stone is removed)', () => {
    // 5x5 board: white stone at center [2,2] surrounded by black on all 4 sides
    const tree = parseSgf('(;GM[1]FF[4]SZ[5];W[cc];B[bc];B[dc];B[cb];B[cd])')
    const leaf = findMainLineLeaf(tree)
    const { signMap } = boardPositionFromMoves(tree, leaf.id)

    expect(signMap[2][2]).toBe(0) // white stone at [2,2] captured after the 4th black move
  })
})
```

- [ ] **Step 3: Запустить тест, убедиться, что падает**

Run: `pnpm exec vitest run tests/renderer/board/boardPosition.test.ts`
Expected: FAIL — модуль не существует.

- [ ] **Step 4: Реализовать `boardPosition.ts`**

```ts
import Board from '@sabaki/go-board'
import type GameTree from '@sabaki/immutable-gametree'
import { getBoardSize, movesFromRootToNode } from './sgfLoader'

export function sgfCoordToVertex(sgfCoord: string | null): [number, number] | null {
  if (!sgfCoord) return null
  const x = sgfCoord.charCodeAt(0) - 'a'.charCodeAt(0)
  const y = sgfCoord.charCodeAt(1) - 'a'.charCodeAt(0)
  return [x, y]
}

export function boardPositionFromMoves(
  tree: GameTree,
  nodeId: number
): { signMap: number[][]; boardSize: number } {
  const boardSize = getBoardSize(tree)
  let board = Board.fromDimensions(boardSize)

  for (const { color, sgfCoord } of movesFromRootToNode(tree, nodeId)) {
    const vertex = sgfCoordToVertex(sgfCoord)
    if (vertex === null) continue // pass — доска не меняется
    const sign = color === 'B' ? 1 : -1
    board = board.makeMove(sign, vertex)
  }

  return { signMap: board.signMap, boardSize }
}
```

- [ ] **Step 5: Запустить тест, убедиться, что проходит**

Run: `pnpm exec vitest run tests/renderer/board/boardPosition.test.ts`
Expected: PASS (4 passed). Если тест на взятие не проходит — проверить порядок аргументов `makeMove(sign, vertex)` и формат `vertex` по фактическому поведению установленной версии `@sabaki/go-board` (см. README пакета в `node_modules`).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/renderer/src/board/boardPosition.ts frontend/tests/renderer/board/boardPosition.test.ts frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat: derive board signMap from a game tree via @sabaki/go-board"
```

---

### Task 7: Состояние приложения (`@preact/signals`)

**Files:**
- Create: `frontend/src/renderer/src/state/appState.ts`
- Test: `frontend/tests/renderer/state/appState.test.ts`

**Interfaces:**
- Consumes: `movesFromRootToNode` (Task 3), `boardPositionFromMoves` (Task 6), `AnalyzeResponse` (Task 4).
- Produces: сигналы `currentTree`, `currentNodeId`, `analysisByTurn`, `streamStatus`, `streamError`; derived `currentBoardPosition`, `currentTurnNumber`, `currentMoveAnalysis`. Используется в Task 8, 9, 10, 11.

- [ ] **Step 1: Написать падающий тест**

`frontend/tests/renderer/state/appState.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import {
  currentTree,
  currentNodeId,
  analysisByTurn,
  currentBoardPosition,
  currentTurnNumber,
  currentMoveAnalysis,
} from '@renderer/state/appState'

const fixtureContent = '(;GM[1]FF[4]SZ[9]KM[7.5]RU[Chinese];B[ee])'

beforeEach(() => {
  currentTree.value = null
  currentNodeId.value = null
  analysisByTurn.value = new Map()
})

describe('currentBoardPosition', () => {
  it('is null when no tree is loaded', () => {
    expect(currentBoardPosition.value).toBeNull()
  })

  it('derives the signMap for the current node once a tree is loaded', () => {
    const tree = parseSgf(fixtureContent)
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    expect(currentBoardPosition.value?.boardSize).toBe(9)
    expect(currentBoardPosition.value?.signMap[4][4]).toBe(1)
  })
})

describe('currentTurnNumber + currentMoveAnalysis', () => {
  it('looks up the analysis for the turn matching the current node', () => {
    const tree = parseSgf(fixtureContent)
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    expect(currentTurnNumber.value).toBe(1)
    expect(currentMoveAnalysis.value).toBeNull()

    const fakeResponse = { id: 'x', moveInfos: [], rootInfo: { winrate: 0.6, scoreLead: 1, visits: 10 } }
    analysisByTurn.value = new Map([[1, fakeResponse]])

    expect(currentMoveAnalysis.value).toEqual(fakeResponse)
  })
})
```

- [ ] **Step 2: Запустить тест, убедиться, что падает**

Run: `pnpm exec vitest run tests/renderer/state/appState.test.ts`
Expected: FAIL — модуль не существует.

- [ ] **Step 3: Реализовать `appState.ts`**

```ts
import { signal, computed } from '@preact/signals'
import type GameTree from '@sabaki/immutable-gametree'
import { movesFromRootToNode } from '../board/sgfLoader'
import { boardPositionFromMoves } from '../board/boardPosition'
import type { AnalyzeResponse } from '../ipc/client'

export const currentTree = signal<GameTree | null>(null)
export const currentNodeId = signal<number | null>(null)
export const analysisByTurn = signal<Map<number, AnalyzeResponse>>(new Map())
export const streamStatus = signal<'idle' | 'streaming' | 'done' | 'error'>('idle')
export const streamError = signal<string | null>(null)

export const currentBoardPosition = computed(() => {
  const tree = currentTree.value
  const nodeId = currentNodeId.value
  if (!tree || nodeId === null) return null
  return boardPositionFromMoves(tree, nodeId)
})

export const currentTurnNumber = computed(() => {
  const tree = currentTree.value
  const nodeId = currentNodeId.value
  if (!tree || nodeId === null) return null
  return movesFromRootToNode(tree, nodeId).length
})

export const currentMoveAnalysis = computed(() => {
  const turn = currentTurnNumber.value
  if (turn === null) return null
  return analysisByTurn.value.get(turn) ?? null
})
```

- [ ] **Step 4: Запустить тест, убедиться, что проходит**

Run: `pnpm exec vitest run tests/renderer/state/appState.test.ts`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/renderer/src/state/appState.ts frontend/tests/renderer/state/appState.test.ts
git commit -m "feat: add @preact/signals app state (tree, current node, streamed analysis)"
```

---

### Task 8: Доска (Shudan)

**Files:**
- Create: `frontend/src/renderer/src/board/BoardView.tsx`
- Test: `frontend/tests/renderer/components/BoardView.test.tsx`

**Interfaces:**
- Consumes: `currentBoardPosition` (Task 7).
- Produces: `BoardView` (Preact-компонент). Расширяется в Task 10 (heatMap/lines/hover).

- [ ] **Step 1: Установить зависимость**

```bash
pnpm add @sabaki/shudan
```

- [ ] **Step 2: Написать падающий тест**

`frontend/tests/renderer/components/BoardView.test.tsx`:

```tsx
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/preact'
import { BoardView } from '@renderer/board/BoardView'
import { currentTree, currentNodeId } from '@renderer/state/appState'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'

afterEach(() => {
  currentTree.value = null
  currentNodeId.value = null
})

describe('BoardView', () => {
  it('shows a placeholder when no game is loaded', () => {
    const { getByText } = render(<BoardView />)
    expect(getByText(/Откройте SGF/i)).toBeTruthy()
  })

  it('renders the Shudan board once a position is available', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    const { container } = render(<BoardView />)
    expect(container.querySelector('.shudan-goban')).toBeTruthy()
  })
})
```

- [ ] **Step 3: Запустить тест, убедиться, что падает**

Run: `pnpm exec vitest run tests/renderer/components/BoardView.test.tsx`
Expected: FAIL — модуль не существует.

- [ ] **Step 4: Реализовать `BoardView.tsx`**

```tsx
import { Goban } from '@sabaki/shudan'
import '@sabaki/shudan/css/goban.css'
import { currentBoardPosition } from '../state/appState'

export function BoardView() {
  const position = currentBoardPosition.value

  if (!position) {
    return <div class="board-view board-view--empty">Откройте SGF-файл, чтобы начать</div>
  }

  return <Goban signMap={position.signMap} vertexSize={24} />
}
```

Если `Goban` не является именованным экспортом установленной версии `@sabaki/shudan` — проверить фактический способ экспорта в `node_modules/@sabaki/shudan` (`package.json`/`dist`) и поправить импорт.

- [ ] **Step 5: Запустить тест, убедиться, что проходит**

Run: `pnpm exec vitest run tests/renderer/components/BoardView.test.tsx`
Expected: PASS (2 passed). Класс `.shudan-goban` — проверить по фактическому DOM, который рендерит установленная версия Shudan (если класс называется иначе, поправить тест на реальный корневой класс компонента).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/renderer/src/board/BoardView.tsx frontend/tests/renderer/components/BoardView.test.tsx frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat: render the board with Shudan from app state"
```

---

### Task 9: Дерево вариаций + клавиатурная навигация

**Files:**
- Create: `frontend/src/renderer/src/board/VariationTree.tsx`
- Test: `frontend/tests/renderer/components/VariationTree.test.tsx`

**Interfaces:**
- Consumes: `currentTree`, `currentNodeId` (Task 7).
- Produces: `VariationTree` (Preact-компонент, рендерит дерево + обрабатывает `ArrowUp`/`ArrowDown` для шага по текущей ветке).

- [ ] **Step 1: Написать падающий тест**

`frontend/tests/renderer/components/VariationTree.test.tsx`:

```tsx
import { describe, it, expect, afterEach } from 'vitest'
import { render, fireEvent } from '@testing-library/preact'
import { VariationTree } from '@renderer/board/VariationTree'
import { currentTree, currentNodeId } from '@renderer/state/appState'
import { parseSgf } from '@renderer/board/sgfLoader'

afterEach(() => {
  currentTree.value = null
  currentNodeId.value = null
})

describe('VariationTree', () => {
  it('renders nothing meaningful when no tree is loaded', () => {
    const { container } = render(<VariationTree />)
    expect(container.textContent).toBe('')
  })

  it('steps to the next node on ArrowDown and back on ArrowUp', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[ec])')
    currentTree.value = tree
    currentNodeId.value = tree.root.id

    const { container } = render(<VariationTree />)
    const el = container.querySelector('[tabindex]') as HTMLElement
    el.focus()

    fireEvent.keyDown(el, { key: 'ArrowDown' })
    expect(currentNodeId.value).toBe(tree.root.children[0].id)

    fireEvent.keyDown(el, { key: 'ArrowUp' })
    expect(currentNodeId.value).toBe(tree.root.id)
  })

  it('does nothing on ArrowDown at a leaf with no children', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = tree.root.children[0]
    currentTree.value = tree
    currentNodeId.value = leaf.id

    const { container } = render(<VariationTree />)
    const el = container.querySelector('[tabindex]') as HTMLElement
    el.focus()
    fireEvent.keyDown(el, { key: 'ArrowDown' })

    expect(currentNodeId.value).toBe(leaf.id)
  })
})
```

- [ ] **Step 2: Запустить тест, убедиться, что падает**

Run: `pnpm exec vitest run tests/renderer/components/VariationTree.test.tsx`
Expected: FAIL — модуль не существует.

- [ ] **Step 3: Реализовать `VariationTree.tsx`**

```tsx
import { currentTree, currentNodeId } from '../state/appState'

function stepDown() {
  const tree = currentTree.value
  const nodeId = currentNodeId.value
  if (!tree || nodeId === null) return
  const node = tree.get(nodeId)
  if (node && node.children.length > 0) {
    currentNodeId.value = node.children[0].id
  }
}

function stepUp() {
  const tree = currentTree.value
  const nodeId = currentNodeId.value
  if (!tree || nodeId === null) return
  const node = tree.get(nodeId)
  if (node && node.parentId !== null && node.parentId !== undefined) {
    currentNodeId.value = node.parentId
  }
}

function handleKeyDown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    stepDown()
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    stepUp()
  }
}

export function VariationTree() {
  const tree = currentTree.value
  if (!tree) return <div class="variation-tree" />

  return (
    <div class="variation-tree" tabIndex={0} onKeyDown={handleKeyDown}>
      {renderNode(tree.root)}
    </div>
  )

  function renderNode(node: any) {
    const isCurrent = node.id === currentNodeId.value
    return (
      <div class="variation-tree__node" key={node.id}>
        <button
          type="button"
          class={isCurrent ? 'variation-tree__marker variation-tree__marker--current' : 'variation-tree__marker'}
          onClick={() => (currentNodeId.value = node.id)}
        >
          {node.data.B ? `B ${node.data.B[0]}` : node.data.W ? `W ${node.data.W[0]}` : '·'}
        </button>
        {node.children.length > 0 && (
          <div class="variation-tree__children">{node.children.map((child: any) => renderNode(child))}</div>
        )}
      </div>
    )
  }
}
```

- [ ] **Step 4: Запустить тест, убедиться, что проходит**

Run: `pnpm exec vitest run tests/renderer/components/VariationTree.test.tsx`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/renderer/src/board/VariationTree.tsx frontend/tests/renderer/components/VariationTree.test.tsx
git commit -m "feat: render the variation tree with arrow-key navigation"
```

---

### Task 10: Overlay-панели (heatmap, PV-стрелки, winrate-график)

**Files:**
- Modify: `frontend/src/renderer/src/board/BoardView.tsx`
- Create: `frontend/src/renderer/src/analysis/WinrateChart.tsx`
- Test: `frontend/tests/renderer/components/WinrateChart.test.tsx`
- Modify: `frontend/tests/renderer/components/BoardView.test.tsx`

**Interfaces:**
- Consumes: `currentMoveAnalysis`, `analysisByTurn` (Task 7); расширяет `BoardView` (Task 8).
- Produces: `WinrateChart` (Preact-компонент); `BoardView` теперь также рисует ownership-heatmap и PV-стрелки.

- [ ] **Step 1: Установить зависимость**

```bash
pnpm add uplot
```

- [ ] **Step 2: Дополнить тест `BoardView.test.tsx` (падающий кусок)**

Добавить в `frontend/tests/renderer/components/BoardView.test.tsx`:

```tsx
import { analysisByTurn } from '@renderer/state/appState'

// ...внутри describe('BoardView', ...):

it('shows ownership heatmap cells when analysis for the current turn is available', () => {
  const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
  const leaf = findMainLineLeaf(tree)
  currentTree.value = tree
  currentNodeId.value = leaf.id
  analysisByTurn.value = new Map([
    [1, { id: 'x', moveInfos: [], rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 }, ownership: new Array(81).fill(0.9) }],
  ])

  const { container } = render(<BoardView />)
  expect(container.querySelector('.shudan-heat_9')).toBeTruthy()
})
```

(И добавить `analysisByTurn.value = new Map()` в существующий `afterEach`.)

- [ ] **Step 3: Запустить тест, убедиться, что падает**

Run: `pnpm exec vitest run tests/renderer/components/BoardView.test.tsx`
Expected: FAIL — `BoardView` пока не рисует `heatMap`.

- [ ] **Step 4: Дополнить `BoardView.tsx` heatmap-конверсией и PV-стрелками**

Заменить содержимое файла целиком:

```tsx
import { Goban } from '@sabaki/shudan'
import '@sabaki/shudan/css/goban.css'
import { currentBoardPosition, currentMoveAnalysis } from '../state/appState'

function ownershipToHeatMap(ownership: number[] | undefined, boardSize: number): (null | { strength: number; text: string })[][] | undefined {
  if (!ownership) return undefined
  const grid: (null | { strength: number; text: string })[][] = []
  for (let y = 0; y < boardSize; y++) {
    const row: (null | { strength: number; text: string })[] = []
    for (let x = 0; x < boardSize; x++) {
      const value = ownership[y * boardSize + x]
      const strength = Math.min(9, Math.max(1, Math.ceil(Math.abs(value) * 9)))
      row.push({ strength, text: value.toFixed(2) })
    }
    grid.push(row)
  }
  return grid
}

function pvToLines(pv: string[] | undefined): { v1: [number, number]; v2: [number, number]; type: string }[] {
  if (!pv || pv.length < 2) return []
  // PV-координаты приходят от backend в GTP-формате (см. gameRequestBuilder.ts) —
  // здесь предполагается, что для отображения стрелок реализована обратная конверсия
  // GTP -> [x, y]; для Фазы 1 достаточно первой стрелки текущего PV.
  return []
}

export function BoardView() {
  const position = currentBoardPosition.value
  const analysis = currentMoveAnalysis.value

  if (!position) {
    return <div class="board-view board-view--empty">Откройте SGF-файл, чтобы начать</div>
  }

  const heatMap = ownershipToHeatMap(analysis?.ownership, position.boardSize)

  return <Goban signMap={position.signMap} heatMap={heatMap} vertexSize={24} />
}
```

**Важно:** `pvToLines` намеренно оставлен как заглушка, возвращающая `[]` — обратная конверсия GTP→vertex для PV-стрелок не покрыта тестом в этом шаге и не влияет на прохождение теста Step 3 (который проверяет только heatmap). Реализовать её как отдельный маленький шаг ниже.

- [ ] **Step 5: Запустить тест из Step 3, убедиться, что проходит**

Run: `pnpm exec vitest run tests/renderer/components/BoardView.test.tsx`
Expected: PASS (3 passed)

- [ ] **Step 6: Написать падающий тест на PV-стрелки**

Добавить в `frontend/tests/renderer/components/BoardView.test.tsx`:

```tsx
it('draws a PV line from the first two moves of the top candidate', () => {
  const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
  const leaf = findMainLineLeaf(tree)
  currentTree.value = tree
  currentNodeId.value = leaf.id
  analysisByTurn.value = new Map([
    [
      1,
      {
        id: 'x',
        moveInfos: [{ move: 'C3', winrate: 0.6, scoreLead: 1, visits: 100, prior: 0.5, pv: ['C3', 'G7'] }],
        rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 },
      },
    ],
  ])

  const { container } = render(<BoardView />)
  expect(container.querySelector('.shudan-line')).toBeTruthy()
})
```

- [ ] **Step 7: Запустить тест, убедиться, что падает**

Run: `pnpm exec vitest run tests/renderer/components/BoardView.test.tsx`
Expected: FAIL — `lines` пока всегда `[]`.

- [ ] **Step 8: Реализовать GTP→vertex конверсию и подключить `lines`**

В `BoardView.tsx` **удалить** заглушку `pvToLines` из Step 4 и **заменить** её (вместе с добавлением `gtpToVertex` перед ней, сразу после `ownershipToHeatMap`) на:

```tsx
const GTP_COLUMNS = 'ABCDEFGHJKLMNOPQRSTUVWXYZ'

function gtpToVertex(gtpCoord: string, boardSize: number): [number, number] | null {
  if (gtpCoord === 'pass') return null
  const col = GTP_COLUMNS.indexOf(gtpCoord[0].toUpperCase())
  const row = parseInt(gtpCoord.slice(1), 10)
  if (col === -1 || Number.isNaN(row)) return null
  return [col, boardSize - row]
}

function pvToLines(
  pv: string[] | undefined,
  boardSize: number
): { v1: [number, number]; v2: [number, number]; type: string }[] {
  if (!pv || pv.length < 2) return []
  const lines: { v1: [number, number]; v2: [number, number]; type: string }[] = []
  for (let i = 0; i < pv.length - 1; i++) {
    const v1 = gtpToVertex(pv[i], boardSize)
    const v2 = gtpToVertex(pv[i + 1], boardSize)
    if (v1 && v2) lines.push({ v1, v2, type: 'line' })
  }
  return lines
}
```

(Файл должен содержать только одно определение `pvToLines` — эту версию, не заглушку из Step 4.) И заменить последний `return` в `BoardView`:

```tsx
  const heatMap = ownershipToHeatMap(analysis?.ownership, position.boardSize)
  const topMove = analysis?.moveInfos[0]
  const lines = pvToLines(topMove?.pv, position.boardSize)

  return <Goban signMap={position.signMap} heatMap={heatMap} lines={lines} vertexSize={24} />
```

Проверить фактическое имя CSS-класса для линий у установленной версии Shudan (в тесте использован `.shudan-line` по аналогии с `.shudan-heat_N`) — поправить тест на реальный класс, если отличается.

- [ ] **Step 9: Запустить тест, убедиться, что проходит**

Run: `pnpm exec vitest run tests/renderer/components/BoardView.test.tsx`
Expected: PASS (4 passed)

- [ ] **Step 10: Написать падающий тест на `WinrateChart`**

`frontend/tests/renderer/components/WinrateChart.test.tsx`:

```tsx
import { describe, it, expect, afterEach } from 'vitest'
import { render } from '@testing-library/preact'
import { WinrateChart } from '@renderer/analysis/WinrateChart'
import { analysisByTurn } from '@renderer/state/appState'

afterEach(() => {
  analysisByTurn.value = new Map()
})

describe('WinrateChart', () => {
  it('renders a chart container without throwing when no data is present', () => {
    const { container } = render(<WinrateChart />)
    expect(container.querySelector('.winrate-chart')).toBeTruthy()
  })

  it('re-renders without throwing once analysis data arrives', () => {
    const { container, rerender } = render(<WinrateChart />)
    analysisByTurn.value = new Map([
      [0, { id: 'a', moveInfos: [], rootInfo: { winrate: 0.5, scoreLead: 0, visits: 1 } }],
      [1, { id: 'b', moveInfos: [], rootInfo: { winrate: 0.55, scoreLead: 1.2, visits: 1 } }],
    ])
    rerender(<WinrateChart />)
    expect(container.querySelector('.winrate-chart')).toBeTruthy()
  })
})
```

- [ ] **Step 11: Запустить тест, убедиться, что падает**

Run: `pnpm exec vitest run tests/renderer/components/WinrateChart.test.tsx`
Expected: FAIL — модуль не существует.

- [ ] **Step 12: Реализовать `WinrateChart.tsx`**

```tsx
import { useEffect, useRef } from 'preact/hooks'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { effect } from '@preact/signals'
import { analysisByTurn } from '../state/appState'

export function WinrateChart() {
  const containerRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    plotRef.current = new uPlot(
      {
        width: containerRef.current.clientWidth || 600,
        height: 160,
        series: [
          {},
          { label: 'Winrate (B), %', stroke: '#4c9aff', width: 2 },
          { label: 'Score lead', stroke: '#ff6b6b', width: 2, dash: [6, 4], scale: 'score' },
        ],
        scales: {
          y: { range: [0, 100] },
          score: {},
        },
        axes: [{}, { scale: 'y', label: 'Winrate %' }, { scale: 'score', side: 1, label: 'Score lead' }],
      },
      [[], [], []],
      containerRef.current
    )

    const stopEffect = effect(() => {
      const entries = [...analysisByTurn.value.entries()].sort((a, b) => a[0] - b[0])
      const xs = entries.map(([turn]) => turn)
      const winrates = entries.map(([, r]) => r.rootInfo.winrate * 100)
      const scoreLeads = entries.map(([, r]) => r.rootInfo.scoreLead)
      plotRef.current?.setData([xs, winrates, scoreLeads])
    })

    return () => {
      stopEffect()
      plotRef.current?.destroy()
    }
  }, [])

  return <div ref={containerRef} class="winrate-chart" />
}
```

- [ ] **Step 13: Запустить тест, убедиться, что проходит**

Run: `pnpm exec vitest run tests/renderer/components/WinrateChart.test.tsx`
Expected: PASS (2 passed)

- [ ] **Step 14: Запустить полный набор тестов**

Run: `pnpm exec vitest run`
Expected: PASS (все тесты всех предыдущих задач)

- [ ] **Step 15: Commit**

```bash
git add frontend/src/renderer/src/board/BoardView.tsx frontend/src/renderer/src/analysis/WinrateChart.tsx frontend/tests/renderer/components/BoardView.test.tsx frontend/tests/renderer/components/WinrateChart.test.tsx frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat: add ownership heatmap, PV arrows, and winrate/score-lead chart"
```

---

### Task 11: AppShell (layout B, ConnectionGate, загрузка SGF, обработка ошибок)

**Files:**
- Modify: `frontend/src/renderer/src/App.tsx`
- Create: `frontend/src/renderer/src/App.css` (или расширение существующего глобального CSS файла, если scaffold уже создал один — использовать его)
- Test: `frontend/tests/renderer/components/App.test.tsx`

**Interfaces:**
- Consumes: всё из Task 2–10 (`getBackendConnection` через `window.baduk`, `parseSgf`, `buildStreamRequest`, `streamAnalysis`, `appState`-сигналы, `BoardView`, `VariationTree`, `WinrateChart`).
- Produces: собранное приложение — терминальная задача плана.

- [ ] **Step 1: Написать падающий тест**

`frontend/tests/renderer/components/App.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/preact'
import { App } from '@renderer/App'

beforeEach(() => {
  ;(globalThis as any).window = (globalThis as any).window ?? {}
})

describe('App / ConnectionGate', () => {
  it('shows a connection-error screen if the backend connection promise rejects', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockRejectedValue(new Error('backend did not start')),
    }

    const { getByText } = render(<App />)

    await waitFor(() => {
      expect(getByText(/не удалось запустить backend/i)).toBeTruthy()
    })
  })

  it('renders the app shell once the backend connection resolves', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
    }

    const { container } = render(<App />)

    await waitFor(() => {
      expect(container.querySelector('.app-shell')).toBeTruthy()
    })
  })
})
```

- [ ] **Step 2: Запустить тест, убедиться, что падает**

Run: `pnpm exec vitest run tests/renderer/components/App.test.tsx`
Expected: FAIL — `App` ещё не реализует `ConnectionGate`/`.app-shell`.

- [ ] **Step 3: Реализовать `App.tsx`**

Заменить содержимое файла (созданного scaffold'ом) на:

```tsx
import { useEffect } from 'preact/hooks'
import { signal } from '@preact/signals'
import { BoardView } from './board/BoardView'
import { VariationTree } from './board/VariationTree'
import { WinrateChart } from './analysis/WinrateChart'
import { parseSgf, SgfParseError } from './board/sgfLoader'
import { buildStreamRequest } from './board/gameRequestBuilder'
import { streamAnalysis } from './ipc/client'
import { currentTree, currentNodeId, analysisByTurn, streamStatus, streamError } from './state/appState'

const DEFAULT_MAX_VISITS = 500

const connectionState = signal<'pending' | 'ready' | 'error'>('pending')
const connectionErrorMessage = signal<string | null>(null)
const sgfError = signal<string | null>(null)
const lastLoadedSgfContent = signal<string | null>(null)

function loadGame(content: string) {
  lastLoadedSgfContent.value = content
  sgfError.value = null
  let tree
  try {
    tree = parseSgf(content)
  } catch (err) {
    sgfError.value = err instanceof SgfParseError ? err.message : 'Не удалось разобрать SGF'
    return
  }

  currentTree.value = tree
  currentNodeId.value = tree.root.id
  analysisByTurn.value = new Map()
  streamStatus.value = 'streaming'
  streamError.value = null

  const request = buildStreamRequest(tree, { maxVisits: DEFAULT_MAX_VISITS })
  streamAnalysis(request, {
    onProgress(msg) {
      const next = new Map(analysisByTurn.value)
      next.set(msg.turnNumber, msg.result)
      analysisByTurn.value = next
    },
    onDone() {
      streamStatus.value = 'done'
    },
    onError(msg) {
      streamStatus.value = 'error'
      streamError.value = msg.detail
    },
  })
}

function handleDrop(event: DragEvent) {
  event.preventDefault()
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  file.text().then(loadGame)
}

function handleDragOver(event: DragEvent) {
  event.preventDefault()
}

export function App() {
  useEffect(() => {
    window.baduk
      .getBackendConnection()
      .then(() => {
        connectionState.value = 'ready'
      })
      .catch((err: Error) => {
        connectionState.value = 'error'
        connectionErrorMessage.value = err.message
      })
  }, [])

  if (connectionState.value === 'pending') {
    return <div class="connection-gate">Подключение к backend...</div>
  }

  if (connectionState.value === 'error') {
    return (
      <div class="connection-gate connection-gate--error">
        Не удалось запустить backend: {connectionErrorMessage.value}. Перезапустите приложение.
      </div>
    )
  }

  return (
    <div class="app-shell" onDrop={handleDrop} onDragOver={handleDragOver}>
      <div class="app-shell__top">
        <div class="app-shell__tree">
          <VariationTree />
        </div>
        <div class="app-shell__board">
          <BoardView />
          {sgfError.value && <div class="app-shell__banner app-shell__banner--error">{sgfError.value}</div>}
          {streamStatus.value === 'error' && (
            <div class="app-shell__banner app-shell__banner--error">
              Ошибка анализа: {streamError.value}
              <button
                type="button"
                onClick={() => lastLoadedSgfContent.value && loadGame(lastLoadedSgfContent.value)}
              >
                Повторить
              </button>
            </div>
          )}
        </div>
      </div>
      <div class="app-shell__chart">
        <WinrateChart />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Обновить `main.tsx` (bootstrap), если он ещё рендерит старый scaffold-компонент**

Убедиться, что `frontend/src/renderer/src/main.tsx` рендерит `<App />` из `./App` (созданный scaffold'ом bootstrap обычно уже это делает под другим именем компонента — переименовать импорт на `App`, если нужно).

- [ ] **Step 5: Запустить тест, убедиться, что проходит**

Run: `pnpm exec vitest run tests/renderer/components/App.test.tsx`
Expected: PASS (2 passed)

- [ ] **Step 6: Добавить layout-CSS (вариант B)**

В файл глобальных стилей (созданный scaffold'ом, обычно `frontend/src/renderer/src/assets/*.css`, импортированный в `main.tsx`) добавить:

```css
.app-shell {
  display: grid;
  grid-template-rows: 1fr auto;
  height: 100vh;
}
.app-shell__top {
  display: grid;
  grid-template-columns: minmax(160px, 220px) 1fr;
  gap: 8px;
  overflow: hidden;
}
.app-shell__chart {
  border-top: 1px solid var(--border-color, #333);
}
.connection-gate {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
}
```

- [ ] **Step 7: Запустить полный набор тестов**

Run: `pnpm exec vitest run`
Expected: PASS (весь набор тестов всех задач плана)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/renderer/src/App.tsx frontend/tests/renderer/components/App.test.tsx frontend/src/renderer/src/assets
git commit -m "feat: wire AppShell (layout B, SGF drag&drop, streaming analysis, error banners)"
```

---

## Definition of Done

- Весь набор Vitest-тестов (`pnpm exec vitest run` из `frontend/`) проходит зелёным после каждой задачи.
- `pnpm exec electron-vite dev` (backend-sidecar запущен, `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` установлены) открывает окно, drag&drop SGF-файла показывает доску и дерево вариаций, winrate/ownership обновляются по мере прихода WS-прогресса — это финальная **ручная** сквозная приёмка (критерий Фазы 1 из `docs/ARCHITECTURE.md` § Проверка), не автоматизируется в этом плане.
- Некорректный SGF → видимая ошибка в UI, не тихий сбой.
- Обрыв/ошибка backend-подключения → явный экран ошибки, не пустой белый экран.
- Ни один хардкод-путь (KataGo, backend-команда) не закоммичен — только `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL`/`BADUK_BACKEND_COMMAND` env vars.
