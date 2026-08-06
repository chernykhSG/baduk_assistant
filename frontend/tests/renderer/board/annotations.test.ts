import { describe, it, expect } from 'vitest'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import type { NodeObject } from '@renderer/board/sgfLoader'
import {
  vertexToSgfCoord,
  addFigureMarkup,
  addLabelMarkup,
  removeMarkupAtVertex,
  setComment,
  nextLabelText,
  buildAnnotationMarkerMap,
  emptyMarkerGrid
} from '@renderer/board/annotations'

describe('vertexToSgfCoord', () => {
  it('converts a vertex to the matching SGF coordinate', () => {
    expect(vertexToSgfCoord([0, 0])).toBe('aa')
    expect(vertexToSgfCoord([2, 4])).toBe('ce')
  })
})

describe('addFigureMarkup', () => {
  it('adds a figure property to the target node without mutating the original tree', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    const next = addFigureMarkup(tree, leaf.id, 'TR', [2, 4])

    expect((tree.get(leaf.id) as NodeObject).data.TR).toBeUndefined()
    expect((next.get(leaf.id) as NodeObject).data.TR).toEqual(['ce'])
  })

  it('replaces any existing markup at the same vertex instead of stacking it', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    const withCircle = addFigureMarkup(tree, leaf.id, 'CR', [2, 4])
    const withTriangle = addFigureMarkup(withCircle, leaf.id, 'TR', [2, 4])

    const data = (withTriangle.get(leaf.id) as NodeObject).data
    expect(data.CR).toBeUndefined()
    expect(data.TR).toEqual(['ce'])
  })
})

describe('addLabelMarkup', () => {
  it('adds a coord:text entry to LB', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    const next = addLabelMarkup(tree, leaf.id, [4, 4], 'A')

    expect((next.get(leaf.id) as NodeObject).data.LB).toEqual(['ee:A'])
  })

  it('replaces a figure previously placed at the same vertex', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    const withSquare = addFigureMarkup(tree, leaf.id, 'SQ', [4, 4])
    const withLabel = addLabelMarkup(withSquare, leaf.id, [4, 4], 'A')

    const data = (withLabel.get(leaf.id) as NodeObject).data
    expect(data.SQ).toBeUndefined()
    expect(data.LB).toEqual(['ee:A'])
  })
})

describe('removeMarkupAtVertex', () => {
  it('removes a figure at the given vertex', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    const withMarker = addFigureMarkup(tree, leaf.id, 'MA', [1, 1])

    const cleared = removeMarkupAtVertex(withMarker, leaf.id, [1, 1])

    expect((cleared.get(leaf.id) as NodeObject).data.MA).toBeUndefined()
  })

  it('removes a label at the given vertex without touching other labels', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    const withLabels = addLabelMarkup(
      addLabelMarkup(tree, leaf.id, [0, 0], 'A'),
      leaf.id,
      [1, 0],
      'B'
    )

    const cleared = removeMarkupAtVertex(withLabels, leaf.id, [0, 0])

    expect((cleared.get(leaf.id) as NodeObject).data.LB).toEqual(['ba:B'])
  })

  it('is a no-op when there is no markup at the vertex', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    const result = removeMarkupAtVertex(tree, leaf.id, [3, 3])

    expect((result.get(leaf.id) as NodeObject).data).toEqual((tree.get(leaf.id) as NodeObject).data)
  })
})

describe('setComment', () => {
  it('sets the C property on the target node', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    const next = setComment(tree, leaf.id, 'Хороший ход')

    expect((next.get(leaf.id) as NodeObject).data.C).toEqual(['Хороший ход'])
  })

  it('clears the C property when set to an empty string', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]C[old])')
    const leaf = findMainLineLeaf(tree)

    const next = setComment(tree, leaf.id, '')

    expect((next.get(leaf.id) as NodeObject).data.C).toBeUndefined()
  })
})

describe('nextLabelText', () => {
  it('suggests A for the first letter label', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    expect(nextLabelText(tree.get(leaf.id) as NodeObject, 'letter')).toBe('A')
  })

  it('suggests the next unused letter after existing letter labels', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]LB[aa:A][bb:B])')
    const leaf = findMainLineLeaf(tree)
    expect(nextLabelText(tree.get(leaf.id) as NodeObject, 'letter')).toBe('C')
  })

  it('suggests 1 for the first number label, ignoring letter labels', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]LB[aa:A])')
    const leaf = findMainLineLeaf(tree)
    expect(nextLabelText(tree.get(leaf.id) as NodeObject, 'number')).toBe('1')
  })

  it('suggests the next unused number after existing number labels', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]LB[aa:1][bb:2])')
    const leaf = findMainLineLeaf(tree)
    expect(nextLabelText(tree.get(leaf.id) as NodeObject, 'number')).toBe('3')
  })
})

describe('emptyMarkerGrid', () => {
  it('returns a boardSize x boardSize grid of nulls', () => {
    const grid = emptyMarkerGrid(3)
    expect(grid).toEqual([
      [null, null, null],
      [null, null, null],
      [null, null, null]
    ])
  })
})

describe('buildAnnotationMarkerMap', () => {
  it('renders figures and labels from node data at their board positions', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]TR[gg]SQ[cc]CR[aa]MA[ii]LB[ee:A])')
    const leaf = findMainLineLeaf(tree)

    const grid = buildAnnotationMarkerMap(tree.get(leaf.id) as NodeObject, 9)

    // SGF 'gg' -> vertex [6, 6], 'cc' -> [2, 2], 'aa' -> [0, 0], 'ii' -> [8, 8], 'ee' -> [4, 4]
    expect(grid[6][6]).toEqual({ type: 'triangle' })
    expect(grid[2][2]).toEqual({ type: 'square' })
    expect(grid[0][0]).toEqual({ type: 'circle' })
    expect(grid[8][8]).toEqual({ type: 'cross' })
    expect(grid[4][4]).toEqual({ type: 'label', label: 'A' })
  })

  it('returns an empty grid for a node with no markup', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)

    expect(buildAnnotationMarkerMap(tree.get(leaf.id) as NodeObject, 9)).toEqual(emptyMarkerGrid(9))
  })

  it('skips out-of-range markup coordinates instead of throwing', () => {
    // 'zz' -> vertex [25, 25], far outside a 9x9 board (e.g. leftover 19-board
    // markup, or a hand-edited/foreign SGF).
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]TR[zz]SQ[cc])')
    const leaf = findMainLineLeaf(tree)
    const node = tree.get(leaf.id) as NodeObject

    let grid: ReturnType<typeof buildAnnotationMarkerMap> | undefined
    expect(() => {
      grid = buildAnnotationMarkerMap(node, 9)
    }).not.toThrow()

    // Other valid markup on the same node still renders normally.
    expect(grid![2][2]).toEqual({ type: 'square' })
    // No marker exists anywhere for the malformed 'zz' entry — every cell is
    // either null or the one valid square marker above.
    const onlyExpectedMarkers = grid!.every((row) =>
      row.every((cell) => cell === null || cell.type === 'square')
    )
    expect(onlyExpectedMarkers).toBe(true)
  })
})
