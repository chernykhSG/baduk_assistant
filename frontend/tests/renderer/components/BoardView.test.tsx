import { describe, it, expect, afterEach } from 'vitest'
import { render, fireEvent } from '@testing-library/preact'
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
      [
        1,
        {
          id: 'x',
          moveInfos: [],
          rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 },
          ownership: new Array(81).fill(0.9)
        }
      ]
    ])

    const { container } = render(<BoardView />)
    expect(container.querySelector('.shudan-heat_9')).toBeTruthy()
  })

  it('only shows the ownership numeric label for the currently-hovered vertex', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    analysisByTurn.value = new Map([
      [
        leaf.id,
        {
          id: 'x',
          moveInfos: [],
          rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 },
          ownership: new Array(81).fill(0.9)
        }
      ]
    ])

    const { container } = render(<BoardView />)

    // No numeric label anywhere on the board before any hover.
    expect(container.querySelector('.shudan-heatlabel')).toBeNull()

    const vertex = container.querySelector('[data-x="0"][data-y="0"]')
    expect(vertex).toBeTruthy()

    fireEvent.pointerEnter(vertex as Element)
    const label = container.querySelector('.shudan-heatlabel')
    expect(label).toBeTruthy()
    expect(label?.textContent).toBe('0.90')

    // Only the hovered vertex gets a label - no others appear.
    expect(container.querySelectorAll('.shudan-heatlabel').length).toBe(1)

    fireEvent.pointerLeave(vertex as Element)
    expect(container.querySelector('.shudan-heatlabel')).toBeNull()
  })

  it('marks the top candidate move with its rank number', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    analysisByTurn.value = new Map([
      [
        1,
        {
          id: 'x',
          moveInfos: [
            { move: 'C3', winrate: 0.6, scoreLead: 1, visits: 100, prior: 0.5, pv: ['C3', 'G7'] }
          ],
          rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 }
        }
      ]
    ])

    const { container } = render(<BoardView />)
    const markers = Array.from(container.querySelectorAll('.shudan-marker'))
    expect(markers.some((el) => el.textContent === '1')).toBe(true)
  })

  it('marks the last-played move on the board', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    const { container } = render(<BoardView />)
    expect(container.querySelector('.shudan-marker')).toBeTruthy()
  })

  it('renders existing figure and label markup from the SGF node', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]TR[gg]LB[cc:A])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    const { container } = render(<BoardView />)

    const markers = Array.from(container.querySelectorAll('.shudan-marker'))
    expect(markers.some((el) => el.querySelector('path'))).toBe(true) // triangle renders as an svg <path>
    expect(markers.some((el) => el.textContent === 'A')).toBe(true)
  })

  it('lets user markup take priority over a PV candidate label at the same vertex', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]LB[cc:A])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    analysisByTurn.value = new Map([
      [
        1,
        {
          id: 'x',
          // 'cc' (sgf) -> vertex [2,2] -> GTP 'C7' on a 9x9 board (row = 9 - 2 = 7)
          moveInfos: [
            { move: 'C7', winrate: 0.6, scoreLead: 1, visits: 100, prior: 0.5, pv: ['C7'] }
          ],
          rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 }
        }
      ]
    ])

    const { container } = render(<BoardView />)

    const markers = Array.from(container.querySelectorAll('.shudan-marker'))
    // The user's label 'A' wins; the PV rank label '1' must not appear at all,
    // since its only candidate vertex is occupied by the user's own markup.
    expect(markers.some((el) => el.textContent === 'A')).toBe(true)
    expect(markers.some((el) => el.textContent === '1')).toBe(false)
  })
})
