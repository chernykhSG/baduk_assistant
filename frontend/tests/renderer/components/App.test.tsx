import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, fireEvent } from '@testing-library/preact'
import { App, loadGame, sgfError, saveCurrentGame, saveError } from '@renderer/App'
import {
  currentTree,
  currentNodeId,
  streamStatus,
  streamError,
  currentFilePath,
  isDirty
} from '@renderer/state/appState'

beforeEach(() => {
  ;(globalThis as any).window = (globalThis as any).window ?? {}
})

afterEach(() => {
  currentTree.value = null
  currentNodeId.value = null
  streamStatus.value = 'idle'
  streamError.value = null
  sgfError.value = null
  currentFilePath.value = null
  isDirty.value = false
  saveError.value = null
})

describe('App / ConnectionGate', () => {
  it('shows a connection-error screen if the backend connection promise rejects', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockRejectedValue(new Error('backend did not start')),
      reportDirtyState: vi.fn(),
      onSaveBeforeClose: vi.fn().mockReturnValue(() => {})
    }

    const { getByText } = render(<App />)

    await waitFor(() => {
      expect(getByText(/не удалось запустить backend/i)).toBeTruthy()
    })
  })

  it('renders the app shell once the backend connection resolves', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      reportDirtyState: vi.fn(),
      onSaveBeforeClose: vi.fn().mockReturnValue(() => {})
    }

    const { container } = render(<App />)

    await waitFor(() => {
      expect(container.querySelector('.app-shell')).toBeTruthy()
    })
  })
})

describe('loadGame with a rectangular-board SGF', () => {
  it('surfaces an explicit sgfError banner instead of crashing/leaving stale tree state', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      reportDirtyState: vi.fn(),
      onSaveBeforeClose: vi.fn().mockReturnValue(() => {})
    }

    const { container } = render(<App />)
    await waitFor(() => {
      expect(container.querySelector('.app-shell')).toBeTruthy()
    })

    // Must not throw synchronously or produce an unhandled rejection.
    expect(() => loadGame('(;GM[1]FF[4]SZ[19:13];B[qd])')).not.toThrow()

    // Scoped to this test's own container: other <App/> instances mounted by
    // earlier tests in this file share the same global signals and are not
    // unmounted between tests, so a document-wide query would match stale
    // banners from those too.
    await waitFor(() => {
      const banner = container.querySelector('.app-shell__banner--error')
      expect(banner?.textContent).toMatch(/Rectangular boards/i)
    })

    // No tree/node state should have been committed for the rejected SGF.
    expect(currentTree.value).toBeNull()
    expect(currentNodeId.value).toBeNull()
    expect(streamStatus.value).toBe('idle')
    expect(streamError.value).toBeNull()
  })
})

