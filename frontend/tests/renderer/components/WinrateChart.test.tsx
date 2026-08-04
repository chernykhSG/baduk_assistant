import { describe, it, expect, afterEach } from 'vitest'
import { render } from '@testing-library/preact'
import { WinrateChart } from '@renderer/analysis/WinrateChart'
import { analysisByTurn } from '@renderer/state/appState'

afterEach(() => {
  analysisByTurn.value = new Map()
})

describe('WinrateChart', () => {
  it('renders a chart container without throwing when no data is present', () => {
    const { container } = render(<WinrateChart />)
    expect(container.querySelector('.winrate-chart')).toBeTruthy()
  })

  it('re-renders without throwing once analysis data arrives', () => {
    const { container, rerender } = render(<WinrateChart />)
    analysisByTurn.value = new Map([
      [0, { id: 'a', moveInfos: [], rootInfo: { winrate: 0.5, scoreLead: 0, visits: 1 } }],
      [1, { id: 'b', moveInfos: [], rootInfo: { winrate: 0.55, scoreLead: 1.2, visits: 1 } }],
    ])
    rerender(<WinrateChart />)
    expect(container.querySelector('.winrate-chart')).toBeTruthy()
  })
})
