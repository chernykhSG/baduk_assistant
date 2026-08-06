export interface BackendConnection {
  port: number
  token: string
}

export type SaveFileAsResult = { path: string } | { canceled: true }

declare global {
  interface Window {
    baduk: {
      getBackendConnection(): Promise<BackendConnection>
      saveFile(path: string, content: string): Promise<void>
      saveFileAs(defaultPath: string | undefined, content: string): Promise<SaveFileAsResult>
      reportDirtyState(isDirty: boolean): void
      onSaveBeforeClose(handler: () => void): () => void
      sendSaveBeforeCloseResult(success: boolean): void
    }
  }
}
