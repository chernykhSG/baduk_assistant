import { useEffect, useState } from 'preact/hooks'
import type { JSX } from 'preact'
import { currentTree, currentNodeId, isDirty } from '../state/appState'
import { setComment } from '../board/annotations'

export function AnnotationPanel(): JSX.Element {
  const [text, setText] = useState('')
  const nodeId = currentNodeId.value

  useEffect(() => {
    const tree = currentTree.value
    if (!tree || nodeId === null) {
      setText('')
      return
    }
    const node = tree.get(nodeId) as { data: Record<string, string[]> } | null
    setText(node?.data.C?.[0] ?? '')
  }, [nodeId])

  function handleBlur(event: Event): void {
    const tree = currentTree.value
    if (!tree || nodeId === null) return
    currentTree.value = setComment(tree, nodeId, (event.target as HTMLTextAreaElement).value)
    isDirty.value = true
  }

  return (
    <div class="annotation-panel">
      <textarea
        class="annotation-panel__comment"
        placeholder="Комментарий к этому ходу"
        value={text}
        disabled={!currentTree.value || nodeId === null}
        onInput={(event) => setText((event.target as HTMLTextAreaElement).value)}
        onBlur={handleBlur}
      />
    </div>
  )
}
