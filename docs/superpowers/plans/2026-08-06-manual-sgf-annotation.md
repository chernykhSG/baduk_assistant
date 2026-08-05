# Ручная SGF-разметка/комментарии Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user annotate an open SGF game (letter/number labels, triangle/square/circle/cross figures, per-move text comments) and save those annotations back to the SGF file, on top of the already-shipped Phase 1 viewer.

**Architecture:** The `GameTree` from `@sabaki/immutable-gametree` stays the single source of truth — annotations are written as ordinary SGF node properties (`TR`/`SQ`/`CR`/`MA`/`LB`/`C`) via `tree.mutate()`, exactly like the tree itself was produced by `@sabaki/sgf`'s parser. Saving is `sgf.stringify(tree.root)` written to disk through a new, minimal main-process file IPC. A toolbar next to the board selects the active annotation tool; clicking a board vertex applies it. A third "Разметка" tab in the existing analysis panel holds the per-node text comment.

**Tech Stack:** Electron + TypeScript + Preact (existing Phase 1 stack), `@sabaki/sgf` (`stringify`), `@sabaki/immutable-gametree` (`tree.mutate`/`Draft`), `@sabaki/shudan` (`Marker` type, `onVertexClick`), `@preact/signals` (`signal`/`computed`/`useSignalEffect`), Vitest + `@testing-library/preact` + jsdom (existing test stack), Node's `node:fs/promises` + Electron's `dialog` (new, main-process only).

## Global Constraints

- Work only on a new branch off `main`, named `feature-sgf-annotation` — never commit directly to `main` (see `CLAUDE.md`).
- TDD: write the failing test before the implementation, for every step that produces testable code.
- No config/paths/secrets hardcoded in source (not directly relevant to this feature, but the rule always applies — see `CLAUDE.md`).
- Out of scope, do NOT implement: undo/redo for annotation actions, editing the move tree itself (adding/removing/reordering branches), anything LLM-related. If a task's obvious "nice to have" would cross into one of these, skip it.
- Spec of record: `docs/superpowers/specs/2026-08-06-manual-sgf-annotation-design.md`. Every task below implements a specific section of it — consult it for the "why" behind a decision if a step feels arbitrary.
- Existing project conventions to preserve: Preact function components using `preact/hooks` (`useState`/`useEffect`) plus global `@preact/signals` state in `frontend/src/renderer/src/state/appState.ts`; Russian-language user-facing strings; dark-theme CSS already in `frontend/src/renderer/assets/main.css`; `@typescript-eslint/no-explicit-any` is enabled for `src/**` (not `tests/**`) — never introduce an explicit `: any` in `src/`.

---

## Context for every task: libraries used, verified against installed source

These are not guesses — each was confirmed by reading the installed package source in this repo's `node_modules` during planning. Use them verbatim.

**`@sabaki/sgf`** (`stringify`, from `node_modules/.pnpm/@sabaki+sgf@3.5.0/.../src/stringify.js`):
```js
exports.stringify = function(node, {linebreak = '\n', indent = '  ', level = 0} = {})
```
Takes a node shaped `{data, children}` (recursively) — exactly the shape of `GameTree`'s `tree.root`. No adapter needed: `sgf.stringify(tree.root)` produces the full SGF text.

**`@sabaki/immutable-gametree`** (`Draft`, from `node_modules/.pnpm/@sabaki+immutable-gametree@1.9.4/.../src/Draft.js`):
- `tree.mutate(mutator: (draft: Draft) => void): GameTree` — returns a **new** tree, original untouched.
- `draft.get(id)` → node object `{id, data, parentId, children}` (same shape as `NodeObject` in `sgfLoader.ts`).
- `draft.addToProperty(id, property, value)` — appends `value` to `data[property]` (creates the array if absent), ignores exact duplicates.
- `draft.removeFromProperty(id, property, value)` — removes `value` from `data[property]`; deletes the key entirely if the array becomes empty.
- `draft.updateProperty(id, property, values)` — replaces `data[property]` wholesale; `values == null || values.length === 0` deletes the key.

Neither `@sabaki/sgf` nor `@sabaki/immutable-gametree` ship TypeScript declarations (confirmed: no `.d.ts`, no `types` field in either `package.json`) — this is why `sgfLoader.ts` already hand-rolls a local `NodeObject` interface instead of importing one. Follow the same approach: `tree: GameTree` is imported as a type from the untyped package (already done project-wide, resolves without error under this project's tsconfig), but the `Draft` parameter inside a `mutate()` callback needs its own **local** interface (below) so that `@typescript-eslint/no-explicit-any` isn't triggered by an explicit `any`.

**`@sabaki/shudan`** (`Marker` type + `onVertexClick`, from `node_modules/.pnpm/@sabaki+shudan@1.8.0_preact@10.29.8/.../src/Goban.d.ts` — this package **does** ship real `.d.ts` files):
```ts
export interface Marker {
  type?: "circle" | "cross" | "triangle" | "square" | "point" | "loader" | "label" | null
  label?: string | null
  tooltip?: string | null
}
export type Vertex = [x: number, y: number]
// on GobanProps (inherited by BoundedGobanProps):
onVertexClick?: (evt: MouseEvent, vertex: Vertex) => void
markerMap?: Marker[][]
```
So the four figure properties map directly: `TR` → `{type: 'triangle'}`, `SQ` → `{type: 'square'}`, `CR` → `{type: 'circle'}`, `MA` → `{type: 'cross'}`, `LB` → `{type: 'label', label: '...'}`. Import `Marker` (and `Vertex` where convenient) as a type directly from `@sabaki/shudan` instead of hand-rolling a local marker type.

**`webUtils.getPathForFile`** — already available with zero new preload code. `frontend/src/preload/index.ts` already does `contextBridge.exposeInMainWorld('electron', electronAPI)` where `electronAPI` comes from `@electron-toolkit/preload`, whose shipped `ElectronAPI` interface already includes `webUtils: WebUtils` with `getPathForFile(file: File): string`. So `window.electron.webUtils.getPathForFile(file)` is already callable from renderer code today, fully typed, no preload/`global.d.ts` changes needed for it.

---

### Task 1: Annotation mutation + read-model helpers (`board/annotations.ts`)

**Files:**
- Create: `frontend/src/renderer/src/board/annotations.ts`
- Test: `frontend/tests/renderer/board/annotations.test.ts`

**Interfaces:**
- Consumes: `NodeObject` (type, from `frontend/src/renderer/src/board/sgfLoader.ts`), `sgfCoordToVertex` (function, from `frontend/src/renderer/src/board/boardPosition.ts`), `Marker` (type, from `@sabaki/shudan`), `GameTree` (type, from `@sabaki/immutable-gametree`).
- Produces (used by later tasks): `type FigureProperty = 'TR' | 'SQ' | 'CR' | 'MA'`; `type AnnotationTool = FigureProperty | 'LB' | 'erase'`; `vertexToSgfCoord(vertex: [number, number]): string`; `addFigureMarkup(tree: GameTree, nodeId: number, property: FigureProperty, vertex: [number, number]): GameTree`; `addLabelMarkup(tree: GameTree, nodeId: number, vertex: [number, number], text: string): GameTree`; `removeMarkupAtVertex(tree: GameTree, nodeId: number, vertex: [number, number]): GameTree`; `setComment(tree: GameTree, nodeId: number, text: string): GameTree`; `nextLabelText(node: NodeObject, mode: 'letter' | 'number'): string`; `emptyMarkerGrid(boardSize: number): (Marker | null)[][]`; `buildAnnotationMarkerMap(node: NodeObject, boardSize: number): (Marker | null)[][]`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/renderer/board/annotations.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import type { NodeObject } from '@renderer/board/sgfLoader'
import {
  vertexToSgfCoord,
  addFigureMarkup,
  addLabelMarkup,
  removeMarkupAtVertex,
  setComment,
  nextLabelText,
  buildAnnotationMarkerMap,
  emptyMarkerGrid
} from '@renderer/board/annotations'

describe('vertexToSgfCoord', () => {
  it('converts a vertex to the matching SGF coordinate', () => {
    expect(vertexToSgfCoord([0, 0])).toBe('aa')
    expect(vertexToSgfCoord([2, 4])).toBe('ce')
  })
})

describe('addFigureMarkup', () => {
  it('adds a figure property to the target node without mutating the original tree', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    const next = addFigureMarkup(tree, leaf.id, 'TR', [2, 4])

    expect((tree.get(leaf.id) as NodeObject).data.TR).toBeUndefined()
    expect((next.get(leaf.id) as NodeObject).data.TR).toEqual(['ce'])
  })

  it('replaces any existing markup at the same vertex instead of stacking it', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    const withCircle = addFigureMarkup(tree, leaf.id, 'CR', [2, 4])
    const withTriangle = addFigureMarkup(withCircle, leaf.id, 'TR', [2, 4])

    const data = (withTriangle.get(leaf.id) as NodeObject).data
    expect(data.CR).toBeUndefined()
    expect(data.TR).toEqual(['ce'])
  })
})

describe('addLabelMarkup', () => {
  it('adds a coord:text entry to LB', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    const next = addLabelMarkup(tree, leaf.id, [4, 4], 'A')

    expect((next.get(leaf.id) as NodeObject).data.LB).toEqual(['ee:A'])
  })

  it('replaces a figure previously placed at the same vertex', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    const withSquare = addFigureMarkup(tree, leaf.id, 'SQ', [4, 4])
    const withLabel = addLabelMarkup(withSquare, leaf.id, [4, 4], 'A')

    const data = (withLabel.get(leaf.id) as NodeObject).data
    expect(data.SQ).toBeUndefined()
    expect(data.LB).toEqual(['ee:A'])
  })
})

