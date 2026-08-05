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
): { signMap: (0 | 1 | -1)[][]; boardSize: number; lastMoveVertex: [number, number] | null } {
  const boardSize = getBoardSize(tree)
  let board = Board.fromDimensions(boardSize)
  let lastMoveVertex: [number, number] | null = null

  for (const { color, sgfCoord } of movesFromRootToNode(tree, nodeId)) {
    const vertex = sgfCoordToVertex(sgfCoord)
    if (vertex === null) continue // pass — доска не меняется, маркер последнего хода не двигаем
    const sign = color === 'B' ? 1 : -1
    board = board.makeMove(sign, vertex)
    lastMoveVertex = vertex
  }

  return { signMap: board.signMap, boardSize, lastMoveVertex }
}
