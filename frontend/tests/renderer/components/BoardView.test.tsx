import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/preact'
import { BoardView } from '@renderer/board/BoardView'
import { currentTree, currentNodeId, analysisByTurn } from '@renderer/state/appState'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'

afterEach(() => {
  currentTree.value = null
  currentNodeId.value = null
  analysisByTurn.value = new Map()
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

  it('shows ownership heatmap cells when analysis for the current turn is available', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    analysisByTurn.value = new Map([
      [1, { id: 'x', moveInfos: [], rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 }, ownership: new Array(81).fill(0.9) }],
    ])

    const { container } = render(<BoardView />)
    expect(container.querySelector('.shudan-heat_9')).toBeTruthy()
  })

  it('draws a PV line from the first two moves of the top candidate', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    analysisByTurn.value = new Map([
      [
        1,
        {
          id: 'x',
          moveInfos: [{ move: 'C3', winrate: 0.6, scoreLead: 1, visits: 100, prior: 0.5, pv: ['C3', 'G7'] }],
          rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 },
        },
      ],
    ])

    const { container } = render(<BoardView />)
    expect(container.querySelector('.shudan-line')).toBeTruthy()
  })
})
