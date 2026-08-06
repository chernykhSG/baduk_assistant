import { writeFile } from 'node:fs/promises'
import { dialog, type BrowserWindow } from 'electron'

export async function saveFile(path: string, content: string): Promise<void> {
  await writeFile(path, content, 'utf-8')
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
