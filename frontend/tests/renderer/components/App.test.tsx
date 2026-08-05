import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/preact'
import { App, loadGame, sgfError } from '@renderer/App'
import { currentTree, currentNodeId, streamStatus, streamError } from '@renderer/state/appState'

beforeEach(() => {
  ;(globalThis as any).window = (globalThis as any).window ?? {}
})

afterEach(() => {
  currentTree.value = null
  currentNodeId.value = null
  streamStatus.value = 'idle'
  streamError.value = null
  sgfError.value = null
})

describe('App / ConnectionGate', () => {
  it('shows a connection-error screen if the backend connection promise rejects', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockRejectedValue(new Error('backend did not start'))
    }

    const { getByText } = render(<App />)

    await waitFor(() => {
      expect(getByText(/не удалось запустить backend/i)).toBeTruthy()
    })
  })

  it('renders the app shell once the backend connection resolves', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' })
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
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' })
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
