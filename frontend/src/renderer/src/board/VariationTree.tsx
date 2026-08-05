import { useEffect, useRef } from 'preact/hooks'
import type { ComponentChild } from 'preact'
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
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    currentRef.current?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [nodeId])

  // Focus the tree as soon as a game loads (a new tree object), so
  // arrow-key navigation works immediately instead of requiring a click first.
  useEffect(() => {
    containerRef.current?.focus()
  }, [tree])

  if (!tree) return <div class="variation-tree" ref={containerRef} />

  return (
    <div class="variation-tree" ref={containerRef} tabIndex={0} onKeyDown={handleKeyDown}>
      {renderChain(tree.root)}
    </div>
  )

  function renderMarker(node: NodeObject) {
    const isCurrent = node.id === nodeId
    const colorClass = node.data.B
      ? 'variation-tree__marker--black'
      : node.data.W
        ? 'variation-tree__marker--white'
        : 'variation-tree__marker--root'
    const label = node.data.B ? `B ${node.data.B[0]}` : node.data.W ? `W ${node.data.W[0]}` : 'root'
    return (
      <button
        key={node.id}
        ref={isCurrent ? currentRef : undefined}
        type="button"
        class={`variation-tree__marker ${colorClass}${isCurrent ? ' variation-tree__marker--current' : ''}`}
        onClick={() => (currentNodeId.value = node.id)}
        title={label}
        aria-label={label}
      />
    )
  }

  // Walks a straight run of single-child moves as one flat, unindented
  // column (so a game with no variations reads as a plain vertical list,
  // not a staircase). Indentation only appears at an actual branch point,
  // where every child — including what would've been the "main" line —
  // becomes its own indented sub-chain.
  function renderChain(startNode: NodeObject) {
    const items: ComponentChild[] = []
    let node: NodeObject | null = startNode
    while (node) {
      items.push(renderMarker(node))
      if (node.children.length === 1) {
        node = node.children[0]
      } else if (node.children.length > 1) {
        const branches = node.children
        items.push(
          <div class="variation-tree__children" key={`branches-${node.id}`}>
            {branches.map((child) => (
              <div class="variation-tree__branch" key={child.id}>
                {renderChain(child)}
              </div>
            ))}
          </div>
        )
        node = null
      } else {
        node = null
      }
    }
    return items
  }
}
