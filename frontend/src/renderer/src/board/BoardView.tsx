import { useEffect, useRef, useState } from 'preact/hooks'
import { BoundedGoban } from '@sabaki/shudan'
import '@sabaki/shudan/css/goban.css'
import { currentBoardPosition, currentMoveAnalysis } from '../state/appState'

function useContainerSize(): [(el: HTMLDivElement | null) => void, { width: number; height: number }] {
  const [size, setSize] = useState({ width: 0, height: 0 })
  const observerRef = useRef<ResizeObserver | null>(null)

  const setRef = (el: HTMLDivElement | null): void => {
    observerRef.current?.disconnect()
    observerRef.current = null
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      const { width, height } = entry.contentRect
      setSize({ width, height })
    })
    observer.observe(el)
    observerRef.current = observer
  }

  useEffect(() => () => observerRef.current?.disconnect(), [])

  return [setRef, size]
}

function lastMoveToMarkerMap(
  lastMoveVertex: [number, number] | null,
  boardSize: number
): (null | { type: 'point' })[][] | undefined {
  if (!lastMoveVertex) return undefined
  const grid: (null | { type: 'point' })[][] = []
  for (let y = 0; y < boardSize; y++) {
    const row: (null | { type: 'point' })[] = []
    for (let x = 0; x < boardSize; x++) {
      row.push(x === lastMoveVertex[0] && y === lastMoveVertex[1] ? { type: 'point' } : null)
    }
    grid.push(row)
  }
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
): { v1: [number, number]; v2: [number, number]; type: 'line' | 'arrow' }[] {
  if (!pv || pv.length < 2) return []
  const lines: { v1: [number, number]; v2: [number, number]; type: 'line' | 'arrow' }[] = []
  for (let i = 0; i < pv.length - 1; i++) {
    const v1 = gtpToVertex(pv[i], boardSize)
    const v2 = gtpToVertex(pv[i + 1], boardSize)
    if (v1 && v2) lines.push({ v1, v2, type: 'line' })
  }
  return lines
}

export function BoardView() {
  const [hoveredVertex, setHoveredVertex] = useState<[number, number] | null>(null)
  const [containerRef, containerSize] = useContainerSize()
  const position = currentBoardPosition.value
  const analysis = currentMoveAnalysis.value

  if (!position) {
    return (
      <div class="board-view board-view--empty" ref={containerRef}>
        Откройте SGF-файл, чтобы начать
      </div>
    )
  }

  const heatMap = ownershipToHeatMap(analysis?.ownership, position.boardSize, hoveredVertex)
  const markerMap = lastMoveToMarkerMap(position.lastMoveVertex, position.boardSize)
  const topMove = analysis?.moveInfos[0]
  const lines = pvToLines(topMove?.pv, position.boardSize)

  // Before the first ResizeObserver callback (or in test environments, where
  // jsdom never performs real layout and none ever fires), fall back to a
  // fixed size so the board still renders instead of collapsing to nothing.
  const maxWidth = containerSize.width || 600
  const maxHeight = containerSize.height || 600

  return (
    <div class="board-view" ref={containerRef}>
      <BoundedGoban
        signMap={position.signMap}
        heatMap={heatMap}
        markerMap={markerMap}
        lines={lines}
        maxWidth={maxWidth}
        maxHeight={maxHeight}
        onVertexPointerEnter={(_event, vertex) => setHoveredVertex(vertex as [number, number])}
        onVertexPointerLeave={() => setHoveredVertex(null)}
      />
    </div>
  )
}
