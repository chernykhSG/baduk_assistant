# Variation Tree Annotation Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a small triangle icon inside each variation-tree node marker whose SGF node has a comment and/or markup, so annotated nodes are visible without navigating to them.

**Architecture:** A pure function `hasAnnotation(node: NodeObject): boolean` added to `frontend/src/renderer/src/board/VariationTree.tsx` checks `node.data` for a non-empty `C`, `TR`, `SQ`, `CR`, `MA`, or `LB` property. The existing `renderMarker(node)` function conditionally renders a small inline SVG triangle (same path convention as `@sabaki/shudan`'s `Marker.js`) inside the marker button when `hasAnnotation(node)` is true. No new state, IPC, or tree mutation — this is a read-only render addition.

**Tech Stack:** Preact + TypeScript (existing `VariationTree.tsx` component), Vitest + `@testing-library/preact` for tests, plain CSS in `frontend/src/renderer/assets/main.css`.

## Global Constraints

- Work happens only on branch `fix-variation-tree-annotation-indicator`, forked from `main`. Never commit directly to `main`.
- TDD: write the failing test first, verify it fails, then implement, then verify it passes — one component at a time, per existing project convention.
- No hardcoded config/paths/secrets (not relevant to this feature, but the rule always applies per `CLAUDE.md`).
- No new signals, IPC contracts, or SGF mutations — `hasAnnotation` is a pure function of `node.data`, called only at render time.
- Single combined indicator per node (comment OR markup, no distinction between the two) — this is deliberate scope from the design spec, not an oversight.

---

## Context for the implementer

**Current state of `frontend/src/renderer/src/board/VariationTree.tsx`** (read in full before starting — this is the only file whose logic changes):

- `renderMarker(node: NodeObject): JSX.Element` (lines 68-87) renders a `<button>` with no children:
  ```tsx
  function renderMarker(node: NodeObject): JSX.Element {
    const isCurrent = node.id === nodeId
    const colorClass = node.data.B
      ? 'variation-tree__marker--black'
      : node.data.W
        ? 'variation-tree__marker--white'
        : 'variation-tree__marker--root'
    const label = node.data.B ? `B ${node.data.B[0]}` : node.data.W ? `W ${node.data.W[0]}` : 'root'
    return (
      <button
        key={node.id}
        ref={isCurrent ? currentRef : undefined}
        type="button"
        class={`variation-tree__marker ${colorClass}${isCurrent ? ' variation-tree__marker--current' : ''}`}
        onClick={() => (currentNodeId.value = node.id)}
        title={label}
        aria-label={label}
      />
    )
  }
  ```
- `NodeObject` (from `frontend/src/renderer/src/board/sgfLoader.ts:10-15`):
  ```ts
  export interface NodeObject {
    id: number
    data: Record<string, string[]>
    parentId: number | null
    children: NodeObject[]
  }
  ```
- `setComment(tree, nodeId, text)` in `frontend/src/renderer/src/board/annotations.ts:91-95` sets `C` to `[]` (not deleting the key) when `text` is empty — so an "empty comment" node has `data.C === []`, and `data.C?.[0]` is `undefined` (falsy). The `hasAnnotation` check must rely on `data.C?.[0]` (truthy check on the string), not merely on the key's presence.

**Current relevant CSS** (`frontend/src/renderer/assets/main.css:315-345`):
```css
.variation-tree__marker {
  appearance: none;
  -webkit-appearance: none;
  background: none;
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  margin: 3px 0;
  padding: 0;
  /* ...border/border-radius rules continue, not shown here... */
}
.variation-tree__marker--black {
  background: #111;
  border-color: #6b6b6b;
}
.variation-tree__marker--white {
  background: #eee;
  border-color: #999;
}
.variation-tree__marker--root {
  background: transparent;
}
.variation-tree__marker--current {
  outline: 2px solid #4dabf7;
  outline-offset: 1px;
}
```
`.variation-tree__marker` has no `position` rule currently — it needs `position: relative` added so the new icon can be absolutely positioned inside it.

There is no `--color-accent` CSS custom property defined anywhere in this codebase yet (confirmed by search) even though `docs/ARCHITECTURE.md` documents it as a design token. Use `fill: var(--color-accent, #22C55E)` exactly as written — the fallback value applies since the custom property is currently undefined, and this keeps the rule forward-compatible if `--color-accent` is defined later.

**Test file to extend**: `frontend/tests/renderer/components/VariationTree.test.tsx`. Existing pattern (full file, for reference):
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
  // ...existing keyboard-navigation tests...
})
```
`parseSgf(sgfString: string): GameTree` (from `frontend/src/renderer/src/board/sgfLoader.ts`) is the existing helper used to build a tree from raw SGF text in tests — reuse it to construct nodes with `C[...]`/`TR[...]` properties directly in the SGF string (e.g. `(;GM[1]FF[4]SZ[9];B[ee]C[hello])`).

---

### Task 1: Add `hasAnnotation` and render the indicator icon

**Files:**
- Modify: `frontend/src/renderer/src/board/VariationTree.tsx`
- Modify: `frontend/src/renderer/assets/main.css`
- Test: `frontend/tests/renderer/components/VariationTree.test.tsx`

**Interfaces:**
- Consumes: `NodeObject` type (`frontend/src/renderer/src/board/sgfLoader.ts`), existing `renderMarker(node)` internal function.
- Produces: `hasAnnotation(node: NodeObject): boolean` — a module-scope (not exported) pure function inside `VariationTree.tsx`. Nothing outside this file depends on it, so it does not need to be exported.

- [ ] **Step 1: Write the failing tests**

Add these four tests inside the existing `describe('VariationTree', ...)` block in `frontend/tests/renderer/components/VariationTree.test.tsx`, after the existing tests:

```tsx
  it('shows the annotation indicator on a node with a comment', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]C[hello])')
    currentTree.value = tree
    currentNodeId.value = tree.root.id

    const { container } = render(<VariationTree />)

    const icon = container.querySelector('.variation-tree__marker-annotation-icon')
    expect(icon).not.toBeNull()
  })

  it('shows the annotation indicator on a node with markup', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]TR[ec])')
    currentTree.value = tree
    currentNodeId.value = tree.root.id

    const { container } = render(<VariationTree />)

    const icon = container.querySelector('.variation-tree__marker-annotation-icon')
    expect(icon).not.toBeNull()
  })

  it('does not show the annotation indicator on a node with neither comment nor markup', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    currentTree.value = tree
    currentNodeId.value = tree.root.id

    const { container } = render(<VariationTree />)

    const icon = container.querySelector('.variation-tree__marker-annotation-icon')
    expect(icon).toBeNull()
  })

  it('does not show the annotation indicator on a node with an emptied comment', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]C[hello])')
    const clearedTree = setComment(tree, tree.root.children[0].id, '')
    currentTree.value = clearedTree
    currentNodeId.value = clearedTree.root.id

    const { container } = render(<VariationTree />)

    const icons = container.querySelectorAll('.variation-tree__marker-annotation-icon')
    expect(icons.length).toBe(0)
  })
