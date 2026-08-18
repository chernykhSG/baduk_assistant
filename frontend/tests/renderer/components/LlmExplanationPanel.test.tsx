import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/preact'
import { LlmExplanationPanel } from '@renderer/analysis/LlmExplanationPanel'
import {
  currentTree,
  currentNodeId,
  analysisByTurn,
  gameLoadSequence
} from '@renderer/state/appState'
import {
  parseSgf,
  findMainLineLeaf,
  mainLineNodeIds,
  nodeIdsFromRootToNode
} from '@renderer/board/sgfLoader'
import { explainPosition, explainOpening, askQuestion } from '@renderer/ipc/client'
import type { ExplainResponse, AskResponse } from '@renderer/ipc/client'

vi.mock('@renderer/ipc/client', () => ({
  explainPosition: vi.fn(),
  explainOpening: vi.fn(),
  askQuestion: vi.fn()
}))

const mockExplainPosition = vi.mocked(explainPosition)
const mockExplainOpening = vi.mocked(explainOpening)
const mockAskQuestion = vi.mocked(askQuestion)

afterEach(() => {
  currentTree.value = null
  currentNodeId.value = null
  analysisByTurn.value = new Map()
  gameLoadSequence.value = 0
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

function loadOpeningReadyPosition(): void {
  const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[gg])')
  const leaf = findMainLineLeaf(tree)
  const nodeIds = nodeIdsFromRootToNode(tree, leaf.id)
  currentTree.value = tree
  currentNodeId.value = leaf.id
  analysisByTurn.value = new Map(
    nodeIds.map((id, turn) => [
      id,
      {
        id: String(turn),
        moveInfos: [],
        rootInfo: { winrate: 0.5, scoreLead: 5 - turn, visits: 1000 },
        ownership: undefined
      }
    ])
  )
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
      message: null,
      citation: null
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
      message: null,
      citation: null
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
      message: 'Ничего заметного не найдено в этой позиции',
      citation: null
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
      message: null,
      citation: null
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
      message: null,
      citation: null
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
      message: null,
      citation: null
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
      message: null,
      citation: null
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

  it('shows a collapsible citation section, closed by default, that opens when clicked', async () => {
    loadPosition()
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Объяснение с цитатой', claims: [] },
      verified: true,
      message: null,
      citation: {
        doc_id: 'two-eyes-necessary',
        title: 'Два глаза',
        source: 'principles/two-eyes.md',
        text_snippet: 'Группа с двумя глазами не может быть захвачена.'
      }
    })

    const { getByText, container } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(getByText('Два глаза', { exact: false })).toBeTruthy()
    })

    const details = container.querySelector(
      'details.llm-explanation-panel__citation'
    ) as HTMLDetailsElement
    expect(details).toBeTruthy()
    expect(details.open).toBe(false)

    const summary = details.querySelector('summary') as HTMLElement
    fireEvent.click(summary)
    expect(details.open).toBe(true)
  })

  it('omits the citation section entirely when the response has no citation', async () => {
    loadPosition()
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Объяснение без цитаты', claims: [] },
      verified: true,
      message: null,
      citation: null
    })

    const { getByText, container } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(getByText('Объяснение без цитаты')).toBeTruthy()
    })
    expect(container.querySelector('.llm-explanation-panel__citation')).toBeNull()
  })

  it('disables the opening button when opening-window analysis is incomplete', () => {
    const { getByText } = render(<LlmExplanationPanel />)

    expect((getByText('Проанализировать дебют') as HTMLButtonElement).disabled).toBe(true)
  })

  it('calls explainOpening with the selected color and shows the result', async () => {
    loadOpeningReadyPosition()
    mockExplainOpening.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Разбор дебюта', claims: [] },
      verified: true,
      message: null,
      citation: null
    })

    const { getByText, getByLabelText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByLabelText('Белые'))
    fireEvent.click(getByText('Проанализировать дебют'))

    await waitFor(() => {
      expect(getByText('Разбор дебюта')).toBeTruthy()
    })
    expect(mockExplainOpening).toHaveBeenCalledWith(expect.objectContaining({ color: 'W' }))
  })

  it('keeps the opening result when the current board position changes', async () => {
    loadOpeningReadyPosition()
    mockExplainOpening.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Разбор дебюта', claims: [] },
      verified: true,
      message: null,
      citation: null
    })

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Проанализировать дебют'))
    await waitFor(() => {
      expect(getByText('Разбор дебюта')).toBeTruthy()
    })

    const nodeIds = nodeIdsFromRootToNode(currentTree.value!, currentNodeId.value!)
    currentNodeId.value = nodeIds[1] // navigate elsewhere - the per-move panel resets, the opening block must not

    expect(getByText('Разбор дебюта')).toBeTruthy()
  })

  it('calls explainOpening with the opening-window-boundary analysis, not the current node\'s analysis', async () => {
    // 11 moves on a 9x9 board: the opening window is floor(81*0.12)=9, so
    // buildOpeningSequence covers turns 0..9 (10 nodes, indices 0..9) - the
    // window's boundary node is nodeIds[9]. The current node (leaf, index
    // 11) lies well past the window and has its own, deliberately
    // different, analysis - explainOpening must be sent the boundary's
    // rootInfo, not the current node's.
    const tree = parseSgf(
      '(;GM[1]FF[4]SZ[9];B[ee];W[gg];B[cc];W[dd];B[ff];W[hh];B[bb];W[ib];B[gc];W[fd];B[ea])'
    )
    const leaf = findMainLineLeaf(tree)
    const nodeIds = nodeIdsFromRootToNode(tree, leaf.id)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    const boundaryAnalysis = {
      id: 'boundary',
      moveInfos: [],
      rootInfo: { winrate: 0.5, scoreLead: 3, visits: 1000 },
      ownership: undefined
    }
    const currentNodeAnalysis = {
      id: 'current',
      moveInfos: [],
      rootInfo: { winrate: 0.1, scoreLead: -20, visits: 500 },
      ownership: undefined
    }
    const entries = new Map(
      nodeIds.slice(0, 9).map((id, turn) => [
        id,
        {
          id: String(turn),
          moveInfos: [],
          rootInfo: { winrate: 0.5, scoreLead: 5 - turn, visits: 1000 },
          ownership: undefined
        }
      ])
    )
    entries.set(nodeIds[9], boundaryAnalysis)
    entries.set(nodeIds[11], currentNodeAnalysis)
    analysisByTurn.value = entries

    mockExplainOpening.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Разбор дебюта', claims: [] },
      verified: true,
      message: null,
      citation: null
    })

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Проанализировать дебют'))

    await waitFor(() => {
      expect(mockExplainOpening).toHaveBeenCalledWith(
        expect.objectContaining({ analysisAtEnd: boundaryAnalysis })
      )
    })
  })

  it('shows a hint when the opening window is not fully analyzed, and hides it once it is', async () => {
    const { getByText, queryByText } = render(<LlmExplanationPanel />)

    expect(getByText('Дебют ещё не полностью проанализирован')).toBeTruthy()

    loadOpeningReadyPosition()

    await waitFor(() => {
      expect(queryByText('Дебют ещё не полностью проанализирован')).toBeNull()
    })
  })

  it('resets the opening result when a different game is loaded', async () => {
    loadOpeningReadyPosition()
    mockExplainOpening.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Разбор дебюта', claims: [] },
      verified: true,
      message: null,
      citation: null
    })

    const { getByText, queryByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Проанализировать дебют'))
    await waitFor(() => {
      expect(getByText('Разбор дебюта')).toBeTruthy()
    })

    // Simulate loading an entirely different SGF file, as App.tsx's
    // loadGame() does on file load: a fresh GameTree object (not just a
    // different node within the same tree), a new current node, fresh
    // per-turn analysis, AND incrementing gameLoadSequence (the actual
    // signal the reset effect is keyed on - see the next test for why
    // `tree` reference alone is not a safe proxy for "a new game loaded").
    const otherTree = parseSgf('(;GM[1]FF[4]SZ[9];B[cc])')
    const otherLeaf = findMainLineLeaf(otherTree)
    currentTree.value = otherTree
    currentNodeId.value = otherLeaf.id
    analysisByTurn.value = new Map()
    gameLoadSequence.value += 1

    await waitFor(() => {
      expect(queryByText('Разбор дебюта')).toBeNull()
    })
  })

  it('keeps the opening result across an in-game tree mutation (e.g. adding board markup or a comment)', async () => {
    loadOpeningReadyPosition()
    mockExplainOpening.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Разбор дебюта', claims: [] },
      verified: true,
      message: null,
      citation: null
    })

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Проанализировать дебют'))
    await waitFor(() => {
      expect(getByText('Разбор дебюта')).toBeTruthy()
    })

    // Simulate what AnnotationPanel.tsx's setComment / BoardView.tsx's
    // markup tools actually do: reassign currentTree.value to a new
    // GameTree object produced by tree.mutate() for the SAME game -
    // deliberately without touching gameLoadSequence, exactly as those
    // components do. The opening result must NOT be wiped by this.
    const mutatedTree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[gg])')
    currentTree.value = mutatedTree

    expect(getByText('Разбор дебюта')).toBeTruthy()
  })

  it('disables the ask button when the question field is empty', () => {
    loadPosition()
    const { getByText } = render(<LlmExplanationPanel />)
    expect((getByText('Спросить') as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows a verified answer after a successful ask', async () => {
    loadPosition()
    mockAskQuestion.mockResolvedValue({
      answer: 'Winrate сейчас 60%.',
      verified: true,
      message: null,
      citation: null
    } satisfies AskResponse)

    const { getByText, getByPlaceholderText } = render(<LlmExplanationPanel />)
    fireEvent.input(getByPlaceholderText('Задайте вопрос про текущую позицию...'), {
      target: { value: 'какой сейчас winrate?' }
    })
    fireEvent.click(getByText('Спросить'))

    await waitFor(() => {
      expect(getByText('Winrate сейчас 60%.')).toBeTruthy()
    })
  })

  it('shows an error message when askQuestion rejects', async () => {
    loadPosition()
    mockAskQuestion.mockRejectedValue(new Error('askQuestion failed (503): доступно только с llama'))

    const { getByText, getByPlaceholderText } = render(<LlmExplanationPanel />)
    fireEvent.input(getByPlaceholderText('Задайте вопрос про текущую позицию...'), {
      target: { value: 'вопрос' }
    })
    fireEvent.click(getByText('Спросить'))

    await waitFor(() => {
      expect(getByText(/доступно только с llama/)).toBeTruthy()
    })
  })

  it('resets the ask result when the current position changes', async () => {
    // Mirrors the existing 'clears a stale explanation when the current
    // position changes' test above exactly: two real nodes, each with its
    // own analysisByTurn entry, navigate via currentNodeId.value, and assert
    // through waitFor (the reset runs inside a useEffect, not synchronously).
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[gg])')
    const [, nodeA, nodeB] = mainLineNodeIds(tree)
    currentTree.value = tree
    currentNodeId.value = nodeA
    analysisByTurn.value = new Map([
      [nodeA, { id: 'a', moveInfos: [], rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 }, ownership: new Array(81).fill(0) }],
      [nodeB, { id: 'b', moveInfos: [], rootInfo: { winrate: 0.4, scoreLead: -1, visits: 100 }, ownership: new Array(81).fill(0) }]
    ])
    mockAskQuestion.mockResolvedValue({
      answer: 'Ответ про первую позицию',
      verified: true,
      message: null,
      citation: null
    } satisfies AskResponse)

    const { getByText, getByPlaceholderText, queryByText } = render(<LlmExplanationPanel />)
    fireEvent.input(getByPlaceholderText('Задайте вопрос про текущую позицию...'), {
      target: { value: 'вопрос' }
    })
    fireEvent.click(getByText('Спросить'))
    await waitFor(() => expect(getByText('Ответ про первую позицию')).toBeTruthy())

    // Navigate to a different position (B) that also has its own analysis
    // available, without clicking "ask" again.
    currentNodeId.value = nodeB

    await waitFor(() => {
      expect(queryByText('Ответ про первую позицию')).toBeNull()
    })
  })
})
