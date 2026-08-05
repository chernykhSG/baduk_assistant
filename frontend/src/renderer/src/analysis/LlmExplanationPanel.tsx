import { useState } from 'preact/hooks'
import type { JSX } from 'preact'
import { currentTree, currentNodeId, currentMoveAnalysis } from '../state/appState'
import { getBoardSize } from '../board/sgfLoader'
import { gtpMoves } from '../board/gameRequestBuilder'
import { explainPosition } from '../ipc/client'
import type { ExplainResponse } from '../ipc/client'

export function LlmExplanationPanel(): JSX.Element {
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [result, setResult] = useState<ExplainResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const analysis = currentMoveAnalysis.value
  const tree = currentTree.value
  const nodeId = currentNodeId.value

  async function handleExplain(): Promise<void> {
    if (!tree || nodeId === null || !analysis) return
    setStatus('loading')
    setErrorMessage(null)
    try {
      const boardSize = getBoardSize(tree)
      const moves = gtpMoves(tree, nodeId, boardSize)
      const response = await explainPosition({
        moves,
        boardXSize: boardSize,
        boardYSize: boardSize,
        analysis
      })
      setResult(response)
      setStatus('done')
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Не удалось получить объяснение')
      setStatus('error')
    }
  }

  return (
    <div class="llm-explanation-panel">
      <button type="button" disabled={!analysis || status === 'loading'} onClick={handleExplain}>
        {status === 'loading' ? 'Анализирую...' : 'Объяснить эту позицию'}
      </button>
      {status === 'error' && <div class="llm-explanation-panel__error">{errorMessage}</div>}
      {status === 'done' && result?.message && (
        <div class="llm-explanation-panel__message">{result.message}</div>
      )}
      {status === 'done' && result?.explanation && (
        <div class="llm-explanation-panel__summary">{result.explanation.summary}</div>
      )}
    </div>
  )
}
