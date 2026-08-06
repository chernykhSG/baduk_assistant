import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

// Custom APIs for renderer
const api = {}

const baduk = {
  getBackendConnection: () => ipcRenderer.invoke('backend:get-connection'),
  saveFile: (path: string, content: string) => ipcRenderer.invoke('file:save', path, content),
  saveFileAs: (defaultPath: string | undefined, content: string) =>
    ipcRenderer.invoke('file:save-as', defaultPath, content),
  reportDirtyState: (isDirty: boolean) => ipcRenderer.send('file:dirty-changed', isDirty),
  onSaveBeforeClose: (handler: () => void) => {
    const listener = (): void => handler()
    ipcRenderer.on('file:save-before-close', listener)
    return () => ipcRenderer.removeListener('file:save-before-close', listener)
  },
  sendSaveBeforeCloseResult: (success: boolean) =>
    ipcRenderer.send('file:save-before-close-result', success)
}

// Use `contextBridge` APIs to expose Electron APIs to
// renderer only if context isolation is enabled, otherwise
// just add to the DOM global.
if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('api', api)
    contextBridge.exposeInMainWorld('baduk', baduk)
  } catch (error) {
    console.error(error)
  }
} else {
  // @ts-ignore (define in dts)
  window.electron = electronAPI
  // @ts-ignore (define in dts)
  window.api = api
  // @ts-ignore (define in dts)
  window.baduk = baduk
}
