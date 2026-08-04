import { describe, it, expect, beforeEach } from 'vitest'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import {
  currentTree,
  currentNodeId,
  analysisByTurn,
  currentBoardPosition,
  currentTurnNumber,
  currentMoveAnalysis,
} from '@renderer/state/appState'

const fixtureContent = '(;GM[1]FF[4]SZ[9]KM[7.5]RU[Chinese];B[ee])'

beforeEach(() => {
  currentTree.value = null
  currentNodeId.value = null
  analysisByTurn.value = new Map()
})

describe('currentBoardPosition', () => {
  it('is null when no tree is loaded', () => {
    expect(currentBoardPosition.value).toBeNull()
  })

  it('derives the signMap for the current node once a tree is loaded', () => {
    const tree = parseSgf(fixtureContent)
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    expect(currentBoardPosition.value?.boardSize).toBe(9)
    expect(currentBoardPosition.value?.signMap[4][4]).toBe(1)
  })
})

describe('currentTurnNumber + currentMoveAnalysis', () => {
  it('looks up the analysis for the turn matching the current node', () => {
    const tree = parseSgf(fixtureContent)
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    expect(currentTurnNumber.value).toBe(1)
    expect(currentMoveAnalysis.value).toBeNull()

    const fakeResponse = { id: 'x', moveInfos: [], rootInfo: { winrate: 0.6, scoreLead: 1, visits: 10 } }
    analysisByTurn.value = new Map([[1, fakeResponse]])

    expect(currentMoveAnalysis.value).toEqual(fakeResponse)
  })
})
