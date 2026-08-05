import { describe, it, expect, vi, beforeEach } from 'vitest'
import { analyzePosition, streamAnalysis, explainPosition } from '@renderer/ipc/client'

function fakeAnalyzeRequest() {
  return {
    moves: [] as [string, string][],
    rules: 'chinese',
    komi: 7.5,
    boardXSize: 19,
    boardYSize: 19,
    analyzeTurns: [0] as [number],
    maxVisits: 50,
    includeOwnership: true
  }
}

beforeEach(() => {
  ;(globalThis as any).window = (globalThis as any).window ?? {}
  ;(window as any).baduk = {
    getBackendConnection: vi.fn().mockResolvedValue({ port: 5555, token: 'test-token' })
  }
})

describe('analyzePosition', () => {
  it('POSTs to /api/analyze with the auth header and returns the parsed response', async () => {
    const fakeResponse = {
      id: 'x',
      moveInfos: [],
      rootInfo: { winrate: 0.5, scoreLead: 0, visits: 1 }
    }
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => fakeResponse }) as any

    const result = await analyzePosition(fakeAnalyzeRequest())

    expect(globalThis.fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:5555/api/analyze',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-Auth-Token': 'test-token' })
      })
    )
    expect(result).toEqual(fakeResponse)
  })

  it('throws with the response detail when the request fails', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
      json: async () => ({ detail: 'engine crashed' })
    }) as any

    await expect(analyzePosition(fakeAnalyzeRequest())).rejects.toThrow('engine crashed')
  })
})

class FakeWebSocket {
  onopen: (() => void) | null = null
  listeners: Record<string, ((event: any) => void)[]> = {}
  sent: string[] = []
  closed = false
  constructor(public url: string) {
    queueMicrotask(() => this.dispatch('open', {}))
  }
  addEventListener(type: string, cb: (event: any) => void) {
    ;(this.listeners[type] ??= []).push(cb)
  }
  send(data: string) {
    this.sent.push(data)
  }
  close() {
    this.closed = true
  }
  dispatch(type: string, event: any) {
    for (const cb of this.listeners[type] ?? []) cb(event)
  }
}

describe('streamAnalysis', () => {
  it('sends the request on open and routes progress/done messages to handlers', async () => {
    let createdSocket: FakeWebSocket | undefined
    ;(globalThis as any).WebSocket = vi.fn().mockImplementation(function (url: string) {
      createdSocket = new FakeWebSocket(url)
      return createdSocket
    })

    const onProgress = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    streamAnalysis(
      {
        moves: [],
        rules: 'chinese',
        komi: 7.5,
        boardXSize: 19,
        boardYSize: 19,
        turnNumbers: [0],
        maxVisits: 50,
        includeOwnership: true
      },
      { onProgress, onDone, onError }
    )

    await vi.waitUntil(() => createdSocket !== undefined)
    await vi.waitUntil(() => createdSocket!.sent.length > 0)

    expect(createdSocket!.url).toBe('ws://127.0.0.1:5555/api/analyze/stream?token=test-token')

    createdSocket!.dispatch('message', {
      data: JSON.stringify({
        type: 'progress',
        turnNumber: 0,
        total: 1,
        result: { id: 'x', moveInfos: [], rootInfo: { winrate: 0.5, scoreLead: 0, visits: 1 } }
      })
    })
    createdSocket!.dispatch('message', { data: JSON.stringify({ type: 'done' }) })

    expect(onProgress).toHaveBeenCalledOnce()
    expect(onDone).toHaveBeenCalledOnce()
    expect(onError).not.toHaveBeenCalled()
  })

  it('closes the socket when the returned unsubscribe function is called', async () => {
    let createdSocket: FakeWebSocket | undefined
    ;(globalThis as any).WebSocket = vi.fn().mockImplementation(function (url: string) {
      createdSocket = new FakeWebSocket(url)
      return createdSocket
    })

    const close = streamAnalysis(
      {
        moves: [],
        rules: 'chinese',
        komi: 7.5,
        boardXSize: 19,
        boardYSize: 19,
        turnNumbers: [0],
        maxVisits: 50,
        includeOwnership: true
      },
      { onProgress: vi.fn(), onDone: vi.fn(), onError: vi.fn() }
    )

    await vi.waitUntil(() => createdSocket !== undefined)
    close()
    expect(createdSocket!.closed).toBe(true)
  })
})

function fakeAnalysisResult() {
  return {
    id: 'x',
    moveInfos: [],
    rootInfo: { winrate: 0.5, scoreLead: 0, visits: 1 }
  }
}

describe('explainPosition', () => {
  it('POSTs to /api/explain with the auth header and returns the parsed response', async () => {
    const fakeResponse = {
      finding: null,
      explanation: null,
      verified: null,
      message: 'Ничего заметного не найдено в этой позиции'
    }
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => fakeResponse }) as any

    const result = await explainPosition({
      moves: [],
      boardXSize: 9,
      boardYSize: 9,
      analysis: fakeAnalysisResult()
    })

    expect(globalThis.fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:5555/api/explain',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-Auth-Token': 'test-token' })
      })
    )
    expect(result).toEqual(fakeResponse)
  })

  it('throws with the response detail when the request fails', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: async () => ({ detail: 'claude api error' })
    }) as any

    await expect(
      explainPosition({ moves: [], boardXSize: 9, boardYSize: 9, analysis: fakeAnalysisResult() })
    ).rejects.toThrow('claude api error')
  })
})
