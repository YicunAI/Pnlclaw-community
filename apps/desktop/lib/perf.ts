/**
 * Performance instrumentation for exchange-level frontend metrics.
 *
 * Tracks key timing milestones:
 * - route_change: navigation start
 * - chart_visible: chart canvas first paint
 * - ws_ready: WebSocket connection established
 * - first_data: first kline data rendered
 * - cache_hit: IndexedDB cache served data
 *
 * Usage:
 *   perf.mark("route_change")
 *   perf.mark("chart_visible")
 *   perf.measure("time_to_chart", "route_change", "chart_visible")
 */

type PerfEntry = {
  name: string
  timestamp: number
}

class PerfTracker {
  private marks = new Map<string, number>()
  private measures: Array<{ name: string; duration: number; from: string; to: string }> = []
  private enabled: boolean

  constructor() {
    this.enabled =
      typeof window !== "undefined" &&
      (process.env.NODE_ENV === "development" ||
        localStorage.getItem("pnlclaw-perf") === "1")
  }

  mark(name: string): void {
    if (!this.enabled) return
    const ts = performance.now()
    this.marks.set(name, ts)

    if (process.env.NODE_ENV === "development") {
      console.debug(`[perf] mark: ${name} @ ${ts.toFixed(1)}ms`)
    }
  }

  measure(name: string, from: string, to: string): number | null {
    if (!this.enabled) return null
    const start = this.marks.get(from)
    const end = this.marks.get(to)
    if (start === undefined || end === undefined) return null

    const duration = end - start
    this.measures.push({ name, duration, from, to })

    if (process.env.NODE_ENV === "development") {
      const color = duration < 200 ? "color: #10b981" : duration < 500 ? "color: #f59e0b" : "color: #ef4444"
      console.debug(`[perf] %c${name}: ${duration.toFixed(1)}ms%c (${from} → ${to})`, color, "color: inherit")
    }

    return duration
  }

  getMarks(): Map<string, number> {
    return new Map(this.marks)
  }

  getMeasures() {
    return [...this.measures]
  }

  reset(): void {
    this.marks.clear()
    this.measures.length = 0
  }
}

export const perf = new PerfTracker()
