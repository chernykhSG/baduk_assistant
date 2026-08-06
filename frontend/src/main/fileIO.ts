import { rename, writeFile } from 'node:fs/promises'
import { dialog, type BrowserWindow } from 'electron'

export async function saveFile(path: string, content: string): Promise<void> {
  // Write to a temp path in the same directory first, then rename it over
  // the target — rename is atomic on the same filesystem/volume (both
  // Windows and POSIX), so a crash or disk-full failure mid-write leaves
  // the original file intact instead of truncated/corrupted.
  const tempPath = `${path}.tmp`
  await writeFile(tempPath, content, 'utf-8')
  await rename(tempPath, path)
}

export async function saveFileAs(
  defaultPath: string | undefined,
  content: string
): Promise<{ path: string } | { canceled: true }> {
  const result = await dialog.showSaveDialog({
    defaultPath,
    filters: [{ name: 'SGF', extensions: ['sgf'] }]
  })
  if (result.canceled || !result.filePath) return { canceled: true }
  await writeFile(result.filePath, content, 'utf-8')
  return { path: result.filePath }
}

export type UnsavedChangesChoice = 'save-and-close' | 'close-without-saving' | 'cancel'

export function promptUnsavedChangesChoice(window: BrowserWindow): UnsavedChangesChoice {
  const choice = dialog.showMessageBoxSync(window, {
    type: 'warning',
    buttons: ['Сохранить и закрыть', 'Закрыть без сохранения', 'Отмена'],
    defaultId: 0,
    cancelId: 2,
    message: 'В открытой партии есть несохранённые изменения.',
    detail: 'Сохранить изменения перед закрытием?'
  })
  if (choice === 0) return 'save-and-close'
  if (choice === 1) return 'close-without-saving'
  return 'cancel'
}
