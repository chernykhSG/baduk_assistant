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

  it('does not mark dirty or commit the tree when blur happens with no edits', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]C[Исходный комментарий])')
    const leaf = findMainLineLeaf(tree)
    currentTree.value = tree
    currentNodeId.value = leaf.id
    isDirty.value = false

    const { getByRole } = render(<AnnotationPanel />)
    const textarea = getByRole('textbox') as HTMLTextAreaElement

    // Focus and blur without any input event
    fireEvent.focus(textarea)
    fireEvent.blur(textarea)

    // Tree should be unchanged and isDirty should stay false
    const node = currentTree.value!.get(leaf.id) as { data: Record<string, string[]> }
    expect(node.data.C).toEqual(['Исходный комментарий'])
    expect(isDirty.value).toBe(false)
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

  it('shows the new comment after loading a second game whose root node coincidentally shares the same numeric id', async () => {
    const tree1 = parseSgf('(;GM[1]FF[4]SZ[9]C[Комментарий первой партии];B[ee])')
    currentTree.value = tree1
    currentNodeId.value = tree1.root.id

    const { getByRole } = render(<AnnotationPanel />)
    const textarea = getByRole('textbox') as HTMLTextAreaElement
    await waitFor(() => expect(textarea.value).toBe('Комментарий первой партии'))

    // sgfLoader resets its module-level id counter on every parse, so this
    // second, completely different game's root node also gets id 0 — the
    // same numeric id as tree1's root — even though it's a different
    // GameTree instance.
    const tree2 = parseSgf('(;GM[1]FF[4]SZ[9]C[Комментарий второй партии];W[dd])')
    expect(tree2.root.id).toBe(tree1.root.id)
    currentTree.value = tree2
    currentNodeId.value = tree2.root.id

    await waitFor(() => expect(textarea.value).toBe('Комментарий второй партии'))
  })

  it('commits an uncommitted edit to the ORIGINAL node when the node changes without a blur event (e.g. wheel navigation)', async () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee]C[Первый];W[ec]C[Второй])')
    const root = tree.root as { children: { id: number }[] }
    const bMoveNode = root.children[0]
    const wMoveNode = (bMoveNode as unknown as { children: { id: number }[] }).children[0]
    currentTree.value = tree
    currentNodeId.value = bMoveNode.id

    const { getByRole } = render(<AnnotationPanel />)
    const textarea = getByRole('textbox') as HTMLTextAreaElement
    await waitFor(() => expect(textarea.value).toBe('Первый'))

    // Type without blurring — the gap between an edit and the commit-on-blur
    // handler firing.
    fireEvent.input(textarea, { target: { value: 'Отредактированный' } })

    // Simulate VariationTree's wheel handler: it sets currentNodeId directly
    // without firing any blur/focus event on the textarea first.
    currentNodeId.value = wMoveNode.id

    await waitFor(() => expect(textarea.value).toBe('Второй'))

    const editedNode = currentTree.value!.get(bMoveNode.id) as { data: Record<string, string[]> }
    expect(editedNode.data.C).toEqual(['Отредактированный'])
    expect(isDirty.value).toBe(true)
  })
})
