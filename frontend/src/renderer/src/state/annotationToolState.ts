import { signal, computed } from '@preact/signals'
import type { AnnotationTool } from '../board/annotations'
import { nextLabelText } from '../board/annotations'
import { currentNode } from './appState'

export const selectedAnnotationTool = signal<AnnotationTool | null>(null)
export const labelMode = signal<'letter' | 'number'>('letter')
// Text the user manually typed for the next label placement, overriding the
// auto-suggestion below. Reset to null after each placement so the next
// suggestion is recomputed from the (now updated) tree.
export const labelTextOverride = signal<string | null>(null)

export const pendingLabelText = computed(() => {
  if (labelTextOverride.value !== null) return labelTextOverride.value
  const node = currentNode.value
  if (!node) return ''
  return nextLabelText(node, labelMode.value)
})
