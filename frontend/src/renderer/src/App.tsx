import { useEffect } from 'preact/hooks'
import { signal } from '@preact/signals'
import { BoardView } from './board/BoardView'
import { VariationTree } from './board/VariationTree'
import { WinrateChart } from './analysis/WinrateChart'
import { parseSgf, SgfParseError } from './board/sgfLoader'
import { buildStreamRequest } from './board/gameRequestBuilder'
import { streamAnalysis } from './ipc/client'
import { currentTree, currentNodeId, analysisByTurn, streamStatus, streamError } from './state/appState'

const DEFAULT_MAX_VISITS = 500

const connectionState = signal<'pending' | 'ready' | 'error'>('pending')
const connectionErrorMessage = signal<string | null>(null)
const sgfError = signal<string | null>(null)
const lastLoadedSgfContent = signal<string | null>(null)

function loadGame(content: string) {
  lastLoadedSgfContent.value = content
  sgfError.value = null
  let tree
  try {
    tree = parseSgf(content)
  } catch (err) {
    sgfError.value = err instanceof SgfParseError ? err.message : 'Не удалось разобрать SGF'
    return
  }

  currentTree.value = tree
  currentNodeId.value = tree.root.id
  analysisByTurn.value = new Map()
  streamStatus.value = 'streaming'
  streamError.value = null

  const request = buildStreamRequest(tree, { maxVisits: DEFAULT_MAX_VISITS })
  streamAnalysis(request, {
    onProgress(msg) {
      const next = new Map(analysisByTurn.value)
      next.set(msg.turnNumber, msg.result)
      analysisByTurn.value = next
    },
    onDone() {
      streamStatus.value = 'done'
    },
    onError(msg) {
      streamStatus.value = 'error'
      streamError.value = msg.detail
    },
  })
}

function handleDrop(event: DragEvent) {
  event.preventDefault()
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  file.text().then(loadGame)
}

function handleDragOver(event: DragEvent) {
  event.preventDefault()
}

export function App() {
  useEffect(() => {
    window.baduk
      .getBackendConnection()
      .then(() => {
        connectionState.value = 'ready'
      })
      .catch((err: Error) => {
        connectionState.value = 'error'
        connectionErrorMessage.value = err.message
      })
  }, [])

  if (connectionState.value === 'pending') {
    return <div class="connection-gate">Подключение к backend...</div>
  }

  if (connectionState.value === 'error') {
    return (
      <div class="connection-gate connection-gate--error">
        Не удалось запустить backend: {connectionErrorMessage.value}. Перезапустите приложение.
      </div>
    )
  }

  return (
    <div class="app-shell" onDrop={handleDrop} onDragOver={handleDragOver}>
      <div class="app-shell__top">
        <div class="app-shell__tree">
          <VariationTree />
        </div>
        <div class="app-shell__board">
          <BoardView />
          {sgfError.value && <div class="app-shell__banner app-shell__banner--error">{sgfError.value}</div>}
          {streamStatus.value === 'error' && (
            <div class="app-shell__banner app-shell__banner--error">
              Ошибка анализа: {streamError.value}
              <button
                type="button"
                onClick={() => lastLoadedSgfContent.value && loadGame(lastLoadedSgfContent.value)}
              >
                Повторить
              </button>
            </div>
          )}
        </div>
      </div>
      <div class="app-shell__chart">
        <WinrateChart />
      </div>
    </div>
  )
}
