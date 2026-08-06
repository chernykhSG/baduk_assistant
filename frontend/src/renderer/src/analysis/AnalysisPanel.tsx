import { useState } from 'preact/hooks'
import type { JSX } from 'preact'
import { WinrateChart } from './WinrateChart'
import { LlmExplanationPanel } from './LlmExplanationPanel'
import { AnnotationPanel } from './AnnotationPanel'

const TABS = [
  { id: 'katago' as const, label: 'KataGo' },
  { id: 'llm' as const, label: 'LLM' },
  { id: 'annotation' as const, label: 'Разметка' }
]

export function AnalysisPanel(): JSX.Element {
  const [tab, setTab] = useState<'katago' | 'llm' | 'annotation'>('katago')

  return (
    <div class="analysis-panel">
      <div class="analysis-panel__tabs">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            class={
              tab === id ? 'analysis-panel__tab analysis-panel__tab--active' : 'analysis-panel__tab'
            }
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === 'katago' && <WinrateChart />}
      {tab === 'llm' && <LlmExplanationPanel />}
      {tab === 'annotation' && <AnnotationPanel />}
    </div>
  )
}