describe('removeMarkupAtVertex', () => {
  it('removes a figure at the given vertex', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    const withMarker = addFigureMarkup(tree, leaf.id, 'MA', [1, 1])

    const cleared = removeMarkupAtVertex(withMarker, leaf.id, [1, 1])

    expect((cleared.get(leaf.id) as NodeObject).data.MA).toBeUndefined()
  })

  it('removes a label at the given vertex without touching other labels', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    const withLabels = addLabelMarkup(addLabelMarkup(tree, leaf.id, [0, 0], 'A'), leaf.id, [1, 0], 'B')

    const cleared = removeMarkupAtVertex(withLabels, leaf.id, [0, 0])

    expect((cleared.get(leaf.id) as NodeObject).data.LB).toEqual(['ba:B'])
  })

  it('is a no-op when there is no markup at the vertex', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    const result = removeMarkupAtVertex(tree, leaf.id, [3, 3])

    expect((result.get(leaf.id) as NodeObject).data).toEqual((tree.get(leaf.id) as NodeObject).data)
  })
})

describe('setComment', () => {
  it('sets the C property on the target node', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    const next = setComment(tree, leaf.id, 'Хороший ход')

    expect((next.get(leaf.id) as NodeObject).data.C).toEqual(['Хороший ход'])
  })

  it('clears the C property when set to an empty string', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]C[old])')
    const leaf = findMainLineLeaf(tree)

    const next = setComment(tree, leaf.id, '')

    expect((next.get(leaf.id) as NodeObject).data.C).toBeUndefined()
  })
})

describe('nextLabelText', () => {
  it('suggests A for the first letter label', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    expect(nextLabelText(tree.get(leaf.id) as NodeObject, 'letter')).toBe('A')
  })

  it('suggests the next unused letter after existing letter labels', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]LB[aa:A][bb:B])')
    const leaf = findMainLineLeaf(tree)
    expect(nextLabelText(tree.get(leaf.id) as NodeObject, 'letter')).toBe('C')
  })

  it('suggests 1 for the first number label, ignoring letter labels', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]LB[aa:A])')
    const leaf = findMainLineLeaf(tree)
    expect(nextLabelText(tree.get(leaf.id) as NodeObject, 'number')).toBe('1')
  })

  it('suggests the next unused number after existing number labels', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]LB[aa:1][bb:2])')
    const leaf = findMainLineLeaf(tree)
    expect(nextLabelText(tree.get(leaf.id) as NodeObject, 'number')).toBe('3')
  })
})

describe('emptyMarkerGrid', () => {
  it('returns a boardSize x boardSize grid of nulls', () => {
    const grid = emptyMarkerGrid(3)
    expect(grid).toEqual([
      [null, null, null],
      [null, null, null],
      [null, null, null]
    ])
  })
})

