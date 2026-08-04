import { useEffect, useRef } from 'preact/hooks'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { effect } from '@preact/signals'
import { analysisByTurn } from '../state/appState'

export function WinrateChart() {
  const containerRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    plotRef.current = new uPlot(
      {
        width: containerRef.current.clientWidth || 600,
        height: 160,
        series: [
          {},
          { label: 'Winrate (B), %', stroke: '#4c9aff', width: 2 },
          { label: 'Score lead', stroke: '#ff6b6b', width: 2, dash: [6, 4], scale: 'score' },
        ],
        scales: {
          y: { range: [0, 100] },
          score: {},
        },
        axes: [{}, { scale: 'y', label: 'Winrate %' }, { scale: 'score', side: 1, label: 'Score lead' }],
      },
      [[], [], []],
      containerRef.current
    )

    const stopEffect = effect(() => {
      const entries = [...analysisByTurn.value.entries()].sort((a, b) => a[0] - b[0])
      const xs = entries.map(([turn]) => turn)
      const winrates = entries.map(([, r]) => r.rootInfo.winrate * 100)
      const scoreLeads = entries.map(([, r]) => r.rootInfo.scoreLead)
      plotRef.current?.setData([xs, winrates, scoreLeads])
    })

    return () => {
      stopEffect()
      plotRef.current?.destroy()
    }
  }, [])

  return <div ref={containerRef} class="winrate-chart" />
}
