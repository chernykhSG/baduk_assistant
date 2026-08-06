import { writeFile } from 'node:fs/promises'
import { dialog } from 'electron'

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
