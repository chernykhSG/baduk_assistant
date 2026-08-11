import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/preact'
import { LlmExplanationPanel } from '@renderer/analysis/LlmExplanationPanel'
import { currentTree, currentNodeId, analysisByTurn } from '@renderer/state/appState'
import { parseSgf, findMainLineLeaf, mainLineNodeIds } from '@renderer/board/sgfLoader'
import { explainPosition } from '@renderer/ipc/client'
import type { ExplainResponse } from '@renderer/ipc/client'

vi.mock('@renderer/ipc/client', () => ({
  explainPosition: vi.fn()
}))

const mockExplainPosition = vi.mocked(explainPosition)

afterEach(() => {
  currentTree.value = null
  currentNodeId.value = null
  analysisByTurn.value = new Map()
  vi.clearAllMocks()
})

function loadPosition(): void {
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
        ownership: new Array(81).fill(0)
      }
    ]
  ])
}

describe('LlmExplanationPanel', () => {
  it('disables the button when there is no analysis for the current position', () => {
    const { getByText } = render(<LlmExplanationPanel />)
    expect((getByText('Объяснить эту позицию') as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows the explanation summary and a verified status after a successful call', async () => {
    loadPosition()
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Тестовое объяснение', claims: [] },
      verified: true,
      message: null
    })

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(getByText('Тестовое объяснение')).toBeTruthy()
      expect(getByText('Проверено')).toBeTruthy()
    })
  })

  it('shows the not-verified status when the explanation failed numeric verification', async () => {
    loadPosition()
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Резервное объяснение', claims: [] },
      verified: false,
      message: null
    })

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(getByText('Резервное объяснение')).toBeTruthy()
      expect(getByText('Не удалось проверить численно')).toBeTruthy()
    })
  })

  it('shows the message banner when nothing is found', async () => {
    loadPosition()
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: null,
      verified: null,
      message: 'Ничего заметного не найдено в этой позиции'
    })

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(getByText('Ничего заметного не найдено в этой позиции')).toBeTruthy()
    })
  })

  it('shows an error banner when the request fails', async () => {
    loadPosition()
    mockExplainPosition.mockRejectedValue(new Error('explainPosition failed (500): boom'))

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(getByText('explainPosition failed (500): boom')).toBeTruthy()
    })
  })

  it('clears a stale explanation when the current position changes', async () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[gg])')
    const [, nodeA, nodeB] = mainLineNodeIds(tree)
    currentTree.value = tree
    currentNodeId.value = nodeA
    analysisByTurn.value = new Map([
      [
        nodeA,
        {
          id: 'a',
          moveInfos: [],
          rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 },
          ownership: new Array(81).fill(0)
        }
      ],
      [
        nodeB,
        {
          id: 'b',
          moveInfos: [],
          rootInfo: { winrate: 0.4, scoreLead: -1, visits: 100 },
          ownership: new Array(81).fill(0)
        }
      ]
    ])
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Объяснение для позиции A', claims: [] },
      verified: true,
      message: null
    })

    const { getByText, queryByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(getByText('Объяснение для позиции A')).toBeTruthy()
    })

    // Navigate to a different position (B) that also has its own analysis
    // available, without clicking "explain" again.
    currentNodeId.value = nodeB

    await waitFor(() => {
      expect(queryByText('Объяснение для позиции A')).toBeNull()
    })
    expect((getByText('Объяснить эту позицию') as HTMLButtonElement).disabled).toBe(false)
  })

  it('drops a stale in-flight response that resolves after navigating away', async () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[gg])')
    const [, nodeA, nodeB] = mainLineNodeIds(tree)
    currentTree.value = tree
    currentNodeId.value = nodeA
    analysisByTurn.value = new Map([
      [
        nodeA,
        {
          id: 'a',
          moveInfos: [],
          rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 },
          ownership: new Array(81).fill(0)
        }
      ],
      [
        nodeB,
        {
          id: 'b',
          moveInfos: [],
          rootInfo: { winrate: 0.4, scoreLead: -1, visits: 100 },
          ownership: new Array(81).fill(0)
        }
      ]
    ])

    let resolveExplain!: (value: ExplainResponse) => void
    mockExplainPosition.mockImplementation(
      () =>
        new Promise<ExplainResponse>((resolve) => {
          resolveExplain = resolve
        })
    )

    const { getByText, queryByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(getByText('Анализирую...')).toBeTruthy()
    })

    // Navigate to a different position while A's request is still in flight.
    currentNodeId.value = nodeB

    // Let the position-change reset (round-1 fix) fully settle first, so this
    // assertion isolates the in-flight-response guard specifically, rather
    // than accidentally passing because of that unrelated effect's timing.
    await waitFor(() => {
      expect((getByText('Объяснить эту позицию') as HTMLButtonElement).disabled).toBe(false)
    })

    // A's response arrives late, after the user has already moved on and
    // settled on B's (already-idle) state.
    resolveExplain({
      finding: null,
      explanation: { summary: 'Объяснение для позиции A (устарело)', claims: [] },
      verified: true,
      message: null
    })

    // Force every pending microtask (the `await explainPosition(...)`
    // continuation and any state-update flush it triggers) to drain before
    // asserting — a `waitFor` whose very first synchronous check happens to
    // pass (simply because the continuation hasn't run yet) would return
    // immediately without ever re-checking, silently hiding the race this
    // test exists to catch.
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(queryByText('Объяснение для позиции A (устарело)')).toBeNull()
    expect((getByText('Объяснить эту позицию') as HTMLButtonElement).disabled).toBe(false)
  })

  it('includes analysisAfter and nextMove when the current node has a main-line child', async () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[gg])')
    const [, nodeA, nodeB] = mainLineNodeIds(tree)
    currentTree.value = tree
    currentNodeId.value = nodeA
    const analysisA = {
      id: 'a',
      moveInfos: [],
      rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 },
      ownership: new Array(81).fill(0)
    }
    const analysisB = {
      id: 'b',
      moveInfos: [],
      rootInfo: { winrate: 0.4, scoreLead: -1, visits: 100 },
      ownership: new Array(81).fill(0)
    }
    analysisByTurn.value = new Map([
      [nodeA, analysisA],
      [nodeB, analysisB]
    ])
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: { summary: 'ok', claims: [] },
      verified: true,
      message: null
    })

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(mockExplainPosition).toHaveBeenCalledWith(
        expect.objectContaining({
          analysisAfter: analysisB,
          nextMove: ['W', 'G3']
        })
      )
    })
  })

  it('omits analysisAfter and nextMove when the current node is the last move', async () => {
    loadPosition()
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: { summary: 'ok', claims: [] },
      verified: true,
      message: null
    })

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(mockExplainPosition).toHaveBeenCalledWith(
        expect.objectContaining({
          analysisAfter: undefined,
          nextMove: undefined
        })
      )
    })
  })
})
