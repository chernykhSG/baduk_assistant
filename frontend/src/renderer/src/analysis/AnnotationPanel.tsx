import { useEffect, useState, useRef } from 'preact/hooks'
import type { JSX } from 'preact'
import { currentTree, currentNodeId, isDirty, currentNode } from '../state/appState'
import { setComment } from '../board/annotations'

export function AnnotationPanel(): JSX.Element {
  const [text, setText] = useState('')
  const loadedValueRef = useRef('')
  const nodeId = currentNodeId.value

  useEffect(() => {
    const node = currentNode.value
    if (!node) {
      setText('')
      loadedValueRef.current = ''
      return
    }
    const commentText = node.data.C?.[0] ?? ''
    setText(commentText)
    loadedValueRef.current = commentText
  }, [nodeId])

  function handleBlur(event: Event): void {
    const tree = currentTree.value
    if (!tree || nodeId === null) return

    const newValue = (event.target as HTMLTextAreaElement).value

    // Only commit if value actually changed
    if (newValue !== loadedValueRef.current) {
      currentTree.value = setComment(tree, nodeId, newValue)
      isDirty.value = true
      loadedValueRef.current = newValue
    }
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
