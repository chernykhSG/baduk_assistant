import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/preact'
import { AnalysisPanel } from '@renderer/analysis/AnalysisPanel'

vi.mock('@renderer/analysis/WinrateChart', () => ({
  WinrateChart: () => <div data-testid="winrate-chart" />
}))
vi.mock('@renderer/analysis/LlmExplanationPanel', () => ({
  LlmExplanationPanel: () => <div data-testid="llm-panel" />
}))
vi.mock('@renderer/analysis/AnnotationPanel', () => ({
  AnnotationPanel: () => <div class="annotation-panel" />
}))

describe('AnalysisPanel', () => {
  it('shows the KataGo tab by default', () => {
    const { getByTestId, queryByTestId } = render(<AnalysisPanel />)
    expect(getByTestId('winrate-chart')).toBeTruthy()
    expect(queryByTestId('llm-panel')).toBeNull()
  })

  it('switches to the LLM tab on click', () => {
    const { getByText, getByTestId, queryByTestId } = render(<AnalysisPanel />)
    fireEvent.click(getByText('LLM'))
    expect(getByTestId('llm-panel')).toBeTruthy()
    expect(queryByTestId('winrate-chart')).toBeNull()
  })

  it('shows an Разметка tab that renders the AnnotationPanel', () => {
    const { getByText, container } = render(<AnalysisPanel />)
    fireEvent.click(getByText('Разметка'))
    expect(container.querySelector('.annotation-panel')).toBeTruthy()
  })
})