describe('buildAnnotationMarkerMap', () => {
  it('renders figures and labels from node data at their board positions', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]TR[gg]SQ[cc]CR[aa]MA[ii]LB[ee:A])')
    const leaf = findMainLineLeaf(tree)

    const grid = buildAnnotationMarkerMap(tree.get(leaf.id) as NodeObject, 9)

    // SGF 'gg' -> vertex [6, 6], 'cc' -> [2, 2], 'aa' -> [0, 0], 'ii' -> [8, 8], 'ee' -> [4, 4]
    expect(grid[6][6]).toEqual({ type: 'triangle' })
    expect(grid[2][2]).toEqual({ type: 'square' })
    expect(grid[0][0]).toEqual({ type: 'circle' })
    expect(grid[8][8]).toEqual({ type: 'cross' })
    expect(grid[4][4]).toEqual({ type: 'label', label: 'A' })
  })

  it('returns an empty grid for a node with no markup', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    expect(buildAnnotationMarkerMap(tree.get(leaf.id) as NodeObject, 9)).toEqual(emptyMarkerGrid(9))
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && pnpm exec vitest run tests/renderer/board/annotations.test.ts`
Expected: FAIL — `Cannot find module '@renderer/board/annotations'` (file doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/renderer/src/board/annotations.ts`:

```ts
import type GameTree from '@sabaki/immutable-gametree'
import type { Marker } from '@sabaki/shudan'
import type { NodeObject } from './sgfLoader'
import { sgfCoordToVertex } from './boardPosition'

export type FigureProperty = 'TR' | 'SQ' | 'CR' | 'MA'
export type AnnotationTool = FigureProperty | 'LB' | 'erase'

const FIGURE_PROPERTIES: FigureProperty[] = ['TR', 'SQ', 'CR', 'MA']

const FIGURE_TO_MARKER_TYPE: Record<FigureProperty, Marker['type']> = {
  TR: 'triangle',
  SQ: 'square',
  CR: 'circle',
  MA: 'cross'
}

/**
 * The subset of @sabaki/immutable-gametree's Draft class this module uses.
 * Neither @sabaki/sgf nor @sabaki/immutable-gametree ship TypeScript types
 * (confirmed against their published package.json/source) — this local
 * interface lets `tree.mutate(draft => ...)` callbacks stay typed without
 * an explicit `any`, matching how the rest of this codebase (sgfLoader.ts's
 * NodeObject) hand-rolls shapes for these two libraries.
 */
interface TreeDraft {
  get(id: number): NodeObject | null
  addToProperty(id: number, property: string, value: string): boolean
  removeFromProperty(id: number, property: string, value: string): boolean
  updateProperty(id: number, property: string, values: string[]): boolean
}

export function vertexToSgfCoord(vertex: [number, number]): string {
  const [x, y] = vertex
  return String.fromCharCode('a'.charCodeAt(0) + x) + String.fromCharCode('a'.charCodeAt(0) + y)
}

function clearMarkupInDraft(draft: TreeDraft, nodeId: number, coord: string): void {
  const node = draft.get(nodeId)
  if (!node) return

  for (const property of FIGURE_PROPERTIES) {
    if (node.data[property]?.includes(coord)) {
      draft.removeFromProperty(nodeId, property, coord)
    }
  }

  const existingLabel = node.data.LB?.find((entry) => entry.split(':')[0] === coord)
  if (existingLabel) {
    draft.removeFromProperty(nodeId, 'LB', existingLabel)
  }
}

export function addFigureMarkup(
  tree: GameTree,
  nodeId: number,
  property: FigureProperty,
  vertex: [number, number]
): GameTree {
  const coord = vertexToSgfCoord(vertex)
  return tree.mutate((draft: TreeDraft) => {
    clearMarkupInDraft(draft, nodeId, coord)
    draft.addToProperty(nodeId, property, coord)
  })
}

export function addLabelMarkup(
  tree: GameTree,
  nodeId: number,
  vertex: [number, number],
  text: string
): GameTree {
  const coord = vertexToSgfCoord(vertex)
  return tree.mutate((draft: TreeDraft) => {
    clearMarkupInDraft(draft, nodeId, coord)
    draft.addToProperty(nodeId, 'LB', `${coord}:${text}`)
  })
}

export function removeMarkupAtVertex(
  tree: GameTree,
  nodeId: number,
  vertex: [number, number]
): GameTree {
  const coord = vertexToSgfCoord(vertex)
  return tree.mutate((draft: TreeDraft) => {
    clearMarkupInDraft(draft, nodeId, coord)
  })
}

export function setComment(tree: GameTree, nodeId: number, text: string): GameTree {
  return tree.mutate((draft: TreeDraft) => {
    draft.updateProperty(nodeId, 'C', text.length > 0 ? [text] : [])
  })
}

export function nextLabelText(node: NodeObject, mode: 'letter' | 'number'): string {
  const labels = node.data.LB ?? []
  const texts = labels.map((entry) => entry.slice(entry.indexOf(':') + 1))

  if (mode === 'letter') {
    const letterCount = texts.filter((text) => /^[A-Za-z]+$/.test(text)).length
    return letterCount < 26 ? String.fromCharCode(65 + letterCount) : String(letterCount + 1)
  }

  const numberCount = texts.filter((text) => /^\d+$/.test(text)).length
  return String(numberCount + 1)
}

export function emptyMarkerGrid(boardSize: number): (Marker | null)[][] {
  const grid: (Marker | null)[][] = []
  for (let y = 0; y < boardSize; y++) {
    grid.push(new Array(boardSize).fill(null))
  }
  return grid
}

export function buildAnnotationMarkerMap(node: NodeObject, boardSize: number): (Marker | null)[][] {
  const grid = emptyMarkerGrid(boardSize)

  for (const property of FIGURE_PROPERTIES) {
    for (const coord of node.data[property] ?? []) {
      const vertex = sgfCoordToVertex(coord)
      if (!vertex) continue
      grid[vertex[1]][vertex[0]] = { type: FIGURE_TO_MARKER_TYPE[property] }
    }
  }

  for (const entry of node.data.LB ?? []) {
    const separatorIndex = entry.indexOf(':')
    if (separatorIndex === -1) continue
    const coord = entry.slice(0, separatorIndex)
    const label = entry.slice(separatorIndex + 1)
    const vertex = sgfCoordToVertex(coord)
    if (!vertex) continue
    grid[vertex[1]][vertex[0]] = { type: 'label', label }
  }

  return grid
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run tests/renderer/board/annotations.test.ts`
Expected: PASS (all cases above green).

- [ ] **Step 5: Typecheck**

Run: `cd frontend && pnpm run typecheck:web`
Expected: no errors (in particular, no `no-explicit-any` violations — verify with `pnpm run lint` too).

- [ ] **Step 6: Commit**

```bash
cd frontend
git add src/renderer/src/board/annotations.ts tests/renderer/board/annotations.test.ts
git commit -m "feat: add SGF annotation mutation and marker-map helpers"
```

---

### Task 2: SGF serialization (`board/sgfSerializer.ts`)

**Files:**
- Create: `frontend/src/renderer/src/board/sgfSerializer.ts`
- Test: `frontend/tests/renderer/board/sgfSerializer.test.ts`

**Interfaces:**
- Consumes: `GameTree` (type), `parseSgf` (from `sgfLoader.ts`, test-only), `addFigureMarkup`/`addLabelMarkup`/`setComment` (from `annotations.ts`, Task 1, test-only).
- Produces (used by Task 8): `serializeTree(tree: GameTree): string`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/renderer/board/sgfSerializer.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import { addFigureMarkup, addLabelMarkup, setComment } from '@renderer/board/annotations'
import { serializeTree } from '@renderer/board/sgfSerializer'

describe('serializeTree', () => {
  it('serializes a plain tree back to equivalent SGF text', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9]KM[7.5];B[ee];W[ec])')

    const text = serializeTree(tree)

    expect(text).toContain('GM[1]')
    expect(text).toContain('SZ[9]')
    expect(text).toContain('B[ee]')
    expect(text).toContain('W[ec]')
  })

  it('round-trips annotations added via annotations.ts through parse -> mutate -> serialize -> parse', () => {
    const original = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(original)

    const withTriangle = addFigureMarkup(original, leaf.id, 'TR', [2, 2])
    const withLabel = addLabelMarkup(withTriangle, leaf.id, [4, 4], 'A')
    const withComment = setComment(withLabel, leaf.id, 'Хороший ход')

    const text = serializeTree(withComment)
    const reparsed = parseSgf(text)
    const reparsedLeaf = findMainLineLeaf(reparsed)

    expect(reparsedLeaf.data.TR).toEqual(['cc'])
    expect(reparsedLeaf.data.LB).toEqual(['ee:A'])
    expect(reparsedLeaf.data.C).toEqual(['Хороший ход'])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm exec vitest run tests/renderer/board/sgfSerializer.test.ts`
Expected: FAIL — `Cannot find module '@renderer/board/sgfSerializer'`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/renderer/src/board/sgfSerializer.ts`:

```ts
import * as sgf from '@sabaki/sgf'
import type GameTree from '@sabaki/immutable-gametree'

export function serializeTree(tree: GameTree): string {
  return sgf.stringify(tree.root)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm exec vitest run tests/renderer/board/sgfSerializer.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd frontend
git add src/renderer/src/board/sgfSerializer.ts tests/renderer/board/sgfSerializer.test.ts
git commit -m "feat: add SGF tree serialization"
```

---

### Task 3: State — `currentFilePath`, `isDirty`, `currentNode`

**Files:**
- Modify: `frontend/src/renderer/src/state/appState.ts` (full file currently 32 lines)
- Test: `frontend/tests/renderer/state/appState.test.ts` (extend existing file)

**Interfaces:**
- Consumes: `NodeObject` (type, from `sgfLoader.ts`).
- Produces (used by Tasks 4, 5, 6, 8, 9): `currentFilePath: Signal<string | null>`; `isDirty: Signal<boolean>`; `currentNode: ReadonlySignal<NodeObject | null>`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/tests/renderer/state/appState.test.ts` (add this import to the existing `import` block at the top: `currentFilePath, isDirty, currentNode` alongside the already-imported signals), then add at the end of the file:

```ts
describe('currentFilePath + isDirty', () => {
  it('default to null and false', () => {
    expect(currentFilePath.value).toBeNull()
    expect(isDirty.value).toBe(false)
  })

  it('can be set independently of the tree/node signals', () => {
    currentFilePath.value = 'C:/games/example.sgf'
    isDirty.value = true

    expect(currentFilePath.value).toBe('C:/games/example.sgf')
    expect(isDirty.value).toBe(true)

    currentFilePath.value = null
    isDirty.value = false
  })
})

describe('currentNode', () => {
  it('is null when no tree is loaded', () => {
    expect(currentNode.value).toBeNull()
  })

  it('derives the raw node object for the current node id', () => {
    const tree = parseSgf(fixtureContent)
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    expect(currentNode.value?.id).toBe(leaf.id)
    expect(currentNode.value?.data.B).toEqual(['ee'])
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && pnpm exec vitest run tests/renderer/state/appState.test.ts`
Expected: FAIL — `currentFilePath`/`isDirty`/`currentNode` are not exported.

- [ ] **Step 3: Write the implementation**

Modify `frontend/src/renderer/src/state/appState.ts` — add these imports/exports (the full new file):

```ts
import { signal, computed } from '@preact/signals'
import type GameTree from '@sabaki/immutable-gametree'
import type { NodeObject } from '../board/sgfLoader'
import { movesFromRootToNode } from '../board/sgfLoader'
import { boardPositionFromMoves } from '../board/boardPosition'
import type { AnalyzeResponse } from '../ipc/client'

export const currentTree = signal<GameTree | null>(null)
export const currentNodeId = signal<number | null>(null)
export const analysisByTurn = signal<Map<number, AnalyzeResponse>>(new Map())
export const streamStatus = signal<'idle' | 'streaming' | 'done' | 'error'>('idle')
export const streamError = signal<string | null>(null)
export const currentFilePath = signal<string | null>(null)
export const isDirty = signal<boolean>(false)

export const currentBoardPosition = computed(() => {
  const tree = currentTree.value
  const nodeId = currentNodeId.value
  if (!tree || nodeId === null) return null
  return boardPositionFromMoves(tree, nodeId)
})

export const currentNode = computed<NodeObject | null>(() => {
  const tree = currentTree.value
  const nodeId = currentNodeId.value
  if (!tree || nodeId === null) return null
  return tree.get(nodeId) as NodeObject | null
})

export const currentTurnNumber = computed(() => {
  const tree = currentTree.value
  const nodeId = currentNodeId.value
  if (!tree || nodeId === null) return null
  return movesFromRootToNode(tree, nodeId).length
})

export const currentMoveAnalysis = computed(() => {
  const nodeId = currentNodeId.value
  if (nodeId === null) return null
  return analysisByTurn.value.get(nodeId) ?? null
})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run tests/renderer/state/appState.test.ts`
Expected: PASS.

- [ ] **Step 5: Typecheck**

Run: `cd frontend && pnpm run typecheck:web`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
cd frontend
git add src/renderer/src/state/appState.ts tests/renderer/state/appState.test.ts
git commit -m "feat: add currentFilePath, isDirty and currentNode state"
```

---

### Task 4: Render existing/user markup on the board, with priority over PV labels

**Files:**
- Modify: `frontend/src/renderer/src/board/BoardView.tsx` (full file currently 163 lines)
- Test: `frontend/tests/renderer/components/BoardView.test.tsx` (extend existing file)

**Interfaces:**
- Consumes: `buildAnnotationMarkerMap`, `emptyMarkerGrid` (from `annotations.ts`, Task 1), `currentNode` (from `appState.ts`, Task 3), `Marker` (type, from `@sabaki/shudan`).
- Produces: `buildMarkerMap` signature changes from `(lastMoveVertex, suggestedMoves, boardSize) => (BoardMarker|null)[][] | undefined` to `(lastMoveVertex, suggestedMoves, boardSize, userMarkerMap) => (Marker|null)[][]` (always returns a full grid now, never `undefined`) — this is an internal (non-exported) function, no other module imports it, so this is not a breaking change for any other file.

This task only makes existing/foreign markup **visible**; it does not yet let the user place new markup (that's Task 5).

- [ ] **Step 1: Write the failing tests**

Add to `frontend/tests/renderer/components/BoardView.test.tsx` (add these `it` blocks inside the existing `describe('BoardView', ...)` block, after the last existing test):

```ts
  it('renders existing figure and label markup from the SGF node', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]TR[gg]LB[cc:A])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    const { container } = render(<BoardView />)

    const markers = Array.from(container.querySelectorAll('.shudan-marker'))
    expect(markers.some((el) => el.querySelector('path'))).toBe(true) // triangle renders as an svg <path>
    expect(markers.some((el) => el.textContent === 'A')).toBe(true)
  })

  it('lets user markup take priority over a PV candidate label at the same vertex', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]LB[cc:A])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    analysisByTurn.value = new Map([
      [
        1,
        {
          id: 'x',
          // 'cc' (sgf) -> vertex [2,2] -> GTP 'C7' on a 9x9 board (row = 9 - 2 = 7)
          moveInfos: [
            { move: 'C7', winrate: 0.6, scoreLead: 1, visits: 100, prior: 0.5, pv: ['C7'] }
          ],
          rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 }
        }
      ]
    ])

    const { container } = render(<BoardView />)

    const markers = Array.from(container.querySelectorAll('.shudan-marker'))
    // The user's label 'A' wins; the PV rank label '1' must not appear at all,
    // since its only candidate vertex is occupied by the user's own markup.
    expect(markers.some((el) => el.textContent === 'A')).toBe(true)
    expect(markers.some((el) => el.textContent === '1')).toBe(false)
  })
```

Also add these two imports to the top `import` list already in that file: `analysisByTurn` (from `@renderer/state/appState`, alongside `currentTree`, `currentNodeId`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/BoardView.test.tsx`
Expected: FAIL — no figure/label markers render yet (current `buildMarkerMap` only knows about last-move/PV markers).

- [ ] **Step 3: Write the implementation**

In `frontend/src/renderer/src/board/BoardView.tsx`:

Replace the import block (lines 1-7) with:
```tsx
import { useEffect, useRef, useState } from 'preact/hooks'
import { BoundedGoban } from '@sabaki/shudan'
import '@sabaki/shudan/css/goban.css'
import { currentBoardPosition, currentMoveAnalysis, currentNode } from '../state/appState'
import { GTP_COLUMNS } from './gtpColumns'
import { buildAnnotationMarkerMap, emptyMarkerGrid } from './annotations'
import type { JSX } from 'preact'
import type { Marker } from '@sabaki/shudan'
import type { MoveInfo } from '../ipc/client'
```

Replace the `type BoardMarker = ...` line and the `buildMarkerMap` function (originally lines 48-72) with:
```tsx
function buildMarkerMap(
  lastMoveVertex: [number, number] | null,
  suggestedMoves: MoveInfo[] | undefined,
  boardSize: number,
  userMarkerMap: (Marker | null)[][]
): (Marker | null)[][] {
  // Start from a copy of the user's own markup (figures/labels from the SGF
  // node) — it belongs to the position and always wins. KataGo-derived
  // overlays below only fill vertices the user hasn't already marked.
  const grid = userMarkerMap.map((row) => [...row])

  if (lastMoveVertex && !grid[lastMoveVertex[1]][lastMoveVertex[0]]) {
    grid[lastMoveVertex[1]][lastMoveVertex[0]] = { type: 'point' }
  }
  suggestedMoves?.slice(0, MAX_SUGGESTED_MOVES).forEach((info, index) => {
    const vertex = gtpToVertex(info.move, boardSize)
    if (!vertex || grid[vertex[1]][vertex[0]]) return
    grid[vertex[1]][vertex[0]] = { type: 'label', label: String(index + 1) }
  })
  return grid
}
```

In the `BoardView` component body, replace:
```tsx
  const markerMap = buildMarkerMap(
    position.lastMoveVertex,
    showPv ? analysis?.moveInfos : undefined,
    position.boardSize
  )
```
with:
```tsx
  const node = currentNode.value
  const userMarkerMap = node
    ? buildAnnotationMarkerMap(node, position.boardSize)
    : emptyMarkerGrid(position.boardSize)
  const markerMap = buildMarkerMap(
    position.lastMoveVertex,
    showPv ? analysis?.moveInfos : undefined,
    position.boardSize,
    userMarkerMap
  )
```

No other changes in this file for this task (the `heatMap` line above it, and the `<BoundedGoban ... markerMap={markerMap} .../>` usage below, stay as they are — `markerMap`'s new type `(Marker|null)[][]` is assignment-compatible with the prop, which already expected `Marker[][]`-shaped data).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/BoardView.test.tsx`
Expected: PASS (all existing + 2 new tests).

- [ ] **Step 5: Typecheck**

Run: `cd frontend && pnpm run typecheck:web`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
cd frontend
git add src/renderer/src/board/BoardView.tsx tests/renderer/components/BoardView.test.tsx
git commit -m "feat: render SGF figure/label markup on the board, taking priority over PV labels"
```

---

### Task 5: Annotation toolbar + click-to-place/erase

**Files:**
- Create: `frontend/src/renderer/src/state/annotationToolState.ts`
- Modify: `frontend/src/renderer/src/board/BoardView.tsx`
- Modify: `frontend/src/renderer/assets/main.css` (append new rules)
- Test: `frontend/tests/renderer/state/annotationToolState.test.ts`
- Test: `frontend/tests/renderer/components/BoardView.test.tsx` (extend)

**Interfaces:**
- Consumes: `AnnotationTool` (type, from `annotations.ts`), `nextLabelText`, `addFigureMarkup`, `addLabelMarkup`, `removeMarkupAtVertex` (from `annotations.ts`), `currentTree`, `currentNodeId`, `currentNode`, `isDirty` (from `appState.ts`).
- Produces: `selectedAnnotationTool: Signal<AnnotationTool | null>`; `labelMode: Signal<'letter' | 'number'>`; `labelTextOverride: Signal<string | null>`; `pendingLabelText: ReadonlySignal<string>` (all in `state/annotationToolState.ts`); a working `onVertexClick` on the board.

- [ ] **Step 1: Write the failing test for the state module**

Create `frontend/tests/renderer/state/annotationToolState.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import { currentTree, currentNodeId } from '@renderer/state/appState'
import {
  selectedAnnotationTool,
  labelMode,
  labelTextOverride,
  pendingLabelText
} from '@renderer/state/annotationToolState'

beforeEach(() => {
  currentTree.value = null
  currentNodeId.value = null
  selectedAnnotationTool.value = null
  labelMode.value = 'letter'
  labelTextOverride.value = null
})

describe('pendingLabelText', () => {
  it('is empty when there is no current node', () => {
    expect(pendingLabelText.value).toBe('')
  })

  it('suggests the next label for the current node when no override is set', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]LB[aa:A])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    expect(pendingLabelText.value).toBe('B')
  })

  it('uses number mode when selected', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    labelMode.value = 'number'

    expect(pendingLabelText.value).toBe('1')
  })

  it('prefers a manual override over the auto-suggestion', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    labelTextOverride.value = 'X'

    expect(pendingLabelText.value).toBe('X')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm exec vitest run tests/renderer/state/annotationToolState.test.ts`
Expected: FAIL — `Cannot find module '@renderer/state/annotationToolState'`.

- [ ] **Step 3: Write the state module**

Create `frontend/src/renderer/src/state/annotationToolState.ts`:

```ts
import { signal, computed } from '@preact/signals'
import type { AnnotationTool } from '../board/annotations'
import { nextLabelText } from '../board/annotations'
import { currentNode } from './appState'

export const selectedAnnotationTool = signal<AnnotationTool | null>(null)
export const labelMode = signal<'letter' | 'number'>('letter')
// Text the user manually typed for the next label placement, overriding the
// auto-suggestion below. Reset to null after each placement so the next
// suggestion is recomputed from the (now updated) tree.
export const labelTextOverride = signal<string | null>(null)

export const pendingLabelText = computed(() => {
  if (labelTextOverride.value !== null) return labelTextOverride.value
  const node = currentNode.value
  if (!node) return ''
  return nextLabelText(node, labelMode.value)
})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm exec vitest run tests/renderer/state/annotationToolState.test.ts`
Expected: PASS.

- [ ] **Step 5: Write the failing tests for the toolbar/click UI**

Add to `frontend/tests/renderer/components/BoardView.test.tsx` (new imports at top: `fireEvent` already imported; add `selectedAnnotationTool, labelTextOverride` from `@renderer/state/annotationToolState` to the imports, and reset them in the existing `afterEach`):

```ts
// Extend the existing afterEach(() => {...}) block to also reset:
//   selectedAnnotationTool.value = null
//   labelTextOverride.value = null

  it('places a triangle at the clicked vertex when the triangle tool is selected', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    selectedAnnotationTool.value = 'TR'

    const { container } = render(<BoardView />)
    const vertex = container.querySelector('[data-x="2"][data-y="2"]')
    fireEvent.click(vertex as Element)

    expect((currentTree.value!.get(leaf.id) as { data: Record<string, string[]> }).data.TR).toEqual([
      'cc'
    ])
  })

  it('places the pending label text and then resets the override for the next placement', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    selectedAnnotationTool.value = 'LB'
    labelTextOverride.value = 'Z'

    const { container } = render(<BoardView />)
    const vertex = container.querySelector('[data-x="0"][data-y="0"]')
    fireEvent.click(vertex as Element)

    expect((currentTree.value!.get(leaf.id) as { data: Record<string, string[]> }).data.LB).toEqual([
      'aa:Z'
    ])
    expect(labelTextOverride.value).toBeNull()
  })

  it('erases markup at the clicked vertex when the eraser tool is selected', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]MA[cc])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    selectedAnnotationTool.value = 'erase'

    const { container } = render(<BoardView />)
    const vertex = container.querySelector('[data-x="2"][data-y="2"]')
    fireEvent.click(vertex as Element)

    expect(
      (currentTree.value!.get(leaf.id) as { data: Record<string, string[]> }).data.MA
    ).toBeUndefined()
  })

  it('does nothing when no annotation tool is selected', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    const { container } = render(<BoardView />)
    const vertex = container.querySelector('[data-x="2"][data-y="2"]')
    fireEvent.click(vertex as Element)

    expect((currentTree.value!.get(leaf.id) as { data: Record<string, string[]> }).data.TR).toBeUndefined()
  })

  it('renders one button per annotation tool in the toolbar', () => {
    const { container } = render(<BoardView />)
    const buttons = container.querySelectorAll('.board-view__annotation-toolbar button')
    // Triangle, square, circle, cross, label, eraser
    expect(buttons.length).toBe(6)
  })
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/BoardView.test.tsx`
Expected: FAIL — no `onVertexClick` handler, no `.board-view__annotation-toolbar` in the DOM yet.

- [ ] **Step 7: Write the implementation**

In `frontend/src/renderer/src/board/BoardView.tsx`, add to the import block (after the `annotations` import from Task 4):
```tsx
import {
  addFigureMarkup,
  addLabelMarkup,
  removeMarkupAtVertex,
  buildAnnotationMarkerMap,
  emptyMarkerGrid
} from './annotations'
import type { AnnotationTool } from './annotations'
import { currentTree, currentNodeId, isDirty } from '../state/appState'
import {
  selectedAnnotationTool,
  labelMode,
  labelTextOverride,
  pendingLabelText
} from '../state/annotationToolState'
```
(Replace the Task 4 import line `import { buildAnnotationMarkerMap, emptyMarkerGrid } from './annotations'` with the combined one above, since it now needs more exports from the same module.)

Add this constant near the top of the file (after `MAX_SUGGESTED_MOVES`):
```tsx
const ANNOTATION_TOOLS: { tool: AnnotationTool; label: string }[] = [
  { tool: 'TR', label: '△' },
  { tool: 'SQ', label: '□' },
  { tool: 'CR', label: '○' },
  { tool: 'MA', label: '✕' },
  { tool: 'LB', label: 'Метка' },
  { tool: 'erase', label: 'Ластик' }
]
```

Add this function near `gtpToVertex` (module scope, not inside the component):
```tsx
function applyAnnotationTool(tool: AnnotationTool, vertex: [number, number]): void {
  const tree = currentTree.value
  const nodeId = currentNodeId.value
  if (!tree || nodeId === null) return

  if (tool === 'erase') {
    currentTree.value = removeMarkupAtVertex(tree, nodeId, vertex)
  } else if (tool === 'LB') {
    currentTree.value = addLabelMarkup(tree, nodeId, vertex, pendingLabelText.value)
    labelTextOverride.value = null
  } else {
    currentTree.value = addFigureMarkup(tree, nodeId, tool, vertex)
  }
  isDirty.value = true
}
```

In the `BoardView` component, add a click handler and the toolbar markup. Replace the existing:
```tsx
      <div class="board-view__goban" ref={containerRef}>
        <BoundedGoban
          signMap={position.signMap}
          heatMap={heatMap}
          markerMap={markerMap}
          maxWidth={maxWidth}
          maxHeight={maxHeight}
          onVertexPointerEnter={(_event, vertex) => setHoveredVertex(vertex as [number, number])}
          onVertexPointerLeave={() => setHoveredVertex(null)}
        />
      </div>
```
with:
```tsx
      <div class="board-view__annotation-toolbar">
        {ANNOTATION_TOOLS.map(({ tool, label }) => (
          <button
            key={tool}
            type="button"
            class={
              selectedAnnotationTool.value === tool
                ? 'board-view__annotation-tool board-view__annotation-tool--active'
                : 'board-view__annotation-tool'
            }
            onClick={() =>
              (selectedAnnotationTool.value = selectedAnnotationTool.value === tool ? null : tool)
            }
          >
            {label}
          </button>
        ))}
        {selectedAnnotationTool.value === 'LB' && (
          <>
            <label>
              <input
                type="radio"
                checked={labelMode.value === 'letter'}
                onChange={() => (labelMode.value = 'letter')}
              />
              Буквы
            </label>
            <label>
              <input
                type="radio"
                checked={labelMode.value === 'number'}
                onChange={() => (labelMode.value = 'number')}
              />
              Цифры
            </label>
            <input
              class="board-view__label-input"
              type="text"
              value={pendingLabelText.value}
              onInput={(event) => (labelTextOverride.value = (event.target as HTMLInputElement).value)}
            />
          </>
        )}
      </div>
      <div class="board-view__goban" ref={containerRef}>
        <BoundedGoban
          signMap={position.signMap}
          heatMap={heatMap}
          markerMap={markerMap}
          maxWidth={maxWidth}
          maxHeight={maxHeight}
          onVertexClick={(_event, vertex) => {
            const tool = selectedAnnotationTool.value
            if (!tool) return
            applyAnnotationTool(tool, vertex as [number, number])
          }}
          onVertexPointerEnter={(_event, vertex) => setHoveredVertex(vertex as [number, number])}
          onVertexPointerLeave={() => setHoveredVertex(null)}
        />
      </div>
```

Append to `frontend/src/renderer/assets/main.css` (after the existing `.board-view__goban { ... }` rule):
```css
.board-view__annotation-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  font-size: 13px;
  flex-shrink: 0;
}
.board-view__annotation-tool {
  background: none;
  border: 1px solid var(--border-color, #333);
  border-radius: 4px;
  color: var(--ev-c-text-2, #888);
  padding: 2px 8px;
  cursor: pointer;
}
.board-view__annotation-tool--active {
  color: var(--ev-c-text-1, #fff);
  border-color: var(--ev-c-text-2, #888);
}
.board-view__label-input {
  width: 3em;
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/BoardView.test.tsx tests/renderer/state/annotationToolState.test.ts`
Expected: PASS.

- [ ] **Step 9: Typecheck**

Run: `cd frontend && pnpm run typecheck:web`
Expected: no errors.

- [ ] **Step 10: Commit**

```bash
cd frontend
git add src/renderer/src/state/annotationToolState.ts src/renderer/src/board/BoardView.tsx src/renderer/assets/main.css tests/renderer/state/annotationToolState.test.ts tests/renderer/components/BoardView.test.tsx
git commit -m "feat: add annotation toolbar with click-to-place/erase on the board"
```

---

### Task 6: Comment tab (`analysis/AnnotationPanel.tsx`)

**Files:**
- Create: `frontend/src/renderer/src/analysis/AnnotationPanel.tsx`
- Modify: `frontend/src/renderer/src/analysis/AnalysisPanel.tsx` (full file currently 39 lines)
- Modify: `frontend/src/renderer/assets/main.css` (append)
- Test: `frontend/tests/renderer/components/AnnotationPanel.test.tsx`
- Test: `frontend/tests/renderer/components/AnalysisPanel.test.tsx` (extend existing file)

**Interfaces:**
- Consumes: `currentTree`, `currentNodeId`, `currentNode`, `isDirty` (from `appState.ts`), `setComment` (from `annotations.ts`).
- Produces: `AnnotationPanel` component (rendered as the third `AnalysisPanel` tab).

- [ ] **Step 1: Write the failing test for `AnnotationPanel`**

Create `frontend/tests/renderer/components/AnnotationPanel.test.tsx`:

```tsx
import { describe, it, expect, afterEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/preact'
import { AnnotationPanel } from '@renderer/analysis/AnnotationPanel'
import { currentTree, currentNodeId, isDirty } from '@renderer/state/appState'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'

afterEach(() => {
  currentTree.value = null
  currentNodeId.value = null
  isDirty.value = false
})

describe('AnnotationPanel', () => {
  it('is disabled with no game loaded', () => {
    const { getByRole } = render(<AnnotationPanel />)
    expect((getByRole('textbox') as HTMLTextAreaElement).disabled).toBe(true)
  })

  it('shows the current node comment and lets the user edit it', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]C[Исходный комментарий])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    const { getByRole } = render(<AnnotationPanel />)
    const textarea = getByRole('textbox') as HTMLTextAreaElement
    expect(textarea.value).toBe('Исходный комментарий')
  })

  it('commits the edited comment to the tree on blur, not on every keystroke', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    const { getByRole } = render(<AnnotationPanel />)
    const textarea = getByRole('textbox') as HTMLTextAreaElement

    fireEvent.input(textarea, { target: { value: 'Новый комментарий' } })
    expect((currentTree.value!.get(leaf.id) as { data: Record<string, string[]> }).data.C).toBeUndefined()

    fireEvent.blur(textarea)
    expect((currentTree.value!.get(leaf.id) as { data: Record<string, string[]> }).data.C).toEqual([
      'Новый комментарий'
    ])
    expect(isDirty.value).toBe(true)
  })

  it('reloads the textarea contents when the current node changes', async () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]C[Первый];W[ec]C[Второй])')
    const root = tree.root as { children: { id: number }[] }
    const bMoveNode = root.children[0]
    const wMoveNode = (bMoveNode as unknown as { children: { id: number }[] }).children[0]
    currentTree.value = tree
    currentNodeId.value = bMoveNode.id

    const { getByRole } = render(<AnnotationPanel />)
    const textarea = getByRole('textbox') as HTMLTextAreaElement
    expect(textarea.value).toBe('Первый')

    currentNodeId.value = wMoveNode.id
    await waitFor(() => expect(textarea.value).toBe('Второй'))
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/AnnotationPanel.test.tsx`
Expected: FAIL — `Cannot find module '@renderer/analysis/AnnotationPanel'`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/renderer/src/analysis/AnnotationPanel.tsx`:

```tsx
import { useEffect, useState } from 'preact/hooks'
import type { JSX } from 'preact'
import { currentTree, currentNodeId, isDirty } from '../state/appState'
import { setComment } from '../board/annotations'

export function AnnotationPanel(): JSX.Element {
  const [text, setText] = useState('')
  const nodeId = currentNodeId.value

  useEffect(() => {
    const tree = currentTree.value
    if (!tree || nodeId === null) {
      setText('')
      return
    }
    const node = tree.get(nodeId) as { data: Record<string, string[]> } | null
    setText(node?.data.C?.[0] ?? '')
  }, [nodeId])

  function handleBlur(event: Event): void {
    const tree = currentTree.value
    if (!tree || nodeId === null) return
    currentTree.value = setComment(tree, nodeId, (event.target as HTMLTextAreaElement).value)
    isDirty.value = true
  }

  return (
    <div class="annotation-panel">
      <textarea
        class="annotation-panel__comment"
        placeholder="Комментарий к этому ходу"
        value={text}
        disabled={!currentTree.value || nodeId === null}
        onInput={(event) => setText((event.target as HTMLTextAreaElement).value)}
        onBlur={handleBlur}
      />
    </div>
  )
}
```

Append to `frontend/src/renderer/assets/main.css` (after the existing `.llm-explanation-panel*` rules):
```css
.annotation-panel {
  padding: 8px;
}
.annotation-panel__comment {
  width: 100%;
  min-height: 120px;
  box-sizing: border-box;
  resize: vertical;
  font-family: inherit;
  font-size: 13px;
  background: var(--color-surface, #0e1223);
  color: var(--ev-c-text-1, #fff);
  border: 1px solid var(--border-color, #333);
  border-radius: 4px;
  padding: 6px;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/AnnotationPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Write the failing test for the third `AnalysisPanel` tab**

Add to `frontend/tests/renderer/components/AnalysisPanel.test.tsx` (read the existing file first for its current import/test style, then add):

```tsx
  it('shows an Разметка tab that renders the AnnotationPanel', () => {
    const { getByText, container } = render(<AnalysisPanel />)
    fireEvent.click(getByText('Разметка'))
    expect(container.querySelector('.annotation-panel')).toBeTruthy()
  })
```

(Add `fireEvent` to that file's existing `@testing-library/preact` import if not already imported.)

- [ ] **Step 6: Run test to verify it fails**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/AnalysisPanel.test.tsx`
Expected: FAIL — no "Разметка" tab exists yet.

- [ ] **Step 7: Wire the third tab**

Replace the full contents of `frontend/src/renderer/src/analysis/AnalysisPanel.tsx`:

```tsx
import { useState } from 'preact/hooks'
import type { JSX } from 'preact'
import { WinrateChart } from './WinrateChart'
import { LlmExplanationPanel } from './LlmExplanationPanel'
import { AnnotationPanel } from './AnnotationPanel'

const TABS = [
  { id: 'katago' as const, label: 'KataGo' },
  { id: 'llm' as const, label: 'LLM' },
  { id: 'annotation' as const, label: 'Разметка' }
]

export function AnalysisPanel(): JSX.Element {
  const [tab, setTab] = useState<'katago' | 'llm' | 'annotation'>('katago')

  return (
    <div class="analysis-panel">
      <div class="analysis-panel__tabs">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            class={
              tab === id ? 'analysis-panel__tab analysis-panel__tab--active' : 'analysis-panel__tab'
            }
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === 'katago' && <WinrateChart />}
      {tab === 'llm' && <LlmExplanationPanel />}
      {tab === 'annotation' && <AnnotationPanel />}
    </div>
  )
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/AnalysisPanel.test.tsx tests/renderer/components/AnnotationPanel.test.tsx`
Expected: PASS.

- [ ] **Step 9: Typecheck**

Run: `cd frontend && pnpm run typecheck:web`
Expected: no errors.

- [ ] **Step 10: Commit**

```bash
cd frontend
git add src/renderer/src/analysis/AnnotationPanel.tsx src/renderer/src/analysis/AnalysisPanel.tsx src/renderer/assets/main.css tests/renderer/components/AnnotationPanel.test.tsx tests/renderer/components/AnalysisPanel.test.tsx
git commit -m "feat: add Разметка tab with per-node comment editing"
```

---

### Task 7: Main-process file save (`file:save`, `file:save-as`)

**Files:**
- Create: `frontend/src/main/fileIO.ts`
- Modify: `frontend/src/main/index.ts` (full file currently 104 lines)
- Modify: `frontend/src/preload/index.ts` (full file currently 29 lines)
- Modify: `frontend/src/renderer/src/global.d.ts` (full file currently 13 lines)
- Test: `frontend/tests/main/fileIO.test.ts`

**Interfaces:**
- Consumes: Node's `node:fs/promises` (`writeFile`), Electron's `dialog` (`showSaveDialog`).
- Produces (used by Task 8): IPC channels `file:save(path: string, content: string): Promise<void>` and `file:save-as(defaultPath: string | undefined, content: string): Promise<{path: string} | {canceled: true}>`, exposed to renderer as `window.baduk.saveFile(path, content): Promise<void>` and `window.baduk.saveFileAs(defaultPath, content): Promise<{path: string} | {canceled: true}>`.

This project has no existing tests for `main/index.ts` itself (only for the Electron-free `backendConnection.ts`) — it stays thin, untested wiring. All new logic worth testing goes in `fileIO.ts`, following that same split.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/main/fileIO.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { writeFile } from 'node:fs/promises'
import { dialog } from 'electron'
import { saveFile, saveFileAs } from '../../src/main/fileIO'

vi.mock('node:fs/promises', () => ({ writeFile: vi.fn() }))
vi.mock('electron', () => ({ dialog: { showSaveDialog: vi.fn() } }))

beforeEach(() => {
  vi.mocked(writeFile).mockReset().mockResolvedValue(undefined)
  vi.mocked(dialog.showSaveDialog).mockReset()
})

describe('saveFile', () => {
  it('writes the given content to the given path as utf-8', async () => {
    await saveFile('/games/example.sgf', '(;GM[1])')

    expect(writeFile).toHaveBeenCalledWith('/games/example.sgf', '(;GM[1])', 'utf-8')
  })

  it('propagates a write failure', async () => {
    vi.mocked(writeFile).mockRejectedValue(new Error('EACCES: permission denied'))

    await expect(saveFile('/readonly/example.sgf', '(;GM[1])')).rejects.toThrow(
      'permission denied'
    )
  })
})

describe('saveFileAs', () => {
  it('opens a save dialog filtered to .sgf and writes the chosen path', async () => {
    vi.mocked(dialog.showSaveDialog).mockResolvedValue({
      canceled: false,
      filePath: '/games/new-name.sgf'
    } as Awaited<ReturnType<typeof dialog.showSaveDialog>>)

    const result = await saveFileAs('/games/example.sgf', '(;GM[1])')

    expect(dialog.showSaveDialog).toHaveBeenCalledWith(
      expect.objectContaining({
        defaultPath: '/games/example.sgf',
        filters: [{ name: 'SGF', extensions: ['sgf'] }]
      })
    )
    expect(writeFile).toHaveBeenCalledWith('/games/new-name.sgf', '(;GM[1])', 'utf-8')
    expect(result).toEqual({ path: '/games/new-name.sgf' })
  })

  it('returns canceled without writing when the dialog is dismissed', async () => {
    vi.mocked(dialog.showSaveDialog).mockResolvedValue({
      canceled: true,
      filePath: undefined
    } as Awaited<ReturnType<typeof dialog.showSaveDialog>>)

    const result = await saveFileAs(undefined, '(;GM[1])')

    expect(result).toEqual({ canceled: true })
    expect(writeFile).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && pnpm exec vitest run tests/main/fileIO.test.ts`
Expected: FAIL — `Cannot find module '../../src/main/fileIO'`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/main/fileIO.ts`:

```ts
import { writeFile } from 'node:fs/promises'
import { dialog } from 'electron'

export async function saveFile(path: string, content: string): Promise<void> {
  await writeFile(path, content, 'utf-8')
}

export async function saveFileAs(
  defaultPath: string | undefined,
  content: string
): Promise<{ path: string } | { canceled: true }> {
  const result = await dialog.showSaveDialog({
    defaultPath,
    filters: [{ name: 'SGF', extensions: ['sgf'] }]
  })
  if (result.canceled || !result.filePath) return { canceled: true }
  await writeFile(result.filePath, content, 'utf-8')
  return { path: result.filePath }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run tests/main/fileIO.test.ts`
Expected: PASS.

- [ ] **Step 5: Wire the IPC handlers (untested, thin — matches this project's existing `main/index.ts` convention)**

Modify `frontend/src/main/index.ts` — add to the top import (currently `import { app, shell, BrowserWindow, ipcMain } from 'electron'`):
```ts
import { app, shell, BrowserWindow, ipcMain } from 'electron'
```
becomes:
```ts
import { app, shell, BrowserWindow, ipcMain } from 'electron'
import { saveFile, saveFileAs } from './fileIO'
```

In the `app.whenReady().then(() => {...})` block, right after the existing `ipcMain.handle('backend:get-connection', () => getBackendConnection())` line, add:
```ts
  ipcMain.handle('file:save', (_event, path: string, content: string) => saveFile(path, content))
  ipcMain.handle('file:save-as', (_event, defaultPath: string | undefined, content: string) =>
    saveFileAs(defaultPath, content)
  )
```

- [ ] **Step 6: Expose the new IPC calls in preload**

Modify `frontend/src/preload/index.ts` — replace:
```ts
const baduk = {
  getBackendConnection: () => ipcRenderer.invoke('backend:get-connection')
}
```
with:
```ts
const baduk = {
  getBackendConnection: () => ipcRenderer.invoke('backend:get-connection'),
  saveFile: (path: string, content: string) => ipcRenderer.invoke('file:save', path, content),
  saveFileAs: (defaultPath: string | undefined, content: string) =>
    ipcRenderer.invoke('file:save-as', defaultPath, content)
}
```

- [ ] **Step 7: Extend the `window.baduk` type declaration**

Modify `frontend/src/renderer/src/global.d.ts` — replace its full contents:
```ts
export interface BackendConnection {
  port: number
  token: string
}

export type SaveFileAsResult = { path: string } | { canceled: true }

declare global {
  interface Window {
    baduk: {
      getBackendConnection(): Promise<BackendConnection>
      saveFile(path: string, content: string): Promise<void>
      saveFileAs(defaultPath: string | undefined, content: string): Promise<SaveFileAsResult>
    }
  }
}
```

- [ ] **Step 8: Typecheck both processes**

Run: `cd frontend && pnpm run typecheck`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
cd frontend
git add src/main/fileIO.ts src/main/index.ts src/preload/index.ts src/renderer/src/global.d.ts tests/main/fileIO.test.ts
git commit -m "feat: add main-process file save/save-as IPC"
```

---

### Task 8: Renderer save flow — header, Save/Save As, drag&drop path capture

**Files:**
- Modify: `frontend/src/renderer/src/App.tsx` (full file currently 135 lines)
- Modify: `frontend/src/renderer/assets/main.css` (append)
- Test: `frontend/tests/renderer/components/App.test.tsx` (extend existing file)

**Interfaces:**
- Consumes: `currentFilePath`, `isDirty` (from `appState.ts`, Task 3), `serializeTree` (from `sgfSerializer.ts`, Task 2), `window.baduk.saveFile`/`saveFileAs` (from Task 7), `window.electron.webUtils.getPathForFile` (already available, `@electron-toolkit/preload`).
- Produces: `saveCurrentGame(): Promise<void>` and `saveCurrentGameAs(): Promise<void>` (exported from `App.tsx` for tests), `saveError: Signal<string | null>` (exported from `App.tsx`), a header UI showing the current filename + dirty indicator + Save/Save As buttons.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/tests/renderer/components/App.test.tsx` (read the existing file first — it already imports `App`, `loadGame`, `sgfError` from `@renderer/App` and several `appState` signals in its `afterEach`; extend both). Add `saveCurrentGame, saveError` to the `@renderer/App` import and `currentFilePath, isDirty` to the `@renderer/state/appState` import; extend the existing `afterEach` to also reset `currentFilePath.value = null`, `isDirty.value = false`, `saveError.value = null`. Then add:

```tsx
describe('save flow', () => {
  it('shows "Без файла" and disables Save/Save As with no game loaded', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' })
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    const saveButton = getByText('Сохранить') as HTMLButtonElement
    expect(saveButton.disabled).toBe(true)
  })

  it('captures the dropped file path via window.electron.webUtils and marks the game dirty after an edit, then Save writes to that path', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      saveFile: vi.fn().mockResolvedValue(undefined),
      saveFileAs: vi.fn()
    }
    ;(window as any).electron = {
      webUtils: { getPathForFile: vi.fn().mockReturnValue('/games/example.sgf') }
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    loadGame('(;GM[1]FF[4]SZ[9];B[ee])', '/games/example.sgf')
    await waitFor(() => expect(getByText(/example\.sgf/)).toBeTruthy())

    isDirty.value = true
    const saveButton = getByText('Сохранить') as HTMLButtonElement
    expect(saveButton.disabled).toBe(false)

    fireEvent.click(saveButton)
    await waitFor(() => expect((window as any).baduk.saveFile).toHaveBeenCalledWith(
      '/games/example.sgf',
      expect.stringContaining('GM[1]')
    ))
    await waitFor(() => expect(isDirty.value).toBe(false))
  })

  it('falls back to Save As when there is no known file path yet', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      saveFile: vi.fn(),
      saveFileAs: vi.fn().mockResolvedValue({ path: '/games/chosen.sgf' })
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    loadGame('(;GM[1]FF[4]SZ[9];B[ee])')
    isDirty.value = true

    fireEvent.click(getByText('Сохранить'))
    await waitFor(() =>
      expect((window as any).baduk.saveFileAs).toHaveBeenCalledWith(undefined, expect.any(String))
    )
    await waitFor(() => expect(currentFilePath.value).toBe('/games/chosen.sgf'))
    expect((window as any).baduk.saveFile).not.toHaveBeenCalled()
  })

  it('shows an error banner and keeps isDirty true when saving fails', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      saveFile: vi.fn().mockRejectedValue(new Error('disk full')),
      saveFileAs: vi.fn()
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    loadGame('(;GM[1]FF[4]SZ[9];B[ee])', '/games/example.sgf')
    isDirty.value = true

    fireEvent.click(getByText('Сохранить'))
    await waitFor(() => expect(getByText(/disk full/)).toBeTruthy())
    expect(isDirty.value).toBe(true)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/App.test.tsx`
Expected: FAIL — `loadGame` doesn't accept a second argument, no header/Save button exists, `saveCurrentGame`/`saveError` aren't exported.

- [ ] **Step 3: Write the implementation**

In `frontend/src/renderer/src/App.tsx`, replace the full import block (lines 1-16) with:
```tsx
import { useEffect } from 'preact/hooks'
import { signal } from '@preact/signals'
import type { JSX } from 'preact'
import { BoardView } from './board/BoardView'
import { VariationTree } from './board/VariationTree'
import { AnalysisPanel } from './analysis/AnalysisPanel'
import { parseSgf, getBoardSize, mainLineNodeIds, SgfParseError } from './board/sgfLoader'
import { buildStreamRequest } from './board/gameRequestBuilder'
import { serializeTree } from './board/sgfSerializer'
import { streamAnalysis } from './ipc/client'
import {
  currentTree,
  currentNodeId,
  analysisByTurn,
  streamStatus,
  streamError,
  currentFilePath,
  isDirty
} from './state/appState'
```

Replace the module-scope signal declarations (originally lines 20-23):
```tsx
const connectionState = signal<'pending' | 'ready' | 'error'>('pending')
const connectionErrorMessage = signal<string | null>(null)
export const sgfError = signal<string | null>(null)
const lastLoadedSgfContent = signal<string | null>(null)
```
with:
```tsx
const connectionState = signal<'pending' | 'ready' | 'error'>('pending')
const connectionErrorMessage = signal<string | null>(null)
export const sgfError = signal<string | null>(null)
export const saveError = signal<string | null>(null)
const lastLoadedSgfContent = signal<string | null>(null)
const lastLoadedFilePath = signal<string | null>(null)
```

Replace `export function loadGame(content: string): void {` and its body (originally lines 27-67):
```tsx
export function loadGame(content: string, filePath: string | null = null): void {
  closeCurrentStream?.()
  closeCurrentStream = null

  lastLoadedSgfContent.value = content
  lastLoadedFilePath.value = filePath
  sgfError.value = null
  let tree
  try {
    tree = parseSgf(content)
    getBoardSize(tree) // validates board size (throws SgfParseError for rectangular boards) before any state is committed
  } catch (err) {
    sgfError.value = err instanceof SgfParseError ? err.message : 'Не удалось разобрать SGF'
    streamStatus.value = 'idle'
    streamError.value = null
    return
  }

  currentTree.value = tree
  currentNodeId.value = tree.root.id
  currentFilePath.value = filePath
  isDirty.value = false
  analysisByTurn.value = new Map()
  streamStatus.value = 'streaming'
  streamError.value = null

  const mainLineIds = mainLineNodeIds(tree)
  const request = buildStreamRequest(tree, { maxVisits: DEFAULT_MAX_VISITS })
  closeCurrentStream = streamAnalysis(request, {
    onProgress(msg) {
      const nodeId = mainLineIds[msg.turnNumber]
      const next = new Map(analysisByTurn.value)
      next.set(nodeId, msg.result)
      analysisByTurn.value = next
    },
    onDone() {
      streamStatus.value = 'done'
    },
    onError(msg) {
      streamStatus.value = 'error'
      streamError.value = msg.detail
    }
  })
}

export async function saveCurrentGame(): Promise<void> {
  const tree = currentTree.value
  if (!tree) return
  const content = serializeTree(tree)
  saveError.value = null
  try {
    if (currentFilePath.value) {
      await window.baduk.saveFile(currentFilePath.value, content)
      isDirty.value = false
    } else {
      const result = await window.baduk.saveFileAs(undefined, content)
      if ('canceled' in result) return
      currentFilePath.value = result.path
      isDirty.value = false
    }
  } catch (err) {
    saveError.value = err instanceof Error ? err.message : 'Не удалось сохранить файл'
  }
}

export async function saveCurrentGameAs(): Promise<void> {
  const tree = currentTree.value
  if (!tree) return
  const content = serializeTree(tree)
  saveError.value = null
  try {
    const result = await window.baduk.saveFileAs(currentFilePath.value ?? undefined, content)
    if ('canceled' in result) return
    currentFilePath.value = result.path
    isDirty.value = false
  } catch (err) {
    saveError.value = err instanceof Error ? err.message : 'Не удалось сохранить файл'
  }
}
```

Replace `handleDrop` (originally lines 69-74):
```tsx
function handleDrop(event: DragEvent): void {
  event.preventDefault()
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  const filePath = window.electron.webUtils.getPathForFile(file) || null
  file.text().then((content) => loadGame(content, filePath))
}
```

Replace the retry button's `onClick` inside the JSX (originally):
```tsx
                onClick={() => lastLoadedSgfContent.value && loadGame(lastLoadedSgfContent.value)}
```
with:
```tsx
                onClick={() =>
                  lastLoadedSgfContent.value &&
                  loadGame(lastLoadedSgfContent.value, lastLoadedFilePath.value)
                }
```

Finally, add a header row to the returned JSX. Replace:
```tsx
  return (
    <div class="app-shell" onDrop={handleDrop} onDragOver={handleDragOver}>
      <div class="app-shell__top">
```
with:
```tsx
  return (
    <div class="app-shell" onDrop={handleDrop} onDragOver={handleDragOver}>
      <div class="app-shell__header">
        <span class="app-shell__filename">
          {currentFilePath.value ? currentFilePath.value.split(/[\\/]/).pop() : 'Без файла'}
          {isDirty.value ? ' *' : ''}
        </span>
        <button type="button" disabled={!currentTree.value} onClick={() => void saveCurrentGame()}>
          Сохранить
        </button>
        <button type="button" disabled={!currentTree.value} onClick={() => void saveCurrentGameAs()}>
          Сохранить как
        </button>
        {saveError.value && <span class="app-shell__header-error">{saveError.value}</span>}
      </div>
      <div class="app-shell__top">
```

- [ ] **Step 4: Update the CSS grid to fit the new header row**

In `frontend/src/renderer/assets/main.css`, replace:
```css
.app-shell {
  display: grid;
  grid-template-rows: 1fr auto;
  height: 100vh;
  min-height: 0;
}
```
with:
```css
.app-shell {
  display: grid;
  grid-template-rows: auto 1fr auto;
  height: 100vh;
  min-height: 0;
}
.app-shell__header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  font-size: 13px;
  border-bottom: 1px solid var(--border-color, #333);
}
.app-shell__filename {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.app-shell__header-error {
  background: #4a1414;
  color: #ffb4b4;
  border: 1px solid #7a2222;
  border-radius: 4px;
  padding: 2px 8px;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/App.test.tsx`
Expected: PASS.

- [ ] **Step 6: Run the full frontend test suite (regression check)**

Run: `cd frontend && pnpm exec vitest run`
Expected: PASS — all prior Phase 1/Phase 2 tests unaffected (in particular, `loadGame`'s new optional second parameter must not break any existing single-argument call site).

- [ ] **Step 7: Typecheck**

Run: `cd frontend && pnpm run typecheck:web`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
cd frontend
git add src/renderer/src/App.tsx src/renderer/assets/main.css tests/renderer/components/App.test.tsx
git commit -m "feat: add Save/Save As UI and wire drag&drop file-path capture"
```

---

### Task 9: Warn on close with unsaved changes

**Files:**
- Modify: `frontend/src/main/fileIO.ts`
- Modify: `frontend/src/main/index.ts`
- Modify: `frontend/src/preload/index.ts`
- Modify: `frontend/src/renderer/src/global.d.ts`
- Modify: `frontend/src/renderer/src/App.tsx`
- Test: `frontend/tests/main/fileIO.test.ts` (extend)
- Test: `frontend/tests/renderer/components/App.test.tsx` (extend)

**Interfaces:**
- Consumes: `isDirty`, `saveCurrentGame` (from `App.tsx`/`appState.ts`), `dialog.showMessageBoxSync` (Electron), `useSignalEffect` (from `@preact/signals`).
- Produces: `promptUnsavedChangesChoice(window: BrowserWindow): 'save-and-close' | 'close-without-saving' | 'cancel'` (in `fileIO.ts`); IPC channels `file:dirty-changed`, `file:save-before-close`, `file:save-before-close-result`; `window.baduk.reportDirtyState(isDirty: boolean): void`, `window.baduk.onSaveBeforeClose(handler: () => void): () => void`, `window.baduk.sendSaveBeforeCloseResult(success: boolean): void`.

- [ ] **Step 1: Write the failing test for the close-choice prompt**

In `frontend/tests/main/fileIO.test.ts`, replace the existing `vi.mock('electron', () => ({ dialog: { showSaveDialog: vi.fn() } }))` call (there must be exactly one `vi.mock('electron', ...)` in this file, not two) with:
```ts
vi.mock('electron', () => ({
  dialog: { showSaveDialog: vi.fn(), showMessageBoxSync: vi.fn() }
}))
```
Then add:
```ts
import { promptUnsavedChangesChoice } from '../../src/main/fileIO'

describe('promptUnsavedChangesChoice', () => {
  it('maps dialog button index 0 to save-and-close', () => {
    vi.mocked(dialog.showMessageBoxSync).mockReturnValue(0)
    expect(promptUnsavedChangesChoice({} as Electron.BrowserWindow)).toBe('save-and-close')
  })

  it('maps dialog button index 1 to close-without-saving', () => {
    vi.mocked(dialog.showMessageBoxSync).mockReturnValue(1)
    expect(promptUnsavedChangesChoice({} as Electron.BrowserWindow)).toBe('close-without-saving')
  })

  it('maps dialog button index 2 (and the dismiss/Escape case) to cancel', () => {
    vi.mocked(dialog.showMessageBoxSync).mockReturnValue(2)
    expect(promptUnsavedChangesChoice({} as Electron.BrowserWindow)).toBe('cancel')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm exec vitest run tests/main/fileIO.test.ts`
Expected: FAIL — `promptUnsavedChangesChoice` is not exported, `dialog.showMessageBoxSync` doesn't exist on the mock yet (fixed by the same edit).

- [ ] **Step 3: Implement `promptUnsavedChangesChoice`**

In `frontend/src/main/fileIO.ts`, replace the existing `import { dialog } from 'electron'` line with:
```ts
import { dialog, type BrowserWindow } from 'electron'
```

Then append:
```ts
export type UnsavedChangesChoice = 'save-and-close' | 'close-without-saving' | 'cancel'

export function promptUnsavedChangesChoice(window: BrowserWindow): UnsavedChangesChoice {
  const choice = dialog.showMessageBoxSync(window, {
    type: 'warning',
    buttons: ['Сохранить и закрыть', 'Закрыть без сохранения', 'Отмена'],
    defaultId: 0,
    cancelId: 2,
    message: 'В открытой партии есть несохранённые изменения.',
    detail: 'Сохранить изменения перед закрытием?'
  })
  if (choice === 0) return 'save-and-close'
  if (choice === 1) return 'close-without-saving'
  return 'cancel'
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm exec vitest run tests/main/fileIO.test.ts`
Expected: PASS.

- [ ] **Step 5: Wire the close handler and dirty-tracking IPC (thin, untested — same convention as Task 7)**

Modify `frontend/src/main/index.ts`:

Replace the import line added in Task 7:
```ts
import { saveFile, saveFileAs } from './fileIO'
```
with:
```ts
import { saveFile, saveFileAs, promptUnsavedChangesChoice } from './fileIO'
```

Replace:
```ts
let backendConnectionPromise: Promise<BackendConnection> | null = null
```
with:
```ts
let backendConnectionPromise: Promise<BackendConnection> | null = null
let mainWindow: BrowserWindow | null = null
let hasUnsavedChanges = false
```

In `function createWindow(): void {`, replace:
```ts
  const mainWindow = new BrowserWindow({
```
with:
```ts
  mainWindow = new BrowserWindow({
```

Still inside `createWindow()`, right after the existing `mainWindow.webContents.on('console-message', ...)` block, add:
```ts
  mainWindow.on('close', (event) => {
    if (!hasUnsavedChanges) return
    event.preventDefault()

    const choice = promptUnsavedChangesChoice(mainWindow!)
    if (choice === 'cancel') return
    if (choice === 'close-without-saving') {
      hasUnsavedChanges = false
      mainWindow!.destroy()
      return
    }
    mainWindow!.webContents.send('file:save-before-close')
  })
```

In the `app.whenReady().then(() => {...})` block, after the Task 7 `file:save`/`file:save-as` handlers, add:
```ts
  ipcMain.on('file:dirty-changed', (_event, dirty: boolean) => {
    hasUnsavedChanges = dirty
  })
  ipcMain.on('file:save-before-close-result', (_event, success: boolean) => {
    if (!success) return
    hasUnsavedChanges = false
    mainWindow?.destroy()
  })
```

- [ ] **Step 6: Expose the new IPC calls in preload**

Modify `frontend/src/preload/index.ts` — extend the `baduk` object from Task 7:
```ts
const baduk = {
  getBackendConnection: () => ipcRenderer.invoke('backend:get-connection'),
  saveFile: (path: string, content: string) => ipcRenderer.invoke('file:save', path, content),
  saveFileAs: (defaultPath: string | undefined, content: string) =>
    ipcRenderer.invoke('file:save-as', defaultPath, content),
  reportDirtyState: (isDirty: boolean) => ipcRenderer.send('file:dirty-changed', isDirty),
  onSaveBeforeClose: (handler: () => void) => {
    const listener = (): void => handler()
    ipcRenderer.on('file:save-before-close', listener)
    return () => ipcRenderer.removeListener('file:save-before-close', listener)
  },
  sendSaveBeforeCloseResult: (success: boolean) =>
    ipcRenderer.send('file:save-before-close-result', success)
}
```

- [ ] **Step 7: Extend the `window.baduk` type declaration**

Modify `frontend/src/renderer/src/global.d.ts` — extend the `baduk` interface from Task 7:
```ts
declare global {
  interface Window {
    baduk: {
      getBackendConnection(): Promise<BackendConnection>
      saveFile(path: string, content: string): Promise<void>
      saveFileAs(defaultPath: string | undefined, content: string): Promise<SaveFileAsResult>
      reportDirtyState(isDirty: boolean): void
      onSaveBeforeClose(handler: () => void): () => void
      sendSaveBeforeCloseResult(success: boolean): void
    }
  }
}
```

- [ ] **Step 8: Retrofit existing `window.baduk` test mocks, then write the failing renderer-side test**

Step 10 below makes `App()` call `window.baduk.reportDirtyState(...)` and `window.baduk.onSaveBeforeClose(...)` unconditionally on every render. Every test in `frontend/tests/renderer/components/App.test.tsx` that renders `<App />` sets its own `(window as any).baduk = {...}` object literal, and none of the ones written before this task include those two methods — once Step 10 lands, every one of those tests would start throwing `window.baduk.reportDirtyState is not a function`. Fix this now, before writing this task's own new tests, by adding `reportDirtyState: vi.fn()` and `onSaveBeforeClose: vi.fn().mockReturnValue(() => {})` to each of the following existing `(window as any).baduk = {...}` object literals in that file (both the ones already in the repo from Phase 1/2, and the ones this plan's Task 8 added):
- `'shows a connection-error screen if the backend connection promise rejects'`
- `'renders the app shell once the backend connection resolves'`
- `'surfaces an explicit sgfError banner instead of crashing/leaving stale tree state'`
- `'shows "Без файла" and disables Save/Save As with no game loaded'`
- `'captures the dropped file path via window.electron.webUtils ...'`
- `'falls back to Save As when there is no known file path yet'`
- `'shows an error banner and keeps isDirty true when saving fails'`

For example, the first one becomes:
```tsx
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockRejectedValue(new Error('backend did not start')),
      reportDirtyState: vi.fn(),
      onSaveBeforeClose: vi.fn().mockReturnValue(() => {})
    }
```
Apply the same two added lines to each of the other six.

Then add the new tests for this task:

```tsx
describe('unsaved-changes close handshake', () => {
  it('reports dirty state to main whenever isDirty changes', async () => {
    const reportDirtyState = vi.fn()
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      reportDirtyState,
      onSaveBeforeClose: vi.fn().mockReturnValue(() => {})
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    isDirty.value = true
    await waitFor(() => expect(reportDirtyState).toHaveBeenLastCalledWith(true))

    isDirty.value = false
    await waitFor(() => expect(reportDirtyState).toHaveBeenLastCalledWith(false))
  })

  it('saves and reports success when main requests a save before close', async () => {
    let saveBeforeCloseHandler: (() => void) | undefined
    const sendSaveBeforeCloseResult = vi.fn()
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      saveFile: vi.fn().mockResolvedValue(undefined),
      reportDirtyState: vi.fn(),
      onSaveBeforeClose: vi.fn().mockImplementation((handler: () => void) => {
        saveBeforeCloseHandler = handler
        return () => {}
      }),
      sendSaveBeforeCloseResult
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    loadGame('(;GM[1]FF[4]SZ[9];B[ee])', '/games/example.sgf')
    isDirty.value = true

    expect(saveBeforeCloseHandler).toBeTruthy()
    await saveBeforeCloseHandler!()

    expect((window as any).baduk.saveFile).toHaveBeenCalled()
    await waitFor(() => expect(sendSaveBeforeCloseResult).toHaveBeenCalledWith(true))
  })
})
```

- [ ] **Step 9: Run test to verify it fails**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/App.test.tsx`
Expected: FAIL — `App` doesn't call `reportDirtyState`/`onSaveBeforeClose`/`sendSaveBeforeCloseResult` yet.

- [ ] **Step 10: Wire the renderer side**

In `frontend/src/renderer/src/App.tsx`, add `useSignalEffect` to the `preact/signals` import:
```tsx
import { signal, useSignalEffect } from '@preact/signals'
```
(merge with the existing `import { signal } from '@preact/signals'` line)

Inside `export function App(): JSX.Element {`, right after the existing:
```tsx
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
```
add:
```tsx
  useSignalEffect(() => {
    window.baduk.reportDirtyState(isDirty.value)
  })

  useEffect(() => {
    return window.baduk.onSaveBeforeClose(async () => {
      await saveCurrentGame()
      window.baduk.sendSaveBeforeCloseResult(!isDirty.value)
    })
  }, [])
```

- [ ] **Step 11: Run tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/App.test.tsx tests/main/fileIO.test.ts`
Expected: PASS.

- [ ] **Step 12: Run the full frontend test suite (regression check)**

Run: `cd frontend && pnpm exec vitest run`
Expected: PASS.

- [ ] **Step 13: Typecheck both processes**

Run: `cd frontend && pnpm run typecheck`
Expected: no errors.

- [ ] **Step 14: Lint**

Run: `cd frontend && pnpm run lint`
Expected: no errors, no warnings (project convention — see `CLAUDE.md`/backlog history on keeping lint fully green).

- [ ] **Step 15: Commit**

```bash
cd frontend
git add src/main/fileIO.ts src/main/index.ts src/preload/index.ts src/renderer/src/global.d.ts src/renderer/src/App.tsx tests/main/fileIO.test.ts tests/renderer/components/App.test.tsx
git commit -m "feat: warn and offer to save on close when there are unsaved changes"
```

---

## Manual acceptance (after all tasks — not automatable, do not skip)

Per the design spec's "Критерии готовности", after the final review/fix-wave, run the app (`pnpm exec electron-vite dev`, with a backend sidecar available per `CLAUDE.md`) and manually verify:
1. Open an SGF with pre-existing `TR`/`SQ`/`CR`/`MA`/`LB`/`C` properties from another program (e.g. re-save one of `frontend/tests/fixtures/*.sgf` with markup added via a text editor) — markup renders on the board, comment appears in the "Разметка" tab.
2. Place a figure and a label via the toolbar, type a comment — UI updates immediately, filename in the header gets a `*`.
3. Click "Сохранить" — file is overwritten; reopen it — same markup/comment reappear.
4. Click "Сохранить как" — a new file is created; the original is untouched.
5. Make an edit, then try to close the window — get the warning dialog; each of its three choices behaves as expected.

This step cannot be delegated to an automated final-review subagent — flag it explicitly to the user rather than claiming the feature complete without it, consistent with how Phase 2's `weak_group` slice was handled (see `task_plan.md`, "ещё НЕ было ручной сквозной приёмки").
