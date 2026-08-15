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
// Increments exactly once per genuine SGF file load (see App.tsx's
// loadGame()) - unlike `currentTree`, it stays stable across in-game
// tree.mutate() calls (annotations, board markup), so it's the correct
// dependency for state that must survive ordinary in-game edits but reset
// on a new game being opened.
export const gameLoadSequence = signal<number>(0)

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
