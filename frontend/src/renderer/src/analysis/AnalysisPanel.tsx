import { useState } from 'preact/hooks'
import type { JSX } from 'preact'
import { WinrateChart } from './WinrateChart'
import { LlmExplanationPanel } from './LlmExplanationPanel'

export function AnalysisPanel(): JSX.Element {
  const [tab, setTab] = useState<'katago' | 'llm'>('katago')

  return (
    <div class="analysis-panel">
      <div class="analysis-panel__tabs">
        <button
          type="button"
          class={
            tab === 'katago' ? 'analysis-panel__tab analysis-panel__tab--active' : 'analysis-panel__tab'
          }
          onClick={() => setTab('katago')}
        >
          KataGo
        </button>
        <button
          type="button"
          class={tab === 'llm' ? 'analysis-panel__tab analysis-panel__tab--active' : 'analysis-panel__tab'}
          onClick={() => setTab('llm')}
        >
          LLM
        </button>
      </div>
      {tab === 'katago' ? <WinrateChart /> : <LlmExplanationPanel />}
    </div>
  )
}
