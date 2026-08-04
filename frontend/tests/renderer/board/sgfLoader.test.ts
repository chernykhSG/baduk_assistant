import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  parseSgf,
  SgfParseError,
  getBoardSize,
  findMainLineLeaf,
  movesFromRootToNode
} from '@renderer/board/sgfLoader'

const fixturePath = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../fixtures/simple-game.sgf'
)
const fixtureContent = fs.readFileSync(fixturePath, 'utf-8')

describe('parseSgf', () => {
  it('parses a valid SGF into a GameTree with the expected root properties', () => {
    const tree = parseSgf(fixtureContent)
    expect(tree.root.data.SZ).toEqual(['19'])
    expect(tree.root.data.KM).toEqual(['7.5'])
    expect(tree.root.children.length).toBe(1)
  })

  it('throws SgfParseError on malformed content', () => {
    expect(() => parseSgf('not valid sgf (((')).toThrow(SgfParseError)
  })

  it('throws SgfParseError when the file has no game trees', () => {
    expect(() => parseSgf('')).toThrow(SgfParseError)
  })
})

describe('getBoardSize', () => {
  it('reads SZ from the root node', () => {
    const tree = parseSgf(fixtureContent)
    expect(getBoardSize(tree)).toBe(19)
  })

  it('defaults to 19 when SZ is absent', () => {
    const tree = parseSgf('(;GM[1]FF[4];B[qd])')
    expect(getBoardSize(tree)).toBe(19)
  })

  it('throws on rectangular boards', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[19:13];B[qd])')
    expect(() => getBoardSize(tree)).toThrow(/Rectangular boards/)
  })
})

describe('findMainLineLeaf + movesFromRootToNode', () => {
  it('walks the first-child line to the final leaf and lists moves in SGF coordinates', () => {
    const tree = parseSgf(fixtureContent)
    const leaf = findMainLineLeaf(tree)
    const moves = movesFromRootToNode(tree, leaf.id)
    expect(moves).toEqual([
      { color: 'B', sgfCoord: 'qd' },
      { color: 'W', sgfCoord: 'dc' },
      { color: 'B', sgfCoord: 'oq' }
    ])
  })

  it('returns an empty list for the root node itself', () => {
    const tree = parseSgf(fixtureContent)
    expect(movesFromRootToNode(tree, tree.root.id)).toEqual([])
  })
})
