import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

// Custom APIs for renderer
const api = {}

const baduk = {
  getBackendConnection: () => ipcRenderer.invoke('backend:get-connection'),
  saveFile: (path: string, content: string) => ipcRenderer.invoke('file:save', path, content),
  saveFileAs: (defaultPath: string | undefined, content: string) =>
    ipcRenderer.invoke('file:save-as', defaultPath, content)
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
