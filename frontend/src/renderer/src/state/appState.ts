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
