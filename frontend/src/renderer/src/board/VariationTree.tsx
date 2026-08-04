import { currentTree, currentNodeId } from '../state/appState'

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
  if (!tree) return <div class="variation-tree" />

  return (
    <div class="variation-tree" tabIndex={0} onKeyDown={handleKeyDown}>
      {renderNode(tree.root)}
    </div>
  )

  function renderNode(node: any) {
    const isCurrent = node.id === currentNodeId.value
    return (
      <div class="variation-tree__node" key={node.id}>
        <button
          type="button"
          class={isCurrent ? 'variation-tree__marker variation-tree__marker--current' : 'variation-tree__marker'}
          onClick={() => (currentNodeId.value = node.id)}
        >
          {node.data.B ? `B ${node.data.B[0]}` : node.data.W ? `W ${node.data.W[0]}` : '·'}
        </button>
        {node.children.length > 0 && (
          <div class="variation-tree__children">{node.children.map((child: any) => renderNode(child))}</div>
        )}
      </div>
    )
  }
}
