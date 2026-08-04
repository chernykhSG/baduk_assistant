import { useState } from 'preact/hooks'
import { Goban } from '@sabaki/shudan'
import '@sabaki/shudan/css/goban.css'
import { currentBoardPosition, currentMoveAnalysis } from '../state/appState'

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
  const position = currentBoardPosition.value
  const analysis = currentMoveAnalysis.value

  if (!position) {
    return <div class="board-view board-view--empty">Откройте SGF-файл, чтобы начать</div>
  }

  const heatMap = ownershipToHeatMap(analysis?.ownership, position.boardSize, hoveredVertex)
  const topMove = analysis?.moveInfos[0]
  const lines = pvToLines(topMove?.pv, position.boardSize)

  return (
    <Goban
      signMap={position.signMap}
      heatMap={heatMap}
      lines={lines}
      vertexSize={24}
      onVertexPointerEnter={(_event, vertex) => setHoveredVertex(vertex as [number, number])}
      onVertexPointerLeave={() => setHoveredVertex(null)}
    />
  )
}
