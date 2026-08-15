import { afterEach, describe, it, expect } from 'vitest'
import { parseSgf, findMainLineLeaf, nodeIdsFromRootToNode } from '@renderer/board/sgfLoader'
import {
  sgfCoordToGtp,
  mapSgfRules,
  buildAnalyzeRequest,
  buildStreamRequest,
  buildOpeningSequence
} from '@renderer/board/gameRequestBuilder'
import { analysisByTurn } from '@renderer/state/appState'
import type { AnalyzeResponse } from '@renderer/ipc/client'

const fixtureContent = '(;GM[1]FF[4]SZ[19]KM[7.5]RU[Chinese];B[qd];W[dc];B[oq])'

describe('sgfCoordToGtp', () => {
  it('converts SGF coordinates to GTP coordinates on a 19x19 board', () => {
    expect(sgfCoordToGtp('qd', 19)).toBe('R16')
    expect(sgfCoordToGtp('dc', 19)).toBe('D17')
    expect(sgfCoordToGtp('oq', 19)).toBe('P3')
  })

  it('maps a null/empty coordinate to "pass"', () => {
    expect(sgfCoordToGtp(null, 19)).toBe('pass')
    expect(sgfCoordToGtp('', 19)).toBe('pass')
  })
})

describe('mapSgfRules', () => {
  it('lowercases a known ruleset name', () => {
    expect(mapSgfRules('Chinese')).toBe('chinese')
  })

  it('defaults to chinese for unknown/missing values', () => {
    expect(mapSgfRules(undefined)).toBe('chinese')
    expect(mapSgfRules('NotARuleset')).toBe('chinese')
  })
})

describe('buildAnalyzeRequest', () => {
  it('builds a single-turn request for the given node', () => {
    const tree = parseSgf(fixtureContent)
    const leaf = findMainLineLeaf(tree)
    const request = buildAnalyzeRequest(tree, leaf.id, { maxVisits: 500 })

    expect(request).toEqual({
      moves: [
        ['B', 'R16'],
        ['W', 'D17'],
        ['B', 'P3']
      ],
      rules: 'chinese',
      komi: 7.5,
      boardXSize: 19,
      boardYSize: 19,
      analyzeTurns: [3],
      maxVisits: 500,
      includeOwnership: true
    })
  })

  it('falls back to 7.5 komi when KM is present but empty', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[19]KM[];B[qd])')
    const request = buildAnalyzeRequest(tree, tree.root.children[0].id, { maxVisits: 500 })
    expect(request.komi).toBe(7.5)
  })
})

describe('buildStreamRequest', () => {
  it('builds a request covering every turn of the main line', () => {
    const tree = parseSgf(fixtureContent)
    const request = buildStreamRequest(tree, { maxVisits: 500 })

    expect(request.moves).toEqual([
      ['B', 'R16'],
      ['W', 'D17'],
      ['B', 'P3']
    ])
    expect(request.turnNumbers).toEqual([0, 1, 2, 3])
    expect(request.rules).toBe('chinese')
    expect(request.komi).toBe(7.5)
  })
})

function fakeAnalysis(scoreLead: number, visits: number): AnalyzeResponse {
  return { id: 'x', moveInfos: [], rootInfo: { winrate: 0.5, scoreLead, visits }, ownership: undefined }
}

describe('buildOpeningSequence', () => {
  afterEach(() => {
    analysisByTurn.value = new Map()
  })

  it('collects a compact sequence for every turn in the opening window on a 9x9 board', () => {
    // 9x9 board -> window = floor(81 * 0.12) = 9 turns; the fixture has
    // exactly 9 moves.
    const movesText = 'B[aa];W[bb];B[cc];W[dd];B[ee];W[ff];B[gg];W[hh];B[ia]'
    const tree = parseSgf(`(;GM[1]FF[4]SZ[9];${movesText})`)
    const leaf = findMainLineLeaf(tree)
    const nodeIds = nodeIdsFromRootToNode(tree, leaf.id)
    const map = new Map<number, AnalyzeResponse>()
    nodeIds.forEach((id, turn) => map.set(id, fakeAnalysis(10 - turn, 1000)))
    analysisByTurn.value = map

    const sequence = buildOpeningSequence(tree, leaf.id, 9)

    expect(sequence).toHaveLength(10) // turns 0..9
    expect(sequence?.[0]).toEqual({ turnNumber: 0, scoreLead: 10, visits: 1000 })
    expect(sequence?.[9]).toEqual({ turnNumber: 9, scoreLead: 1, visits: 1000 })
  })

  it('shrinks to the actual game length when the game is shorter than the opening window', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[aa];W[bb])')
    const leaf = findMainLineLeaf(tree)
    const nodeIds = nodeIdsFromRootToNode(tree, leaf.id)
    const map = new Map<number, AnalyzeResponse>()
    nodeIds.forEach((id, turn) => map.set(id, fakeAnalysis(5 - turn, 1000)))
    analysisByTurn.value = map

    const sequence = buildOpeningSequence(tree, leaf.id, 9)

    expect(sequence).toHaveLength(3) // turns 0,1,2 - the game only has 2 moves
  })

  it('follows the path to the given node, not the main line', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[aa](;W[bb])(;W[cc]))')
    const child = tree.root.children[0]
    const variation = child.children[1]
    analysisByTurn.value = new Map<number, AnalyzeResponse>([
      [tree.root.id, fakeAnalysis(5, 1000)],
      [child.id, fakeAnalysis(4, 1000)],
      [variation.id, fakeAnalysis(3, 1000)]
    ])

    const sequence = buildOpeningSequence(tree, variation.id, 9)

    expect(sequence).toEqual([
      { turnNumber: 0, scoreLead: 5, visits: 1000 },
      { turnNumber: 1, scoreLead: 4, visits: 1000 },
      { turnNumber: 2, scoreLead: 3, visits: 1000 }
    ])
  })

  it('returns null when analysis is missing for a node inside the window', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[aa];W[bb])')
    const leaf = findMainLineLeaf(tree)
    analysisByTurn.value = new Map<number, AnalyzeResponse>([[tree.root.id, fakeAnalysis(5, 1000)]]) // missing turns 1,2

    expect(buildOpeningSequence(tree, leaf.id, 9)).toBeNull()
  })
})
