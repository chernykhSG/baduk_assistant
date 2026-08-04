import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { startBackend } from '../../src/main/backendConnection'

const fixturesDir = path.join(path.dirname(fileURLToPath(import.meta.url)), '../fixtures/backend')

describe('startBackend', () => {
  it('resolves with port and token parsed from the first JSON stdout line', async () => {
    const command = `node "${path.join(fixturesDir, 'fake-backend.mjs')}"`
    const connection = await startBackend(command)
    expect(connection).toEqual({ port: 54321, token: 'fake-token' })
  })

  it('rejects if the process exits before printing a connection line', async () => {
    const command = `node "${path.join(fixturesDir, 'fake-backend-crash.mjs')}"`
    await expect(startBackend(command)).rejects.toThrow(/exited with code 1/)
  })
})
