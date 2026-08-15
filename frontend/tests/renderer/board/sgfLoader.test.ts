import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  parseSgf,
  SgfParseError,
  getBoardSize,
  findMainLineLeaf,
  mainLineNodeIds,
  movesFromRootToNode,
  nodeIdsFromRootToNode
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

  it('throws SgfParseError on rectangular boards', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[19:13];B[qd])')
    expect(() => getBoardSize(tree)).toThrow(SgfParseError)
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

describe('mainLineNodeIds', () => {
  it('lists node ids from root to leaf, index i being the node at turn i', () => {
    const tree = parseSgf(fixtureContent)
    const leaf = findMainLineLeaf(tree)
    const ids = mainLineNodeIds(tree)

    expect(ids[0]).toBe(tree.root.id)
    expect(ids[ids.length - 1]).toBe(leaf.id)
    expect(ids.length).toBe(movesFromRootToNode(tree, leaf.id).length + 1)
  })

  it('only follows the first-child branch, excluding variation nodes', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee](;W[ec])(;W[gc]))')
    const ids = mainLineNodeIds(tree)
    type Node = { id: number; children: Node[] }
    const bMoveNode = (tree.root as Node).children[0]
    const mainLineVariation = bMoveNode.children[0]
    const otherVariation = bMoveNode.children[1]

    expect(ids).toEqual([tree.root.id, bMoveNode.id, mainLineVariation.id])
    expect(ids).not.toContain(otherVariation.id)
  })
})

describe('nodeIdsFromRootToNode', () => {
  it('returns node ids along the path from root to the given node, root first', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[gg])')
    const child = tree.root.children[0]
    const grandchild = child.children[0]

    expect(nodeIdsFromRootToNode(tree, grandchild.id)).toEqual([tree.root.id, child.id, grandchild.id])
  })

  it('follows a variation branch, not the main line', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee](;W[gg])(;W[cc]))')
    const child = tree.root.children[0]
    const variation = child.children[1] // W[cc], the second branch

    expect(nodeIdsFromRootToNode(tree, variation.id)).toEqual([tree.root.id, child.id, variation.id])
  })

  it('returns just the root when nodeId is the root', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9])')

    expect(nodeIdsFromRootToNode(tree, tree.root.id)).toEqual([tree.root.id])
  })
})
