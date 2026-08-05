import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/preact'
import { LlmExplanationPanel } from '@renderer/analysis/LlmExplanationPanel'
import { currentTree, currentNodeId, analysisByTurn } from '@renderer/state/appState'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import { explainPosition } from '@renderer/ipc/client'

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

  it('shows the explanation summary after a successful call', async () => {
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
})
