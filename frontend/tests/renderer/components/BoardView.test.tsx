import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/preact'
import { BoardView } from '@renderer/board/BoardView'
import { currentTree, currentNodeId } from '@renderer/state/appState'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'

afterEach(() => {
  currentTree.value = null
  currentNodeId.value = null
})

describe('BoardView', () => {
  it('shows a placeholder when no game is loaded', () => {
    const { getByText } = render(<BoardView />)
    expect(getByText(/Откройте SGF/i)).toBeTruthy()
  })

  it('renders the Shudan board once a position is available', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    const { container } = render(<BoardView />)
    expect(container.querySelector('.shudan-goban')).toBeTruthy()
  })
})
