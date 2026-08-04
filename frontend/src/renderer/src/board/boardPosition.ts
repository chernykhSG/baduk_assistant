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
