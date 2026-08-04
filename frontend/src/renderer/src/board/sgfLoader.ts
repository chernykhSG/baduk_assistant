import * as sgf from '@sabaki/sgf'
import GameTree from '@sabaki/immutable-gametree'

export class SgfParseError extends Error {}

/**
 * Shape of a parsed SGF node, shared by @sabaki/sgf's raw parse tree and
 * @sabaki/immutable-gametree's GameTree nodes (neither package ships types).
 */
export interface NodeObject {
  id: number
  data: Record<string, string[]>
  parentId: number | null
  children: NodeObject[]
}

let idCounter = 0
function getId(): number {
  return idCounter++
}

// @sabaki/sgf's parser is lenient: unparseable/garbage content (e.g. unmatched
// parentheses, or free text with no SGF structure) doesn't throw. Instead it
// silently produces a tree containing "dummy" nodes with id === null wherever
// it gave up on a sub-parse, rather than a real id assigned by getId(). A
// well-formed tree never contains a node with id === null, so recursively
// scanning for one is how we detect this class of malformed input.
function containsNullId(node: NodeObject): boolean {
  if (node.id == null) return true
  return node.children.some(containsNullId)
}

export function parseSgf(content: string): GameTree {
  idCounter = 0
  let rootNodes: NodeObject[]
  try {
    rootNodes = sgf.parse(content, { getId })
  } catch (err) {
    throw new SgfParseError(`Failed to parse SGF: ${(err as Error).message}`)
  }
  if (!rootNodes || rootNodes.length === 0) {
    throw new SgfParseError('SGF content contains no game trees')
  }
  if (containsNullId(rootNodes[0])) {
    throw new SgfParseError('SGF content is malformed: parser could not build a valid node tree')
  }
  return new GameTree({ getId, root: rootNodes[0] })
}

export function getBoardSize(tree: GameTree): number {
  const szValue = (tree.root as NodeObject).data.SZ?.[0]
  if (!szValue) return 19
  if (szValue.includes(':')) {
    throw new Error(`Rectangular boards (SZ=${szValue}) are not supported in Phase 1`)
  }
  return parseInt(szValue, 10)
}

export function findMainLineLeaf(tree: GameTree): NodeObject {
  let node = tree.root as NodeObject
  while (node.children.length > 0) {
    node = node.children[0]
  }
  return node
}

export function movesFromRootToNode(
  tree: GameTree,
  nodeId: number
): { color: 'B' | 'W'; sgfCoord: string | null }[] {
  const path: NodeObject[] = []
  let current: NodeObject | null = tree.get(nodeId)
  while (current) {
    path.unshift(current)
    current =
      current.parentId === null || current.parentId === undefined
        ? null
        : tree.get(current.parentId)
  }

  const moves: { color: 'B' | 'W'; sgfCoord: string | null }[] = []
  for (const node of path) {
    if (node.data.B) moves.push({ color: 'B', sgfCoord: node.data.B[0] || null })
    else if (node.data.W) moves.push({ color: 'W', sgfCoord: node.data.W[0] || null })
  }
  return moves
}
