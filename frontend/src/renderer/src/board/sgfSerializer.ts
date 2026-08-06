import * as sgf from '@sabaki/sgf'
import type GameTree from '@sabaki/immutable-gametree'

export function serializeTree(tree: GameTree): string {
  return sgf.stringify(tree.root)
}
