import { describe, it, expect } from 'vitest'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import { addFigureMarkup, addLabelMarkup, setComment } from '@renderer/board/annotations'
import { serializeTree } from '@renderer/board/sgfSerializer'

describe('serializeTree', () => {
  it('serializes a plain tree back to equivalent SGF text', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9]KM[7.5];B[ee];W[ec])')

    const text = serializeTree(tree)

    expect(text).toContain('GM[1]')
    expect(text).toContain('SZ[9]')
    expect(text).toContain('B[ee]')
    expect(text).toContain('W[ec]')
  })

  it('round-trips annotations added via annotations.ts through parse -> mutate -> serialize -> parse', () => {
    const original = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(original)

    const withTriangle = addFigureMarkup(original, leaf.id, 'TR', [2, 2])
    const withLabel = addLabelMarkup(withTriangle, leaf.id, [4, 4], 'A')
    const withComment = setComment(withLabel, leaf.id, 'Хороший ход')

    const text = serializeTree(withComment)
    const reparsed = parseSgf(text)
    const reparsedLeaf = findMainLineLeaf(reparsed)

    expect(reparsedLeaf.data.TR).toEqual(['cc'])
    expect(reparsedLeaf.data.LB).toEqual(['ee:A'])
    expect(reparsedLeaf.data.C).toEqual(['Хороший ход'])
  })

  it('produces well-formed SGF starting with opening parenthesis', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9]KM[7.5];B[ee];W[ec])')

    const text = serializeTree(tree)

    expect(text.trimStart()).toMatch(/^\(/)
  })
})
