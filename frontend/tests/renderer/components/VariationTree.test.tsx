import { describe, it, expect, afterEach } from 'vitest'
import { render, fireEvent } from '@testing-library/preact'
import { VariationTree } from '@renderer/board/VariationTree'
import { currentTree, currentNodeId } from '@renderer/state/appState'
import { parseSgf } from '@renderer/board/sgfLoader'

afterEach(() => {
  currentTree.value = null
  currentNodeId.value = null
})

describe('VariationTree', () => {
  it('renders nothing meaningful when no tree is loaded', () => {
    const { container } = render(<VariationTree />)
    expect(container.textContent).toBe('')
  })

  it('steps to the next node on ArrowDown and back on ArrowUp, regardless of focus', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[ec])')
    currentTree.value = tree
    currentNodeId.value = tree.root.id

    render(<VariationTree />)

    fireEvent.keyDown(window, { key: 'ArrowDown' })
    expect(currentNodeId.value).toBe(tree.root.children[0].id)

    fireEvent.keyDown(window, { key: 'ArrowUp' })
    expect(currentNodeId.value).toBe(tree.root.id)
  })

  it('does nothing on ArrowDown at a leaf with no children', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = tree.root.children[0]
    currentTree.value = tree
    currentNodeId.value = leaf.id

    render(<VariationTree />)
    fireEvent.keyDown(window, { key: 'ArrowDown' })

    expect(currentNodeId.value).toBe(leaf.id)
  })
})
