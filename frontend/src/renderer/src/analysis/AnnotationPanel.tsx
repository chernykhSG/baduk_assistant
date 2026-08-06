import { useState, useRef } from 'preact/hooks'
import { useSignalEffect } from '@preact/signals'
import type { JSX } from 'preact'
import type GameTree from '@sabaki/immutable-gametree'
import { currentTree, currentNodeId, isDirty, currentNode } from '../state/appState'
import { setComment } from '../board/annotations'

export function AnnotationPanel(): JSX.Element {
  const [text, setText] = useState('')
  // Mirrors `text`, but readable from inside useSignalEffect's callback
  // (which — unlike component state — isn't re-created per Preact render,
  // so closing over `text` directly would see a stale value).
  const textRef = useRef('')
  const loadedValueRef = useRef('')
  // Tracks which tree+nodeId the currently-displayed text belongs to, so we
  // can tell a same-node edit (tree changes, nodeId doesn't) apart from
  // in-tree navigation (nodeId changes, tree doesn't) apart from a whole new
  // file loading (tree object changes, regardless of nodeId).
  const outgoingRef = useRef<{ tree: GameTree; nodeId: number } | null>(null)
  const nodeId = currentNodeId.value

  useSignalEffect(() => {
    const tree = currentTree.value
    const id = currentNodeId.value
    const node = currentNode.value

    const outgoing = outgoingRef.current
    // In-tree navigation to a different node (same tree object, different
    // id) can happen without the textarea's blur handler ever firing — e.g.
    // VariationTree's mouse-wheel handler changes currentNodeId without
    // moving keyboard focus. If there's an uncommitted edit sitting in the
    // textarea for the node we're leaving, commit it there now, before
    // switching the display to the new node. (A same-node edit — tree
    // changes, id doesn't, e.g. the blur handler's own commit — and a whole
    // new file loading — tree object changes outright — are deliberately
    // excluded: both are handled by their own paths below.)
    if (outgoing && outgoing.tree === tree && outgoing.nodeId !== id) {
      if (textRef.current !== loadedValueRef.current) {
        outgoingRef.current = null
        currentTree.value = setComment(outgoing.tree, outgoing.nodeId, textRef.current)
        isDirty.value = true
        return // the write above re-triggers this effect with fresh state
      }
    }

    if (!node || !tree || id === null) {
      setText('')
      textRef.current = ''
      loadedValueRef.current = ''
      outgoingRef.current = null
      return
    }

    // Reacting to node/tree *identity* (via the signals read above) rather
    // than only the numeric id matters because sgfLoader resets its
    // module-level id counter on every parse — a freshly-loaded file's root
    // node can carry the exact same id as the previously-loaded file's root,
    // even though it's an entirely different GameTree.
    const commentText = node.data.C?.[0] ?? ''
    setText(commentText)
    textRef.current = commentText
    loadedValueRef.current = commentText
    outgoingRef.current = { tree, nodeId: id }
  })

  function handleBlur(event: Event): void {
    const tree = currentTree.value
    if (!tree || nodeId === null) return

    const newValue = (event.target as HTMLTextAreaElement).value

    // Only commit if value actually changed
    if (newValue !== loadedValueRef.current) {
      currentTree.value = setComment(tree, nodeId, newValue)
      isDirty.value = true
      loadedValueRef.current = newValue
      textRef.current = newValue
      outgoingRef.current = { tree: currentTree.value, nodeId }
    }
  }

  return (
    <div class="annotation-panel">
      <textarea
        class="annotation-panel__comment"
        placeholder="Комментарий к этому ходу"
        value={text}
        disabled={!currentTree.value || nodeId === null}
        onInput={(event) => {
          const value = (event.target as HTMLTextAreaElement).value
          setText(value)
          textRef.current = value
        }}
        onBlur={handleBlur}
      />
    </div>
  )
}
