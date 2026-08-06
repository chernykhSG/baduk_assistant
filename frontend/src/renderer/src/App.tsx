import { useEffect } from 'preact/hooks'
import { signal, useSignalEffect } from '@preact/signals'
import type { JSX } from 'preact'
import type GameTree from '@sabaki/immutable-gametree'
import { BoardView } from './board/BoardView'
import { VariationTree } from './board/VariationTree'
import { AnalysisPanel } from './analysis/AnalysisPanel'
import { parseSgf, getBoardSize, mainLineNodeIds, SgfParseError } from './board/sgfLoader'
import type { NodeObject } from './board/sgfLoader'
import { buildStreamRequest } from './board/gameRequestBuilder'
import { serializeTree } from './board/sgfSerializer'
import { streamAnalysis } from './ipc/client'
import {
  currentTree,
  currentNodeId,
  analysisByTurn,
  streamStatus,
  streamError,
  currentFilePath,
  isDirty
} from './state/appState'
import { selectedAnnotationTool, labelTextOverride } from './state/annotationToolState'

const DEFAULT_MAX_VISITS = 500

const connectionState = signal<'pending' | 'ready' | 'error'>('pending')
const connectionErrorMessage = signal<string | null>(null)
export const sgfError = signal<string | null>(null)
export const saveError = signal<string | null>(null)
const lastLoadedSgfContent = signal<string | null>(null)
const lastLoadedFilePath = signal<string | null>(null)

let closeCurrentStream: (() => void) | null = null

/**
 * Per user decision: reading foreign-charset SGF is not supported — rather
 * than risk silently corrupting a non-UTF-8 file on overwrite (neither the
 * save path nor the drop-file read path check SGF's CA[] charset property),
 * refuse the write and point the user back at the original program.
 * Returns true if it's safe to proceed with the save.
 */
function checkEncodingBeforeSave(tree: GameTree): boolean {
  const ca = (tree.root as NodeObject).data.CA?.[0]
  if (!ca) return true
  if (/^utf-?8$/i.test(ca.trim())) return true
  saveError.value = `Файл в кодировке ${ca}, не UTF-8 — сохранение отключено, чтобы не повредить партию. Отредактируйте её в исходной программе.`
  return false
}

export function loadGame(content: string, filePath: string | null = null): void {
  closeCurrentStream?.()
  closeCurrentStream = null

  lastLoadedSgfContent.value = content
  lastLoadedFilePath.value = filePath
  sgfError.value = null
  let tree
  try {
    tree = parseSgf(content)
    getBoardSize(tree) // validates board size (throws SgfParseError for rectangular boards) before any state is committed
  } catch (err) {
    sgfError.value = err instanceof SgfParseError ? err.message : 'Не удалось разобрать SGF'
    streamStatus.value = 'idle'
    streamError.value = null
    return
  }

  currentTree.value = tree
  currentNodeId.value = tree.root.id
  currentFilePath.value = filePath
  isDirty.value = false
  saveError.value = null
  selectedAnnotationTool.value = null
  labelTextOverride.value = null
  analysisByTurn.value = new Map()
  streamStatus.value = 'streaming'
  streamError.value = null

  const mainLineIds = mainLineNodeIds(tree)
  const request = buildStreamRequest(tree, { maxVisits: DEFAULT_MAX_VISITS })
  closeCurrentStream = streamAnalysis(request, {
    onProgress(msg) {
      const nodeId = mainLineIds[msg.turnNumber]
      const next = new Map(analysisByTurn.value)
      next.set(nodeId, msg.result)
      analysisByTurn.value = next
    },
    onDone() {
      streamStatus.value = 'done'
    },
    onError(msg) {
      streamStatus.value = 'error'
      streamError.value = msg.detail
    }
  })
}

export async function saveCurrentGame(): Promise<void> {
  const tree = currentTree.value
  if (!tree) return
  saveError.value = null
  if (!checkEncodingBeforeSave(tree)) return
  const content = serializeTree(tree)
  try {
    if (currentFilePath.value) {
      await window.baduk.saveFile(currentFilePath.value, content)
      isDirty.value = false
    } else {
      const result = await window.baduk.saveFileAs(undefined, content)
      if ('canceled' in result) return
      currentFilePath.value = result.path
      isDirty.value = false
    }
  } catch (err) {
    saveError.value = err instanceof Error ? err.message : 'Не удалось сохранить файл'
  }
}

export async function saveCurrentGameAs(): Promise<void> {
  const tree = currentTree.value
  if (!tree) return
  saveError.value = null
  if (!checkEncodingBeforeSave(tree)) return
  const content = serializeTree(tree)
  try {
    const result = await window.baduk.saveFileAs(currentFilePath.value ?? undefined, content)
    if ('canceled' in result) return
    currentFilePath.value = result.path
    isDirty.value = false
  } catch (err) {
    saveError.value = err instanceof Error ? err.message : 'Не удалось сохранить файл'
  }
}

function handleDrop(event: DragEvent): void {
  event.preventDefault()
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  const filePath = window.electron.webUtils.getPathForFile(file) || null
  file.text().then((content) => loadGame(content, filePath))
}

function handleDragOver(event: DragEvent): void {
  event.preventDefault()
}

export function App(): JSX.Element {
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

  useSignalEffect(() => {
    window.baduk.reportDirtyState(isDirty.value)
  })

  useEffect(() => {
    return window.baduk.onSaveBeforeClose(async () => {
      await saveCurrentGame()
      window.baduk.sendSaveBeforeCloseResult(!isDirty.value)
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
      <div class="app-shell__header">
        <span class="app-shell__filename">
          {currentFilePath.value ? currentFilePath.value.split(/[\\/]/).pop() : 'Без файла'}
          {isDirty.value ? ' *' : ''}
        </span>
        <button type="button" disabled={!currentTree.value} onClick={() => void saveCurrentGame()}>
          Сохранить
        </button>
        <button
          type="button"
          disabled={!currentTree.value}
          onClick={() => void saveCurrentGameAs()}
        >
          Сохранить как
        </button>
        {saveError.value && <span class="app-shell__header-error">{saveError.value}</span>}
      </div>
      <div class="app-shell__top">
        <div class="app-shell__tree">
          <VariationTree />
        </div>
        <div class="app-shell__board">
          <BoardView />
          {sgfError.value && (
            <div class="app-shell__banner app-shell__banner--error">{sgfError.value}</div>
          )}
          {streamStatus.value === 'error' && (
            <div class="app-shell__banner app-shell__banner--error">
              Ошибка анализа: {streamError.value}
              <button
                type="button"
                onClick={() =>
                  lastLoadedSgfContent.value &&
                  loadGame(lastLoadedSgfContent.value, lastLoadedFilePath.value)
                }
              >
                Повторить
              </button>
            </div>
          )}
        </div>
      </div>
      <div class="app-shell__chart">
        <AnalysisPanel />
      </div>
    </div>
  )
}
