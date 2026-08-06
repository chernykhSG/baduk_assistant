import { describe, it, expect, afterEach } from 'vitest'
import { render, fireEvent } from '@testing-library/preact'
import { VariationTree } from '@renderer/board/VariationTree'
import { currentTree, currentNodeId } from '@renderer/state/appState'
import { parseSgf } from '@renderer/board/sgfLoader'
import { setComment } from '@renderer/board/annotations'

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

  it('shows the annotation indicator on a node with a comment', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]C[hello])')
    currentTree.value = tree
    currentNodeId.value = tree.root.id

    const { container } = render(<VariationTree />)

    const icon = container.querySelector('.variation-tree__marker-annotation-icon')
    expect(icon).not.toBeNull()
  })

  it('shows the annotation indicator on a node with markup', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]TR[ec])')
    currentTree.value = tree
    currentNodeId.value = tree.root.id

    const { container } = render(<VariationTree />)

    const icon = container.querySelector('.variation-tree__marker-annotation-icon')
    expect(icon).not.toBeNull()
  })

  it('does not show the annotation indicator on a node with neither comment nor markup', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    currentTree.value = tree
    currentNodeId.value = tree.root.id

    const { container } = render(<VariationTree />)

    const icon = container.querySelector('.variation-tree__marker-annotation-icon')
    expect(icon).toBeNull()
  })

  it('does not show the annotation indicator on a node with an emptied comment', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]C[hello])')
    const clearedTree = setComment(tree, tree.root.children[0].id, '')
    currentTree.value = clearedTree
    currentNodeId.value = clearedTree.root.id

    const { container } = render(<VariationTree />)

    const icons = container.querySelectorAll('.variation-tree__marker-annotation-icon')
    expect(icons.length).toBe(0)
  })
})
