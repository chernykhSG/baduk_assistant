import type GameTree from '@sabaki/immutable-gametree'
import type { Marker } from '@sabaki/shudan'
import type { NodeObject } from './sgfLoader'
import { sgfCoordToVertex } from './boardPosition'

export type FigureProperty = 'TR' | 'SQ' | 'CR' | 'MA'
export type AnnotationTool = FigureProperty | 'LB' | 'erase'

const FIGURE_PROPERTIES: FigureProperty[] = ['TR', 'SQ', 'CR', 'MA']

const FIGURE_TO_MARKER_TYPE: Record<FigureProperty, Marker['type']> = {
  TR: 'triangle',
  SQ: 'square',
  CR: 'circle',
  MA: 'cross'
}

/**
 * The subset of @sabaki/immutable-gametree's Draft class this module uses.
 * Neither @sabaki/sgf nor @sabaki/immutable-gametree ship TypeScript types
 * (confirmed against their published package.json/source) — this local
 * interface lets `tree.mutate(draft => ...)` callbacks stay typed without
 * an explicit `any`, matching how the rest of this codebase (sgfLoader.ts's
 * NodeObject) hand-rolls shapes for these two libraries.
 */
interface TreeDraft {
  get(id: number): NodeObject | null
  addToProperty(id: number, property: string, value: string): boolean
  removeFromProperty(id: number, property: string, value: string): boolean
  updateProperty(id: number, property: string, values: string[]): boolean
}

export function vertexToSgfCoord(vertex: [number, number]): string {
  const [x, y] = vertex
  return String.fromCharCode('a'.charCodeAt(0) + x) + String.fromCharCode('a'.charCodeAt(0) + y)
}

function clearMarkupInDraft(draft: TreeDraft, nodeId: number, coord: string): void {
  const node = draft.get(nodeId)
  if (!node) return

  for (const property of FIGURE_PROPERTIES) {
    if (node.data[property]?.includes(coord)) {
      draft.removeFromProperty(nodeId, property, coord)
    }
  }

  const existingLabel = node.data.LB?.find((entry) => entry.split(':')[0] === coord)
  if (existingLabel) {
    draft.removeFromProperty(nodeId, 'LB', existingLabel)
  }
}

export function addFigureMarkup(
  tree: GameTree,
  nodeId: number,
  property: FigureProperty,
  vertex: [number, number]
): GameTree {
  const coord = vertexToSgfCoord(vertex)
  return tree.mutate((draft: TreeDraft) => {
    clearMarkupInDraft(draft, nodeId, coord)
    draft.addToProperty(nodeId, property, coord)
  })
}

export function addLabelMarkup(
  tree: GameTree,
  nodeId: number,
  vertex: [number, number],
  text: string
): GameTree {
  const coord = vertexToSgfCoord(vertex)
  return tree.mutate((draft: TreeDraft) => {
    clearMarkupInDraft(draft, nodeId, coord)
    draft.addToProperty(nodeId, 'LB', `${coord}:${text}`)
  })
}

export function removeMarkupAtVertex(
  tree: GameTree,
  nodeId: number,
  vertex: [number, number]
): GameTree {
  const coord = vertexToSgfCoord(vertex)
  return tree.mutate((draft: TreeDraft) => {
    clearMarkupInDraft(draft, nodeId, coord)
  })
}

export function setComment(tree: GameTree, nodeId: number, text: string): GameTree {
  return tree.mutate((draft: TreeDraft) => {
    draft.updateProperty(nodeId, 'C', text.length > 0 ? [text] : [])
  })
}

export function nextLabelText(node: NodeObject, mode: 'letter' | 'number'): string {
  const labels = node.data.LB ?? []
  const texts = labels.map((entry) => entry.slice(entry.indexOf(':') + 1))

  if (mode === 'letter') {
    const letterCount = texts.filter((text) => /^[A-Za-z]+$/.test(text)).length
    return letterCount < 26 ? String.fromCharCode(65 + letterCount) : String(letterCount + 1)
  }

  const numberCount = texts.filter((text) => /^\d+$/.test(text)).length
  return String(numberCount + 1)
}

export function emptyMarkerGrid(boardSize: number): (Marker | null)[][] {
  const grid: (Marker | null)[][] = []
  for (let y = 0; y < boardSize; y++) {
    grid.push(new Array(boardSize).fill(null))
  }
  return grid
}

export function buildAnnotationMarkerMap(node: NodeObject, boardSize: number): (Marker | null)[][] {
  const grid = emptyMarkerGrid(boardSize)

  for (const property of FIGURE_PROPERTIES) {
    for (const coord of node.data[property] ?? []) {
      const vertex = sgfCoordToVertex(coord)
      if (!vertex) continue
      grid[vertex[1]][vertex[0]] = { type: FIGURE_TO_MARKER_TYPE[property] }
    }
  }

  for (const entry of node.data.LB ?? []) {
    const separatorIndex = entry.indexOf(':')
    if (separatorIndex === -1) continue
    const coord = entry.slice(0, separatorIndex)
    const label = entry.slice(separatorIndex + 1)
    const vertex = sgfCoordToVertex(coord)
    if (!vertex) continue
    grid[vertex[1]][vertex[0]] = { type: 'label', label }
  }

  return grid
}