```

Add the new import at the top of the test file, alongside the existing imports:

```tsx
import { setComment } from '@renderer/board/annotations'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/VariationTree.test.tsx`
Expected: the 4 new tests FAIL (no element matches `.variation-tree__marker-annotation-icon` because it doesn't exist yet; the "shows the indicator" tests fail with `expect(icon).not.toBeNull()` receiving `null`, the "does not show" tests trivially pass since nothing renders it — but the emptied-comment test must be checked to confirm it isn't a false-pass: since no icon exists anywhere yet, `icons.length` is already `0`, so that specific test will pass even before implementation. This is expected — the two "shows" tests are the ones that must fail here to prove the test harness is exercising real code.)

- [ ] **Step 3: Implement `hasAnnotation` and update `renderMarker`**

In `frontend/src/renderer/src/board/VariationTree.tsx`, add the `hasAnnotation` function above `renderMarker` (both are declared inside the `VariationTree` component body, after the `if (!tree) return ...` line, alongside the existing `renderMarker`/`renderChain` declarations):

```tsx
  function hasAnnotation(node: NodeObject): boolean {
    if (node.data.C?.[0]) return true
    return (['TR', 'SQ', 'CR', 'MA', 'LB'] as const).some((key) => (node.data[key]?.length ?? 0) > 0)
  }
```

Replace the `renderMarker` function body to add the icon as a child of the button when `hasAnnotation(node)` is true:

```tsx
  function renderMarker(node: NodeObject): JSX.Element {
    const isCurrent = node.id === nodeId
    const colorClass = node.data.B
      ? 'variation-tree__marker--black'
      : node.data.W
        ? 'variation-tree__marker--white'
        : 'variation-tree__marker--root'
    const label = node.data.B ? `B ${node.data.B[0]}` : node.data.W ? `W ${node.data.W[0]}` : 'root'
    return (
      <button
        key={node.id}
        ref={isCurrent ? currentRef : undefined}
        type="button"
        class={`variation-tree__marker ${colorClass}${isCurrent ? ' variation-tree__marker--current' : ''}`}
        onClick={() => (currentNodeId.value = node.id)}
        title={label}
        aria-label={label}
      >
        {hasAnnotation(node) && (
          <svg
            class="variation-tree__marker-annotation-icon"
            viewBox="0 0 1 1"
            aria-hidden="true"
          >
            <path d="M 0 .5 L .6 .5 L .3 0 z" transform="translate(.2 .2)" />
          </svg>
        )}
      </button>
    )
  }
```

- [ ] **Step 4: Add the CSS rules**

In `frontend/src/renderer/assets/main.css`, add `position: relative` to the existing `.variation-tree__marker` rule (around line 315) — insert it alongside the existing declarations, e.g. right after `padding: 0;`:

```css
.variation-tree__marker {
  appearance: none;
  -webkit-appearance: none;
  background: none;
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  margin: 3px 0;
  padding: 0;
  position: relative;
  /* ...existing border/border-radius rules unchanged... */
}
```

Then add a new rule after the existing `.variation-tree__marker--current` rule (after line 345):

```css
.variation-tree__marker-annotation-icon {
  position: absolute;
  top: 1px;
  left: 1px;
  width: 8px;
  height: 8px;
  fill: var(--color-accent, #22C55E);
  pointer-events: none;
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/VariationTree.test.tsx`
Expected: all tests in the file PASS, including the 4 new ones.

- [ ] **Step 6: Run the full frontend test suite, typecheck, and lint**

Run:
```bash
cd frontend
pnpm exec vitest run
pnpm run typecheck:web
pnpm run typecheck:node
pnpm run lint
```
Expected: all pass with no new failures. (Project's pre-existing `pnpm run lint` backlog, if any remains from before this task, is out of scope — only confirm this task introduces no *new* lint errors in the touched files.)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/renderer/src/board/VariationTree.tsx frontend/src/renderer/assets/main.css frontend/tests/renderer/components/VariationTree.test.tsx
git commit -m "feat: show annotation indicator on variation-tree nodes with comments or markup"
```

---

## Manual verification (after the task is complete)

Open a game with comments and/or markup (`TR`/`SQ`/`CR`/`MA`/`LB`) set on several nodes — e.g. reuse the manual-test SGF from the SGF-annotation feature's acceptance testing. Confirm the small green triangle appears inside the marker of every annotated node, on any position in the tree (not just the current node), and does not appear on unannotated nodes.
