/// <reference types="vitest" />
/// <vitest environment="node" />
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mockWriteFile } = vi.hoisted(() => {
  return {
    mockWriteFile: vi.fn()
  }
})

const { mockShowSaveDialog } = vi.hoisted(() => {
  return {
    mockShowSaveDialog: vi.fn()
  }
})

vi.mock('node:fs/promises', () => {
  return {
    default: {
      writeFile: mockWriteFile,
      readFile: vi.fn(),
      appendFile: vi.fn(),
      unlink: vi.fn(),
      mkdir: vi.fn(),
      rmdir: vi.fn(),
      rename: vi.fn(),
      stat: vi.fn(),
      access: vi.fn()
    },
    writeFile: mockWriteFile,
    readFile: vi.fn(),
    appendFile: vi.fn(),
    unlink: vi.fn(),
    mkdir: vi.fn(),
    rmdir: vi.fn(),
    rename: vi.fn(),
    stat: vi.fn(),
    access: vi.fn()
  }
})

vi.mock('electron', () => ({
  dialog: { showSaveDialog: mockShowSaveDialog, showMessageBoxSync: vi.fn() }
}))

import { dialog } from 'electron'
import { saveFile, saveFileAs, promptUnsavedChangesChoice } from '../../src/main/fileIO'

beforeEach(() => {
  mockWriteFile.mockReset().mockResolvedValue(undefined)
  mockShowSaveDialog.mockReset()
})

describe('saveFile', () => {
  it('writes the given content to the given path as utf-8', async () => {
    await saveFile('/games/example.sgf', '(;GM[1])')

    expect(mockWriteFile).toHaveBeenCalledWith('/games/example.sgf', '(;GM[1])', 'utf-8')
  })

  it('propagates a write failure', async () => {
    mockWriteFile.mockRejectedValue(new Error('EACCES: permission denied'))

    await expect(saveFile('/readonly/example.sgf', '(;GM[1])')).rejects.toThrow(
      'permission denied'
    )
  })
})

describe('saveFileAs', () => {
  it('opens a save dialog filtered to .sgf and writes the chosen path', async () => {
    mockShowSaveDialog.mockResolvedValue({
      canceled: false,
      filePath: '/games/new-name.sgf'
    })

    const result = await saveFileAs('/games/example.sgf', '(;GM[1])')

    expect(mockShowSaveDialog).toHaveBeenCalledWith(
      expect.objectContaining({
        defaultPath: '/games/example.sgf',
        filters: [{ name: 'SGF', extensions: ['sgf'] }]
      })
    )
    expect(mockWriteFile).toHaveBeenCalledWith('/games/new-name.sgf', '(;GM[1])', 'utf-8')
    expect(result).toEqual({ path: '/games/new-name.sgf' })
  })

  it('returns canceled without writing when the dialog is dismissed', async () => {
    mockShowSaveDialog.mockResolvedValue({
      canceled: true,
      filePath: undefined
    })

    const result = await saveFileAs(undefined, '(;GM[1])')

    expect(result).toEqual({ canceled: true })
    expect(mockWriteFile).not.toHaveBeenCalled()
  })
})

describe('promptUnsavedChangesChoice', () => {
  it('maps dialog button index 0 to save-and-close', () => {
    vi.mocked(dialog.showMessageBoxSync).mockReturnValue(0)
    expect(promptUnsavedChangesChoice({} as Electron.BrowserWindow)).toBe('save-and-close')
  })

  it('maps dialog button index 1 to close-without-saving', () => {
    vi.mocked(dialog.showMessageBoxSync).mockReturnValue(1)
    expect(promptUnsavedChangesChoice({} as Electron.BrowserWindow)).toBe('close-without-saving')
  })

  it('maps dialog button index 2 (and the dismiss/Escape case) to cancel', () => {
    vi.mocked(dialog.showMessageBoxSync).mockReturnValue(2)
    expect(promptUnsavedChangesChoice({} as Electron.BrowserWindow)).toBe('cancel')
  })
})
