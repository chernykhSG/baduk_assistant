import { describe, it, expect, afterEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/preact'
import { AnnotationPanel } from '@renderer/analysis/AnnotationPanel'
import { currentTree, currentNodeId, isDirty } from '@renderer/state/appState'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'

afterEach(() => {
  currentTree.value = null
  currentNodeId.value = null
  isDirty.value = false
})

describe('AnnotationPanel', () => {
  it('is disabled with no game loaded', () => {
    const { getByRole } = render(<AnnotationPanel />)
    expect((getByRole('textbox') as HTMLTextAreaElement).disabled).toBe(true)
  })

  it('shows the current node comment and lets the user edit it', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]C[Исходный комментарий])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    const { getByRole } = render(<AnnotationPanel />)
    const textarea = getByRole('textbox') as HTMLTextAreaElement
    expect(textarea.value).toBe('Исходный комментарий')
  })

  it('commits the edited comment to the tree on blur, not on every keystroke', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id

    const { getByRole } = render(<AnnotationPanel />)
    const textarea = getByRole('textbox') as HTMLTextAreaElement

    fireEvent.input(textarea, { target: { value: 'Новый комментарий' } })
    const node1 = currentTree.value!.get(leaf.id) as { data: Record<string, string[]> }
    expect(node1.data.C).toBeUndefined()

    fireEvent.blur(textarea)
    const node2 = currentTree.value!.get(leaf.id) as { data: Record<string, string[]> }
    expect(node2.data.C).toEqual(['Новый комментарий'])
    expect(isDirty.value).toBe(true)
  })

  it('reloads the textarea contents when the current node changes', async () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]C[Первый];W[ec]C[Второй])')
    const root = tree.root as { children: { id: number }[] }
    const bMoveNode = root.children[0]
    const wMoveNode = (bMoveNode as unknown as { children: { id: number }[] }).children[0]
    currentTree.value = tree
    currentNodeId.value = bMoveNode.id

    const { getByRole } = render(<AnnotationPanel />)
    const textarea = getByRole('textbox') as HTMLTextAreaElement
    expect(textarea.value).toBe('Первый')

    currentNodeId.value = wMoveNode.id
    await waitFor(() => expect(textarea.value).toBe('Второй'))
  })
})
