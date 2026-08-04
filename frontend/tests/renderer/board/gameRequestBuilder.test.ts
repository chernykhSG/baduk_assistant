import { describe, it, expect } from 'vitest'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import { sgfCoordToGtp, mapSgfRules, buildAnalyzeRequest, buildStreamRequest } from '@renderer/board/gameRequestBuilder'

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
        ['B', 'P3'],
      ],
      rules: 'chinese',
      komi: 7.5,
      boardXSize: 19,
      boardYSize: 19,
      analyzeTurns: [3],
      maxVisits: 500,
      includeOwnership: true,
    })
  })
})

describe('buildStreamRequest', () => {
  it('builds a request covering every turn of the main line', () => {
    const tree = parseSgf(fixtureContent)
    const request = buildStreamRequest(tree, { maxVisits: 500 })

    expect(request.moves).toEqual([
      ['B', 'R16'],
      ['W', 'D17'],
      ['B', 'P3'],
    ])
    expect(request.turnNumbers).toEqual([0, 1, 2, 3])
    expect(request.rules).toBe('chinese')
    expect(request.komi).toBe(7.5)
  })
})
