import { useEffect, useRef } from 'preact/hooks'
import type { JSX } from 'preact'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { effect } from '@preact/signals'
import { analysisByTurn, currentNodeId } from '../state/appState'

// uPlot draws axis tick labels and axis titles on <canvas>, so they're
// invisible to CSS entirely — the default `stroke` is a dark gray meant for
// a light page background, which on this app's dark theme was nearly
// indistinguishable from the background behind it.
const AXIS_TEXT_COLOR = '#c6c9d1'
const AXIS_GRID_COLOR = 'rgba(198, 201, 209, 0.15)'

export function WinrateChart(): JSX.Element {
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
          { label: 'Ход' },
          { label: 'Winrate (B), %', stroke: '#4c9aff', width: 2 },
          { label: 'Score lead', stroke: '#ff6b6b', width: 2, dash: [6, 4], scale: 'score' }
        ],
        scales: {
          // uPlot treats the x scale as Unix-time-in-seconds by default, so
          // our plain turn numbers (0, 1, 2...) were rendered as dates near
          // the epoch ("1/1/70 5:00am") with an axis labeled "Time".
          x: { time: false },
          y: { range: [0, 100] },
          score: {}
        },
        axes: [
          { label: 'Ход', stroke: AXIS_TEXT_COLOR, grid: { stroke: AXIS_GRID_COLOR } },
          {
            scale: 'y',
            label: 'Winrate %',
            stroke: AXIS_TEXT_COLOR,
            grid: { stroke: AXIS_GRID_COLOR }
          },
          {
            scale: 'score',
            side: 1,
            label: 'Score lead',
            stroke: AXIS_TEXT_COLOR,
            grid: { show: false }
          }
        ]
      },
      [[], [], []],
      container
    )

    const stopEffect = effect(() => {
      const entries = [...analysisByTurn.value.entries()].sort((a, b) => a[0] - b[0])
      const xs = entries.map(([turn]) => turn)
      const winrates = entries.map(([, r]) => r.rootInfo.winrate * 100)
      const scoreLeads = entries.map(([, r]) => r.rootInfo.scoreLead)
      const plot = plotRef.current
      if (!plot) return
      plot.setData([xs, winrates, scoreLeads])

      // Move the chart's cursor/legend to whatever move is currently
      // selected on the board, instead of only updating on mouse hover —
      // stepping through the tree should show that move's numbers without
      // having to separately point at the chart. setCursor() alone moves
      // the crosshair line but does NOT refresh the legend text (that's
      // driven by uPlot's own pointer-tracking, not the cursor position) —
      // setLegend() is the API that actually updates the displayed values.
      const nodeId = currentNodeId.value
      const index = nodeId === null ? -1 : xs.indexOf(nodeId)
      if (index !== -1) {
        plot.setCursor({
          left: plot.valToPos(xs[index], 'x'),
          top: plot.valToPos(winrates[index], 'y')
        })
        plot.setLegend({ idx: index })
      }
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
