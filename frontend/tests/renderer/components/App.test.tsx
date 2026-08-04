import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/preact'
import { App } from '@renderer/App'

beforeEach(() => {
  ;(globalThis as any).window = (globalThis as any).window ?? {}
})

describe('App / ConnectionGate', () => {
  it('shows a connection-error screen if the backend connection promise rejects', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockRejectedValue(new Error('backend did not start')),
    }

    const { getByText } = render(<App />)

    await waitFor(() => {
      expect(getByText(/не удалось запустить backend/i)).toBeTruthy()
    })
  })

  it('renders the app shell once the backend connection resolves', async () => {
    ;(window as any).baduk = {
      getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' }),
    }

    const { container } = render(<App />)

    await waitFor(() => {
      expect(container.querySelector('.app-shell')).toBeTruthy()
    })
  })
})