describe('save flow', () => {
  it('shows "Без файла" and disables Save/Save As with no game loaded', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      reportDirtyState: vi.fn(),
      onSaveBeforeClose: vi.fn().mockReturnValue(() => {})
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    const saveButton = getByText('Сохранить') as HTMLButtonElement
    expect(saveButton.disabled).toBe(true)
  })

  it('captures the dropped file path via window.electron.webUtils and marks the game dirty after an edit, then Save writes to that path', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      saveFile: vi.fn().mockResolvedValue(undefined),
      saveFileAs: vi.fn(),
      reportDirtyState: vi.fn(),
      onSaveBeforeClose: vi.fn().mockReturnValue(() => {})
    }
    ;(window as any).electron = {
      webUtils: { getPathForFile: vi.fn().mockReturnValue('/games/example.sgf') }
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    loadGame('(;GM[1]FF[4]SZ[9];B[ee])', '/games/example.sgf')
    await waitFor(() => expect(getByText(/example\.sgf/)).toBeTruthy())

    isDirty.value = true
    const saveButton = getByText('Сохранить') as HTMLButtonElement
    expect(saveButton.disabled).toBe(false)

    fireEvent.click(saveButton)
    await waitFor(() =>
      expect((window as any).baduk.saveFile).toHaveBeenCalledWith(
        '/games/example.sgf',
        expect.stringContaining('GM[1]')
      )
    )
    await waitFor(() => expect(isDirty.value).toBe(false))
  })

  it('falls back to Save As when there is no known file path yet', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      saveFile: vi.fn(),
      saveFileAs: vi.fn().mockResolvedValue({ path: '/games/chosen.sgf' }),
      reportDirtyState: vi.fn(),
      onSaveBeforeClose: vi.fn().mockReturnValue(() => {})
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    loadGame('(;GM[1]FF[4]SZ[9];B[ee])')
    isDirty.value = true

    fireEvent.click(getByText('Сохранить'))
    await waitFor(() =>
      expect((window as any).baduk.saveFileAs).toHaveBeenCalledWith(undefined, expect.any(String))
    )
    await waitFor(() => expect(currentFilePath.value).toBe('/games/chosen.sgf'))
    expect((window as any).baduk.saveFile).not.toHaveBeenCalled()
  })

  it('shows an error banner and keeps isDirty true when saving fails', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      saveFile: vi.fn().mockRejectedValue(new Error('disk full')),
      saveFileAs: vi.fn(),
      reportDirtyState: vi.fn(),
      onSaveBeforeClose: vi.fn().mockReturnValue(() => {})
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    loadGame('(;GM[1]FF[4]SZ[9];B[ee])', '/games/example.sgf')
    isDirty.value = true

    fireEvent.click(getByText('Сохранить'))
    await waitFor(() => expect(getByText(/disk full/)).toBeTruthy())
    expect(isDirty.value).toBe(true)
  })

  it('calling saveCurrentGame directly writes to the known path (not just via the button click)', async () => {
    const saveFile = vi.fn().mockResolvedValue(undefined)
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      saveFile,
      saveFileAs: vi.fn(),
      reportDirtyState: vi.fn(),
      onSaveBeforeClose: vi.fn().mockReturnValue(() => {})
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    loadGame('(;GM[1]FF[4]SZ[9];B[ee])', '/games/example.sgf')
    isDirty.value = true

    await saveCurrentGame()

    expect(saveFile).toHaveBeenCalledWith('/games/example.sgf', expect.stringContaining('GM[1]'))
    expect(isDirty.value).toBe(false)
  })

  it('"Сохранить как" always opens the save dialog, even when a file path is already known (unlike "Сохранить")', async () => {
    const saveFile = vi.fn()
    const saveFileAs = vi.fn().mockResolvedValue({ path: '/games/new-name.sgf' })
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      saveFile,
      saveFileAs,
      reportDirtyState: vi.fn(),
      onSaveBeforeClose: vi.fn().mockReturnValue(() => {})
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    loadGame('(;GM[1]FF[4]SZ[9];B[ee])', '/games/example.sgf')
    await waitFor(() => expect(getByText(/example\.sgf/)).toBeTruthy())

    fireEvent.click(getByText('Сохранить как'))

    await waitFor(() =>
      expect(saveFileAs).toHaveBeenCalledWith(
        '/games/example.sgf',
        expect.stringContaining('GM[1]')
      )
    )
    expect(saveFile).not.toHaveBeenCalled()
    await waitFor(() => expect(currentFilePath.value).toBe('/games/new-name.sgf'))
  })

  it('refuses to save and shows a warning banner when the loaded game declares a non-UTF-8 charset', async () => {
    const saveFile = vi.fn().mockResolvedValue(undefined)
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      saveFile,
      saveFileAs: vi.fn(),
      reportDirtyState: vi.fn(),
      onSaveBeforeClose: vi.fn().mockReturnValue(() => {})
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    loadGame('(;GM[1]FF[4]SZ[9]CA[Shift_JIS];B[ee])', '/games/example.sgf')
    isDirty.value = true

    fireEvent.click(getByText('Сохранить'))

    await waitFor(() => expect(getByText(/Shift_JIS/)).toBeTruthy())
    expect(saveFile).not.toHaveBeenCalled()
    expect(isDirty.value).toBe(true)
  })
})

describe('unsaved-changes close handshake', () => {
  it('reports dirty state to main whenever isDirty changes', async () => {
    const reportDirtyState = vi.fn()
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      reportDirtyState,
      onSaveBeforeClose: vi.fn().mockReturnValue(() => {})
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    isDirty.value = true
    await waitFor(() => expect(reportDirtyState).toHaveBeenLastCalledWith(true))

    isDirty.value = false
    await waitFor(() => expect(reportDirtyState).toHaveBeenLastCalledWith(false))
  })

  it('saves and reports success when main requests a save before close', async () => {
    let saveBeforeCloseHandler: (() => void) | undefined
    const sendSaveBeforeCloseResult = vi.fn()
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
      saveFile: vi.fn().mockResolvedValue(undefined),
      reportDirtyState: vi.fn(),
      onSaveBeforeClose: vi.fn().mockImplementation((handler: () => void) => {
        saveBeforeCloseHandler = handler
        return () => {}
      }),
      sendSaveBeforeCloseResult
    }

    const { getByText } = render(<App />)
    await waitFor(() => expect(getByText(/Без файла/)).toBeTruthy())

    loadGame('(;GM[1]FF[4]SZ[9];B[ee])', '/games/example.sgf')
    isDirty.value = true

    expect(saveBeforeCloseHandler).toBeTruthy()
    await saveBeforeCloseHandler!()

    expect((window as any).baduk.saveFile).toHaveBeenCalled()
    await waitFor(() => expect(sendSaveBeforeCloseResult).toHaveBeenCalledWith(true))
  })
})
