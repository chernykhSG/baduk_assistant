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
    const container = containerRef.current

    plotRef.current = new uPlot(
      {
        width: container.clientWidth || 600,
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
      container
    )

    const stopEffect = effect(() => {
      const entries = [...analysisByTurn.value.entries()].sort((a, b) => a[0] - b[0])
      const xs = entries.map(([turn]) => turn)
      const winrates = entries.map(([, r]) => r.rootInfo.winrate * 100)
      const scoreLeads = entries.map(([, r]) => r.rootInfo.scoreLead)
      plotRef.current?.setData([xs, winrates, scoreLeads])
    })

    // uPlot's canvas is a fixed pixel size set once at construction — it
    // never tracks its container on its own, so maximizing/resizing the
    // window left the chart pinned at its original width. Re-applies the
    // container's current width on resize (rounded, and skipped when
    // unchanged, to avoid the same kind of ResizeObserver feedback loop
    // fixed in BoardView).
    let lastWidth = container.clientWidth
    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      const width = Math.round(entry.contentRect.width)
      if (width === 0 || width === lastWidth) return
      lastWidth = width
      plotRef.current?.setSize({ width, height: 160 })
    })
    resizeObserver.observe(container)

    return () => {
      resizeObserver.disconnect()
      stopEffect()
      plotRef.current?.destroy()
    }
  }, [])

  return <div ref={containerRef} class="winrate-chart" />
}
