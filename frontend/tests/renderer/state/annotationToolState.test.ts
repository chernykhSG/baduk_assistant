import { describe, it, expect, beforeEach } from 'vitest'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import { currentTree, currentNodeId } from '@renderer/state/appState'
import {
  selectedAnnotationTool,
  labelMode,
  labelTextOverride,
  pendingLabelText
} from '@renderer/state/annotationToolState'

beforeEach(() => {
  currentTree.value = null
  currentNodeId.value = null
  selectedAnnotationTool.value = null
  labelMode.value = 'letter'
  labelTextOverride.value = null
})

describe('pendingLabelText', () => {
  it('is empty when there is no current node', () => {
    expect(pendingLabelText.value).toBe('')
  })

  it('suggests the next label for the current node when no override is set', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]LB[aa:A])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    expect(pendingLabelText.value).toBe('B')
  })

  it('uses number mode when selected', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    labelMode.value = 'number'

    expect(pendingLabelText.value).toBe('1')
  })

  it('prefers a manual override over the auto-suggestion', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    labelTextOverride.value = 'X'

    expect(pendingLabelText.value).toBe('X')
  })
})
