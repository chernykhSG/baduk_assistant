import { describe, it, expect, beforeEach } from 'vitest'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import {
  currentTree,
  currentNodeId,
  analysisByTurn,
  currentBoardPosition,
  currentTurnNumber,
  currentMoveAnalysis,
  currentFilePath,
  isDirty,
  currentNode
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
  it('looks up the analysis keyed by the current node id', () => {
    const tree = parseSgf(fixtureContent)
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    expect(currentTurnNumber.value).toBe(1)
    expect(currentMoveAnalysis.value).toBeNull()

    const fakeResponse = {
      id: 'x',
      moveInfos: [],
      rootInfo: { winrate: 0.6, scoreLead: 1, visits: 10 }
    }
    analysisByTurn.value = new Map([[leaf.id, fakeResponse]])

    expect(currentMoveAnalysis.value).toEqual(fakeResponse)
  })

  it('returns null for an off-main-line node even when the main line has analysis at the same depth', () => {
    // Two variations after the first move: (;B[ee](;W[ec])(;W[gc]))
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee](;W[ec])(;W[gc]))')
    type Node = { id: number; children: Node[] }
    const bMoveNode = (tree.root as Node).children[0]
    const mainLineVariation = bMoveNode.children[0] // W[ec] - main line (first child)
    const otherVariation = bMoveNode.children[1] // W[gc] - off main line

    currentTree.value = tree

    const fakeResponse = {
      id: 'x',
      moveInfos: [],
      rootInfo: { winrate: 0.6, scoreLead: 1, visits: 10 }
    }
    // Only the main-line node at this depth was ever analyzed (as buildStreamRequest only streams the main line).
    analysisByTurn.value = new Map([[mainLineVariation.id, fakeResponse]])

    currentNodeId.value = otherVariation.id
    expect(currentMoveAnalysis.value).toBeNull()

    currentNodeId.value = mainLineVariation.id
    expect(currentMoveAnalysis.value).toEqual(fakeResponse)
  })
})

describe('currentFilePath + isDirty', () => {
  it('default to null and false', () => {
    expect(currentFilePath.value).toBeNull()
    expect(isDirty.value).toBe(false)
  })

  it('can be set independently of the tree/node signals', () => {
    currentFilePath.value = 'C:/games/example.sgf'
    isDirty.value = true

    expect(currentFilePath.value).toBe('C:/games/example.sgf')
    expect(isDirty.value).toBe(true)

    currentFilePath.value = null
    isDirty.value = false
  })
})

describe('currentNode', () => {
  it('is null when no tree is loaded', () => {
    expect(currentNode.value).toBeNull()
  })

  it('derives the raw node object for the current node id', () => {
    const tree = parseSgf(fixtureContent)
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    expect(currentNode.value?.id).toBe(leaf.id)
    expect(currentNode.value?.data.B).toEqual(['ee'])
  })
})
