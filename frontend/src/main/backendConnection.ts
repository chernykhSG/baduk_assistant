import { spawn, type ChildProcess } from 'node:child_process'
import * as readline from 'node:readline'

export interface BackendConnection {
  port: number
  token: string
}

let currentBackendProcess: ChildProcess | null = null

export function startBackend(
  command: string = process.env.BADUK_BACKEND_COMMAND ?? 'baduk-backend'
): Promise<BackendConnection> {
  return new Promise((resolve, reject) => {
    const child: ChildProcess = spawn(command, [], { shell: true })
    currentBackendProcess = child
    let settled = false

    if (!child.stdout) {
      reject(new Error('Backend process has no stdout stream'))
      return
    }

    const rl = readline.createInterface({ input: child.stdout })

    rl.on('line', (line) => {
      if (settled) return
      try {
        const parsed = JSON.parse(line)
        if (typeof parsed.port === 'number' && typeof parsed.token === 'string') {
          settled = true
          rl.close()
          resolve({ port: parsed.port, token: parsed.token })
        }
      } catch {
        // строка до старт-сообщения (backend может логировать что-то ещё раньше) — игнорируем
      }
    })

    child.on('exit', (code) => {
      if (!settled) {
        settled = true
        rl.close()
        reject(new Error(`Backend process exited with code ${code} before reporting a connection`))
      }
    })

    child.on('error', (err) => {
      if (!settled) {
        settled = true
        rl.close()
        reject(err)
      }
    })
  })
}

export function stopBackend(): void {
  const child = currentBackendProcess
  currentBackendProcess = null
  if (!child || !child.pid) return

  if (process.platform === 'win32') {
    // On Windows, spawn(..., { shell: true }) launches the command via
    // cmd.exe, so `child.pid` is the shell's PID, not the actual backend
    // process's PID. child.kill() would only terminate that shell wrapper
    // and leave the real backend process (a grandchild) running orphaned.
    // /t kills the whole process tree rooted at that PID.
    spawn('taskkill', ['/pid', String(child.pid), '/t', '/f'])
  } else {
    child.kill()
  }
}
