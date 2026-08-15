import { useEffect, useState } from 'preact/hooks'
import type { JSX } from 'preact'
import { currentTree, currentNodeId, currentMoveAnalysis, analysisByTurn } from '../state/appState'
import { getBoardSize } from '../board/sgfLoader'
import type { NodeObject } from '../board/sgfLoader'
import { gtpMoves, sgfCoordToGtp, buildOpeningSequence } from '../board/gameRequestBuilder'
import { explainPosition, explainOpening } from '../ipc/client'
import type { ExplainResponse } from '../ipc/client'

export function LlmExplanationPanel(): JSX.Element {
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [result, setResult] = useState<ExplainResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const analysis = currentMoveAnalysis.value
  const tree = currentTree.value
  const nodeId = currentNodeId.value

  // Any previously fetched explanation/error is only valid for the position
  // it was requested for — clear it whenever the current board position
  // changes so a stale summary can't silently linger under a now-enabled
  // button that looks current for a different position.
  useEffect(() => {
    setStatus('idle')
    setResult(null)
    setErrorMessage(null)
  }, [nodeId])

  async function handleExplain(): Promise<void> {
    if (!tree || nodeId === null || !analysis) return
    // Capture the position this specific request was made for, so that if
    // the user navigates elsewhere before the response arrives, the stale
    // response below can be detected and dropped instead of repopulating
    // the panel with an explanation attributed to the wrong position.
    const requestedNodeId = nodeId
    setStatus('loading')
    setErrorMessage(null)
    try {
      const boardSize = getBoardSize(tree)
      const moves = gtpMoves(tree, requestedNodeId, boardSize)

      const node = tree.get(requestedNodeId) as NodeObject
      const child = node.children[0] as NodeObject | undefined
      let analysisAfter: typeof analysis | undefined
      let nextMove: [string, string] | undefined
      if (child) {
        const childAnalysis = analysisByTurn.value.get(child.id)
        const color = child.data.B ? 'B' : child.data.W ? 'W' : null
        const sgfCoord = child.data.B?.[0] ?? child.data.W?.[0] ?? null
        if (childAnalysis && color) {
          analysisAfter = childAnalysis
          nextMove = [color, sgfCoordToGtp(sgfCoord, boardSize)]
        }
      }

      const response = await explainPosition({
        moves,
        boardXSize: boardSize,
        boardYSize: boardSize,
        analysis,
        analysisAfter,
        nextMove
      })
      if (currentNodeId.value !== requestedNodeId) return
      setResult(response)
      setStatus('done')
    } catch (err) {
      if (currentNodeId.value !== requestedNodeId) return
      setErrorMessage(err instanceof Error ? err.message : 'Не удалось получить объяснение')
      setStatus('error')
    }
  }

  const [openingColor, setOpeningColor] = useState<'B' | 'W'>('B')
  const [openingStatus, setOpeningStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [openingResult, setOpeningResult] = useState<ExplainResponse | null>(null)
  const [openingErrorMessage, setOpeningErrorMessage] = useState<string | null>(null)

  const openingSequence = tree && nodeId !== null ? buildOpeningSequence(tree, nodeId, getBoardSize(tree)) : null
  const analysisAtEnd = nodeId !== null ? analysisByTurn.value.get(nodeId) : undefined

  async function handleExplainOpening(): Promise<void> {
    if (!tree || nodeId === null || !openingSequence) return
    if (!analysisAtEnd) return
    const boardSize = getBoardSize(tree)
    setOpeningStatus('loading')
    setOpeningErrorMessage(null)
    try {
      const response = await explainOpening({
        moves: gtpMoves(tree, nodeId, boardSize),
        boardXSize: boardSize,
        boardYSize: boardSize,
        color: openingColor,
        openingSequence,
        analysisAtEnd
      })
      setOpeningResult(response)
      setOpeningStatus('done')
    } catch (err) {
      setOpeningErrorMessage(err instanceof Error ? err.message : 'Не удалось получить объяснение')
      setOpeningStatus('error')
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
        <>
          <div
            class={
              result.verified
                ? 'llm-explanation-panel__verified llm-explanation-panel__verified--true'
                : 'llm-explanation-panel__verified llm-explanation-panel__verified--false'
            }
          >
            {result.verified ? 'Проверено' : 'Не удалось проверить численно'}
          </div>
          <div class="llm-explanation-panel__summary">{result.explanation.summary}</div>
          {result.citation && (
            <details class="llm-explanation-panel__citation">
              <summary>
                {result.citation.title}{' '}
                <span class="llm-explanation-panel__citation-source">({result.citation.source})</span>
              </summary>
              <div class="llm-explanation-panel__citation-text">{result.citation.text_snippet}</div>
            </details>
          )}
        </>
      )}
      <div class="llm-explanation-panel__opening">
        <h3>Дебют</h3>
        <label>
          <input
            type="radio"
            name="opening-color"
            checked={openingColor === 'B'}
            onChange={() => setOpeningColor('B')}
          />
          Чёрные
        </label>
        <label>
          <input
            type="radio"
            name="opening-color"
            checked={openingColor === 'W'}
            onChange={() => setOpeningColor('W')}
          />
          Белые
        </label>
        <button
          type="button"
          disabled={!openingSequence || !analysisAtEnd || openingStatus === 'loading'}
          onClick={handleExplainOpening}
        >
          {openingStatus === 'loading' ? 'Анализирую...' : 'Проанализировать дебют'}
        </button>
        {openingStatus === 'error' && (
          <div class="llm-explanation-panel__error">{openingErrorMessage}</div>
        )}
        {openingStatus === 'done' && openingResult?.message && (
          <div class="llm-explanation-panel__message">{openingResult.message}</div>
        )}
        {openingStatus === 'done' && openingResult?.explanation && (
          <>
            <div
              class={
                openingResult.verified
                  ? 'llm-explanation-panel__verified llm-explanation-panel__verified--true'
                  : 'llm-explanation-panel__verified llm-explanation-panel__verified--false'
              }
            >
              {openingResult.verified ? 'Проверено' : 'Не удалось проверить численно'}
            </div>
            <div class="llm-explanation-panel__summary">{openingResult.explanation.summary}</div>
            {openingResult.citation && (
              <details class="llm-explanation-panel__citation">
                <summary>
                  {openingResult.citation.title}{' '}
                  <span class="llm-explanation-panel__citation-source">
                    ({openingResult.citation.source})
                  </span>
                </summary>
                <div class="llm-explanation-panel__citation-text">
                  {openingResult.citation.text_snippet}
                </div>
              </details>
            )}
          </>
        )}
      </div>
    </div>
  )
}
