export interface MoveInfo {
  move: string
  winrate: number
  scoreLead: number
  visits: number
  prior: number
  pv: string[]
}

export interface RootInfo {
  winrate: number
  scoreLead: number
  visits: number
}

export interface AnalyzeRequest {
  moves: [string, string][]
  rules: string
  komi: number
  boardXSize: number
  boardYSize: number
  analyzeTurns: [number]
  maxVisits: number
  includeOwnership: boolean
}

export interface AnalyzeResponse {
  id: string
  turnNumber?: number
  moveInfos: MoveInfo[]
  rootInfo: RootInfo
  ownership?: number[]
}

export interface StreamAnalyzeRequest {
  moves: [string, string][]
  rules: string
  komi: number
  boardXSize: number
  boardYSize: number
  turnNumbers: number[]
  maxVisits: number
  includeOwnership: boolean
}

export type ProgressMessage = { type: 'progress'; turnNumber: number; total: number; result: AnalyzeResponse }
export type DoneMessage = { type: 'done' }
export type ErrorMessage = { type: 'error'; detail: string }

let connectionPromise: Promise<{ port: number; token: string }> | null = null

function getConnection(): Promise<{ port: number; token: string }> {
  if (!connectionPromise) {
    // Clear the cache on rejection so a later call retries instead of
    // replaying the same failure forever (e.g. backend sidecar was still
    // starting up on the first attempt).
    connectionPromise = window.baduk.getBackendConnection().catch((err) => {
      connectionPromise = null
      throw err
    })
  }
  return connectionPromise
}

export async function analyzePosition(request: AnalyzeRequest): Promise<AnalyzeResponse> {
  const { port, token } = await getConnection()
  const response = await fetch(`http://127.0.0.1:${port}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Auth-Token': token },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(`analyzePosition failed (${response.status}): ${body.detail ?? response.statusText}`)
  }
  return response.json()
}

export function streamAnalysis(
  request: StreamAnalyzeRequest,
  handlers: {
    onProgress(msg: ProgressMessage): void
    onDone(): void
    onError(msg: ErrorMessage): void
  }
): () => void {
  let closed = false
  // Set once a 'done'/'error' message or the 'error' event already reported
  // the outcome, so the 'close' handler (which always fires afterwards,
  // even on a graceful end) doesn't report it a second time.
  let finished = false
  let ws: WebSocket | null = null

  getConnection().then(({ port, token }) => {
    if (closed) return
    ws = new WebSocket(`ws://127.0.0.1:${port}/api/analyze/stream?token=${encodeURIComponent(token)}`)
    ws.addEventListener('open', () => {
      ws!.send(JSON.stringify(request))
    })
    ws.addEventListener('message', (event: MessageEvent) => {
      const msg = JSON.parse(event.data as string)
      if (msg.type === 'progress') handlers.onProgress(msg)
      else if (msg.type === 'done') {
        finished = true
        handlers.onDone()
      } else if (msg.type === 'error') {
        finished = true
        handlers.onError(msg)
      }
    })
    ws.addEventListener('error', () => {
      finished = true
      handlers.onError({ type: 'error', detail: 'WebSocket connection error' })
    })
    ws.addEventListener('close', (event: CloseEvent) => {
      if (finished || closed) return
      finished = true
      handlers.onError({ type: 'error', detail: `WebSocket closed unexpectedly (code ${event.code})` })
    })
  })

  return () => {
    closed = true
    ws?.close()
  }
}
