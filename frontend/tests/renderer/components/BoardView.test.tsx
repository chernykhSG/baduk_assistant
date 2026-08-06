import { describe, it, expect, afterEach } from 'vitest'
import { render, fireEvent } from '@testing-library/preact'
import { BoardView } from '@renderer/board/BoardView'
import { currentTree, currentNodeId, analysisByTurn } from '@renderer/state/appState'
import { selectedAnnotationTool, labelTextOverride } from '@renderer/state/annotationToolState'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'

afterEach(() => {
  currentTree.value = null
  currentNodeId.value = null
  analysisByTurn.value = new Map()
  selectedAnnotationTool.value = null
  labelTextOverride.value = null
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

  it('places a triangle at the clicked vertex when the triangle tool is selected', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    selectedAnnotationTool.value = 'TR'

    const { container } = render(<BoardView />)
    const vertex = container.querySelector('[data-x="2"][data-y="2"]')
    fireEvent.click(vertex as Element)

    expect((currentTree.value!.get(leaf.id) as { data: Record<string, string[]> }).data.TR).toEqual(
      ['cc']
    )
  })

  it('places the pending label text and then resets the override for the next placement', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    selectedAnnotationTool.value = 'LB'
    labelTextOverride.value = 'Z'

    const { container } = render(<BoardView />)
    const vertex = container.querySelector('[data-x="0"][data-y="0"]')
    fireEvent.click(vertex as Element)

    expect((currentTree.value!.get(leaf.id) as { data: Record<string, string[]> }).data.LB).toEqual(
      ['aa:Z']
    )
    expect(labelTextOverride.value).toBeNull()
  })

  it('erases markup at the clicked vertex when the eraser tool is selected', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]MA[cc])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    selectedAnnotationTool.value = 'erase'

    const { container } = render(<BoardView />)
    const vertex = container.querySelector('[data-x="2"][data-y="2"]')
    fireEvent.click(vertex as Element)

    expect(
      (currentTree.value!.get(leaf.id) as { data: Record<string, string[]> }).data.MA
    ).toBeUndefined()
  })

  it('does nothing when no annotation tool is selected', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    const { container } = render(<BoardView />)
    const vertex = container.querySelector('[data-x="2"][data-y="2"]')
    fireEvent.click(vertex as Element)

    expect(
      (currentTree.value!.get(leaf.id) as { data: Record<string, string[]> }).data.TR
    ).toBeUndefined()
  })

  it('renders one button per annotation tool in the toolbar', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    const { container } = render(<BoardView />)
    const buttons = container.querySelectorAll('.board-view__annotation-toolbar button')
    // Triangle, square, circle, cross, label, eraser
    expect(buttons.length).toBe(6)
  })
})
