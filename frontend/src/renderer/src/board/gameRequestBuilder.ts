import type GameTree from '@sabaki/immutable-gametree'
import { getBoardSize, findMainLineLeaf, movesFromRootToNode } from './sgfLoader'
import { GTP_COLUMNS } from './gtpColumns'
import type { AnalyzeRequest, StreamAnalyzeRequest } from '../ipc/client'

export function sgfCoordToGtp(sgfCoord: string | null, boardSize: number): string {
  if (!sgfCoord) return 'pass'
  const colIndex = sgfCoord.charCodeAt(0) - 'a'.charCodeAt(0)
  const rowIndexFromTop = sgfCoord.charCodeAt(1) - 'a'.charCodeAt(0)
  return `${GTP_COLUMNS[colIndex]}${boardSize - rowIndexFromTop}`
}

const KNOWN_RULES = ['chinese', 'japanese', 'korean', 'aga', 'nz', 'tromp-taylor']

export function mapSgfRules(ruValue: string | undefined): string {
  const normalized = ruValue?.toLowerCase().trim()
  if (normalized && KNOWN_RULES.includes(normalized)) return normalized
  if (normalized) {
    console.warn(`Unrecognized SGF ruleset "${ruValue}", defaulting to chinese rules`)
  }
  return 'chinese'
}

function extractKomi(tree: GameTree): number {
  const parsed = tree.root.data.KM ? parseFloat(tree.root.data.KM[0]) : NaN
  return Number.isFinite(parsed) ? parsed : 7.5
}

function gtpMoves(tree: GameTree, nodeId: number, boardSize: number): [string, string][] {
  return movesFromRootToNode(tree, nodeId).map(({ color, sgfCoord }) => [
    color,
    sgfCoordToGtp(sgfCoord, boardSize)
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
    komi: extractKomi(tree),
    boardXSize: boardSize,
    boardYSize: boardSize,
    analyzeTurns: [moves.length],
    maxVisits: options.maxVisits,
    includeOwnership: true
  }
}

export function buildStreamRequest(
  tree: GameTree,
  options: { maxVisits: number }
): StreamAnalyzeRequest {
  const boardSize = getBoardSize(tree)
  const leaf = findMainLineLeaf(tree)
  const moves = gtpMoves(tree, leaf.id, boardSize)
  return {
    moves,
    rules: mapSgfRules(tree.root.data.RU?.[0]),
    komi: extractKomi(tree),
    boardXSize: boardSize,
    boardYSize: boardSize,
    turnNumbers: Array.from({ length: moves.length + 1 }, (_, i) => i),
    maxVisits: options.maxVisits,
    includeOwnership: true
  }
}
