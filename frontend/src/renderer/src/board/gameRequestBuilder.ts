import type GameTree from '@sabaki/immutable-gametree'
import { getBoardSize, findMainLineLeaf, movesFromRootToNode, nodeIdsFromRootToNode } from './sgfLoader'
import { GTP_COLUMNS } from './gtpColumns'
import { analysisByTurn } from '../state/appState'
import type { AnalyzeRequest, StreamAnalyzeRequest, OpeningTurnEval } from '../ipc/client'

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

export function gtpMoves(tree: GameTree, nodeId: number, boardSize: number): [string, string][] {
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

// Must match feature_extraction/detector_config.v1.json's "k_open" field
// exactly - the backend validates that the opening sequence covers
// precisely this window and rejects the request (422) otherwise, so any
// drift here makes the "Проанализировать дебют" button unusable rather
// than silently wrong.
const K_OPEN = 0.12

export function buildOpeningSequence(
  tree: GameTree,
  nodeId: number,
  boardSize: number
): OpeningTurnEval[] | null {
  const windowEnd = Math.floor(boardSize * boardSize * K_OPEN)
  const nodeIds = nodeIdsFromRootToNode(tree, nodeId)
  const windowLength = Math.min(windowEnd, nodeIds.length - 1) + 1

  const sequence: OpeningTurnEval[] = []
  for (let turnNumber = 0; turnNumber < windowLength; turnNumber++) {
    const analysis = analysisByTurn.value.get(nodeIds[turnNumber])
    if (!analysis) return null
    sequence.push({
      turnNumber,
      scoreLead: analysis.rootInfo.scoreLead,
      visits: analysis.rootInfo.visits
    })
  }
  return sequence
}
