import { describe, it, expect } from 'vitest'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import { sgfCoordToVertex, boardPositionFromMoves } from '@renderer/board/boardPosition'

describe('sgfCoordToVertex', () => {
  it('converts SGF coordinates to zero-based [x, y] vertices', () => {
    expect(sgfCoordToVertex('dd')).toEqual([3, 3])
    expect(sgfCoordToVertex('aa')).toEqual([0, 0])
  })

  it('maps a null/empty coordinate to null (pass)', () => {
    expect(sgfCoordToVertex(null)).toBeNull()
    expect(sgfCoordToVertex('')).toBeNull()
  })
})

describe('boardPositionFromMoves', () => {
  it('replays moves onto an empty board and returns the resulting signMap', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[ec])')
    const leaf = findMainLineLeaf(tree)
    const { signMap, boardSize } = boardPositionFromMoves(tree, leaf.id)

    expect(boardSize).toBe(9)
    expect(signMap[4][4]).toBe(1) // 'ee' -> [4,4], black
    expect(signMap[2][4]).toBe(-1) // 'ec' -> [4,2], white
    expect(signMap[0][0]).toBe(0)
  })

  it('applies captures automatically (surrounded stone is removed)', () => {
    // 5x5 board: white stone at center [2,2] surrounded by black on all 4 sides
    const tree = parseSgf('(;GM[1]FF[4]SZ[5];W[cc];B[bc];B[dc];B[cb];B[cd])')
    const leaf = findMainLineLeaf(tree)
    const { signMap } = boardPositionFromMoves(tree, leaf.id)

    expect(signMap[2][2]).toBe(0) // white stone at [2,2] captured after the 4th black move
  })
})
