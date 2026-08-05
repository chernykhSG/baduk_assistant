import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/preact'

// @testing-library/preact's own auto-cleanup only registers itself against a
// *global* afterEach (i.e. requires vitest's `globals: true`, which this
// project doesn't enable — test files import afterEach explicitly instead).
// Without this, components from a previous test are never unmounted, so
// their effects' cleanup functions (removing event listeners, etc.) never
// run — e.g. VariationTree's window-level keydown listener accumulated
// across every prior test, firing once per leaked instance.
afterEach(() => {
  cleanup()
})

// jsdom does not implement window.matchMedia, which uplot calls at module-load
// time (to detect device pixel ratio changes). Polyfill it so importing uplot
// inside the test environment does not throw.
if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false
    }) as unknown as MediaQueryList
}

// jsdom does not implement Path2D either — uplot uses it to build stroke/fill
// paths for series lines. A no-op stand-in is enough since we never inspect
// pixel output in tests.
if (typeof (globalThis as { Path2D?: unknown }).Path2D === 'undefined') {
  function Path2DStub(this: unknown) {
    return new Proxy(
      {},
      {
        get() {
          return () => {}
        }
      }
    )
  }
  ;(globalThis as unknown as { Path2D: unknown }).Path2D = Path2DStub
}

// jsdom does not implement ResizeObserver, which BoardView uses to size the
// board to its container. A no-op stand-in is enough since tests don't
// assert on measured pixel dimensions.
if (typeof (globalThis as { ResizeObserver?: unknown }).ResizeObserver === 'undefined') {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub
}

// jsdom does not implement Element.scrollIntoView, which VariationTree calls
// to keep the current move visible as the user navigates.
if (typeof Element !== 'undefined' && typeof Element.prototype.scrollIntoView !== 'function') {
  Element.prototype.scrollIntoView = function (): void {}
}

// jsdom does not implement a real 2D canvas rendering context (that requires
// the native "canvas" package). uplot draws its chart on a <canvas> during
// rendering, so provide a no-op 2D context stub — sufficient for tests that
// only assert on DOM structure, not pixel output.
if (typeof HTMLCanvasElement !== 'undefined') {
  HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement) {
    const canvas = this
    const store: Record<string, unknown> = {}
    return new Proxy(
      {},
      {
        get(_target, prop) {
          if (prop === 'canvas') return canvas
          if (prop in store) return store[prop as string]
          return () => {}
        },
        set(_target, prop, value) {
          store[prop as string] = value
          return true
        }
      }
    )
  } as unknown as typeof HTMLCanvasElement.prototype.getContext
}
