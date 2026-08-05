import { useEffect, useRef } from 'preact/hooks'
import { currentTree, currentNodeId } from '../state/appState'
import type { NodeObject } from './sgfLoader'

function stepDown() {
  const tree = currentTree.value
  const nodeId = currentNodeId.value
  if (!tree || nodeId === null) return
  const node = tree.get(nodeId)
  if (node && node.children.length > 0) {
    currentNodeId.value = node.children[0].id
  }
}

function stepUp() {
  const tree = currentTree.value
  const nodeId = currentNodeId.value
  if (!tree || nodeId === null) return
  const node = tree.get(nodeId)
  if (node && node.parentId !== null && node.parentId !== undefined) {
    currentNodeId.value = node.parentId
  }
}

function handleKeyDown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    stepDown()
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    stepUp()
  }
}

export function VariationTree() {
  const tree = currentTree.value
  const nodeId = currentNodeId.value
  const currentRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    currentRef.current?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [nodeId])

  if (!tree) return <div class="variation-tree" />

  return (
    <div class="variation-tree" tabIndex={0} onKeyDown={handleKeyDown}>
      {renderNode(tree.root)}
    </div>
  )

  function renderNode(node: NodeObject) {
    const isCurrent = node.id === nodeId
    const colorClass = node.data.B
      ? 'variation-tree__marker--black'
      : node.data.W
        ? 'variation-tree__marker--white'
        : 'variation-tree__marker--root'
    const label = node.data.B ? `B ${node.data.B[0]}` : node.data.W ? `W ${node.data.W[0]}` : 'root'
    return (
      <div class="variation-tree__node" key={node.id}>
        <button
          ref={isCurrent ? currentRef : undefined}
          type="button"
          class={`variation-tree__marker ${colorClass}${isCurrent ? ' variation-tree__marker--current' : ''}`}
          onClick={() => (currentNodeId.value = node.id)}
          title={label}
          aria-label={label}
        />
        {node.children.length > 0 && (
          <div class="variation-tree__children">{node.children.map((child: NodeObject) => renderNode(child))}</div>
        )}
      </div>
    )
  }
}
