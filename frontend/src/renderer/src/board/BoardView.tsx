import { useEffect, useRef, useState } from 'preact/hooks'
import { BoundedGoban } from '@sabaki/shudan'
import '@sabaki/shudan/css/goban.css'
import { currentBoardPosition, currentMoveAnalysis, currentNode } from '../state/appState'
import { GTP_COLUMNS } from './gtpColumns'
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
import type { JSX } from 'preact'
import type { Marker } from '@sabaki/shudan'
import type { MoveInfo } from '../ipc/client'

const MAX_SUGGESTED_MOVES = 5

const ANNOTATION_TOOLS: { tool: AnnotationTool; label: string }[] = [
  { tool: 'TR', label: '△' },
  { tool: 'SQ', label: '□' },
  { tool: 'CR', label: '○' },
  { tool: 'MA', label: '✕' },
  { tool: 'LB', label: 'Метка' },
  { tool: 'erase', label: 'Ластик' }
]

function useContainerSize(): [
  (el: HTMLDivElement | null) => void,
  { width: number; height: number }
] {
  const [size, setSize] = useState({ width: 0, height: 0 })
  const sizeRef = useRef(size)
  const observerRef = useRef<ResizeObserver | null>(null)

  const setRef = (el: HTMLDivElement | null): void => {
    observerRef.current?.disconnect()
    observerRef.current = null
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      // Round to whole pixels and skip no-op updates: BoundedGoban renders
      // a board smaller than or equal to this container (it never grows
      // it), but sub-pixel/rounding jitter in contentRect between renders
      // was enough to keep re-triggering this observer on every frame —
      // Chrome's "ResizeObserver loop completed with undelivered
      // notifications" warning, logged thousands of times a session,
      // pegging the renderer busy and starving real UI updates.
      const width = Math.round(entry.contentRect.width)
      const height = Math.round(entry.contentRect.height)
      if (width === sizeRef.current.width && height === sizeRef.current.height) return
      sizeRef.current = { width, height }
      setSize(sizeRef.current)
    })
    observer.observe(el)
    observerRef.current = observer
  }

  useEffect(() => () => observerRef.current?.disconnect(), [])

  return [setRef, size]
}

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

function ownershipToHeatMap(
  ownership: number[] | undefined,
  boardSize: number,
  hoveredVertex: [number, number] | null
): (null | { strength: number; text?: string })[][] | undefined {
  if (!ownership) return undefined
  const grid: (null | { strength: number; text?: string })[][] = []
  for (let y = 0; y < boardSize; y++) {
    const row: (null | { strength: number; text?: string })[] = []
    for (let x = 0; x < boardSize; x++) {
      const value = ownership[y * boardSize + x]
      const strength = Math.min(9, Math.max(1, Math.ceil(Math.abs(value) * 9)))
      const isHovered = hoveredVertex !== null && hoveredVertex[0] === x && hoveredVertex[1] === y
      row.push(isHovered ? { strength, text: value.toFixed(2) } : { strength })
    }
    grid.push(row)
  }
  return grid
}

function gtpToVertex(gtpCoord: string, boardSize: number): [number, number] | null {
  if (gtpCoord === 'pass') return null
  const col = GTP_COLUMNS.indexOf(gtpCoord[0].toUpperCase())
  const row = parseInt(gtpCoord.slice(1), 10)
  if (col === -1 || Number.isNaN(row)) return null
  return [col, boardSize - row]
}

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

// Rendered both once a position is loaded (next to the goban) and in the
// empty state before any SGF is opened, so tool selection persists across
// loading a file rather than resetting when the board first appears.
function AnnotationToolbar(): JSX.Element {
  return (
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
  )
}

export function BoardView(): JSX.Element {
  const [hoveredVertex, setHoveredVertex] = useState<[number, number] | null>(null)
  const [containerRef, containerSize] = useContainerSize()
  const [showOwnership, setShowOwnership] = useState(true)
  const [showPv, setShowPv] = useState(true)
  const position = currentBoardPosition.value
  const analysis = currentMoveAnalysis.value

  if (!position) {
    return (
      <div class="board-view board-view--empty">
        <AnnotationToolbar />
        Откройте SGF-файл, чтобы начать
      </div>
    )
  }

  const heatMap = showOwnership
    ? ownershipToHeatMap(analysis?.ownership, position.boardSize, hoveredVertex)
    : undefined
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

  // Before the first ResizeObserver callback (or in test environments, where
  // jsdom never performs real layout and none ever fires), fall back to a
  // fixed size so the board still renders instead of collapsing to nothing.
  const maxWidth = containerSize.width || 600
  const maxHeight = containerSize.height || 600

  return (
    <div class="board-view">
      <div class="board-view__toolbar">
        <label>
          <input
            type="checkbox"
            checked={showOwnership}
            onChange={(event) => setShowOwnership((event.target as HTMLInputElement).checked)}
          />
          Владение (heatmap)
        </label>
        <label>
          <input
            type="checkbox"
            checked={showPv}
            onChange={(event) => setShowPv((event.target as HTMLInputElement).checked)}
          />
          Предлагаемые ходы
        </label>
      </div>
      <AnnotationToolbar />
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
    </div>
  )
}
