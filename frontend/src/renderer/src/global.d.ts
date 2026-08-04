export interface BackendConnection {
  port: number
  token: string
}

declare global {
  interface Window {
    baduk: {
      getBackendConnection(): Promise<BackendConnection>
    }
  }
}
