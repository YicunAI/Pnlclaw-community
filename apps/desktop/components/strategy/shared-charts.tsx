import React from "react"

function formatChartValue(value: number, negative?: boolean): string {
  if (!Number.isFinite(value)) return "—"
  if (negative) return value.toFixed(3)
  if (Math.abs(value) >= 1000) return value.toFixed(0)
  if (Math.abs(value) >= 100) return value.toFixed(1)
  return value.toFixed(2)
}

function buildGradientId(prefix: string, curve: number[]): string {
  return `${prefix}-${curve.length}-${Math.round(curve[0] ?? 0)}-${Math.round(curve[curve.length - 1] ?? 0)}`
}

/* ---------- CurveChart ---------- */

export function CurveChart({
  curve,
  negative = false,
  baselineCurve,
  baselineLabel,
  emptyLabel,
  height = 220,
}: {
  curve: number[]
  negative?: boolean
  baselineCurve?: number[]
  baselineLabel?: string
  emptyLabel?: string
  height?: number
}) {
  if (curve.length < 2) {
    return (
      <p className="flex h-[220px] items-center justify-center rounded-xl border border-dashed border-border/70 bg-muted/20 px-4 text-sm text-muted-foreground">
        {emptyLabel ?? "—"}
      </p>
    )
  }

  const w = 640
  const h = height
  const padX = 54
  const padY = 20

  const allValues = baselineCurve ? [...curve, ...baselineCurve] : curve
  const min = Math.min(...allValues)
  const max = Math.max(...allValues)
  const range = max - min || 1
  const gradientId = buildGradientId(negative ? "ddGrad" : "eqGrad", curve)
  const stroke = negative
    ? "#f59e0b"
    : curve[curve.length - 1] >= curve[0]
      ? "#22c55e"
      : "#ef4444"

  const toPath = (data: number[]) =>
    data
      .map((v, i) => {
        const x = padX + (i / (data.length - 1)) * (w - padX * 2)
        const y = padY + (1 - (v - min) / range) * (h - padY * 2)
        return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`
      })
      .join(" ")

  const path = toPath(curve)
  const areaPath = `${path} L ${(w - padX).toFixed(1)} ${(h - padY).toFixed(1)} L ${padX.toFixed(1)} ${(h - padY).toFixed(1)} Z`
  const lastPointX = padX + (w - padX * 2)
  const lastPointY = padY + (1 - (curve[curve.length - 1] - min) / range) * (h - padY * 2)

  return (
    <div className="space-y-3">
      {baselineCurve && baselineCurve.length >= 2 && baselineLabel ? (
        <div className="flex flex-wrap items-center justify-between gap-3 text-[11px] text-muted-foreground">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: stroke }} />
              <span>Strategy</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-px w-5 border-t border-dashed border-white/40" />
              <span>{baselineLabel}</span>
            </div>
          </div>
          <div className="rounded-full border border-border/70 bg-background/70 px-2.5 py-1 font-mono text-[11px] text-foreground/80">
            Last {formatChartValue(curve[curve.length - 1], negative)}
          </div>
        </div>
      ) : null}
      <div className="overflow-hidden rounded-xl border border-border/70 bg-[#111317] px-2 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
        <svg viewBox={`0 0 ${w} ${h}`} className="w-full overflow-visible">
          {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
            const y = padY + pct * (h - padY * 2)
            const val = max - pct * range
            return (
              <g key={pct}>
                <line x1={padX} y1={y} x2={w - padX} y2={y} stroke="rgba(255,255,255,0.035)" />
                <text x={padX - 8} y={y + 4} textAnchor="end" fontSize={10} className="fill-muted-foreground/75">
                  {formatChartValue(val, negative)}
                </text>
              </g>
            )
          })}
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.2} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <path d={areaPath} fill={`url(#${gradientId})`} />
          <path d={path} fill="none" stroke={stroke} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
          {baselineCurve && baselineCurve.length >= 2 && (
            <path
              d={toPath(baselineCurve)}
              fill="none"
              stroke="rgba(255,255,255,0.34)"
              strokeWidth={1.2}
              strokeDasharray="5 4"
              strokeLinecap="round"
            />
          )}
          <circle cx={lastPointX} cy={lastPointY} r={4.2} fill={stroke} stroke="rgba(17,19,23,0.96)" strokeWidth={2.4} />
        </svg>
      </div>
    </div>
  )
}

/* ---------- MetricCard ---------- */

export function MetricCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string
  value: string
  icon: React.ComponentType<{ className?: string }>
  color?: string
}) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
      <Icon className={`h-4 w-4 ${color || "text-primary"}`} />
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className={`text-sm font-medium font-mono ${color || ""}`}>{value}</p>
      </div>
    </div>
  )
}

/* ---------- TradeDistribution ---------- */

export interface TradeDataRow {
  pnl?: number | string | null
  [key: string]: unknown
}

export function TradeDistribution({
  trades,
  emptyLabel,
  rangeLabel,
}: {
  trades: TradeDataRow[]
  emptyLabel?: string
  rangeLabel?: string
}) {
  const pnls = trades.map((trade) => Number(trade.pnl ?? 0)).filter((v) => Number.isFinite(v))
  if (pnls.length === 0) {
    return <p className="text-sm text-muted-foreground text-center py-8">{emptyLabel ?? "—"}</p>
  }

  const min = Math.min(...pnls)
  const max = Math.max(...pnls)
  const bucketCount = Math.min(8, Math.max(4, pnls.length))
  const width = max - min || 1
  const buckets = Array.from({ length: bucketCount }, (_, index) => {
    const start = min + (width / bucketCount) * index
    const end = index === bucketCount - 1 ? max : min + (width / bucketCount) * (index + 1)
    const count = pnls.filter((v) => v >= start && (index === bucketCount - 1 ? v <= end : v < end)).length
    return { start, end, count }
  })
  const maxCount = Math.max(...buckets.map((b) => b.count), 1)

  return (
    <div className="space-y-3">
      {rangeLabel ? (
        <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          <span>{rangeLabel}</span>
          <span>{pnls.length}</span>
        </div>
      ) : null}
      {buckets.map((bucket, index) => {
        const tone = bucket.end <= 0 ? "bg-red-400" : bucket.start >= 0 ? "bg-emerald-400" : "bg-amber-400"
        return (
          <div key={`${bucket.start}-${index}`} className="rounded-xl border border-border/60 bg-background/30 px-3 py-2">
            <div className="mb-2 flex items-center justify-between gap-4 text-xs text-muted-foreground">
              <span className="font-mono">{bucket.start.toFixed(2)} to {bucket.end.toFixed(2)}</span>
              <span className="font-semibold text-foreground/80">{bucket.count}</span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-muted/70">
              <div className={`h-full rounded-full ${tone}`} style={{ width: `${(bucket.count / maxCount) * 100}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ---------- MonthlyReturnsHeatmap ---------- */

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

function computeMonthlyReturns(
  curve: number[],
  startDate?: string | null,
  endDate?: string | null,
): { label: string; value: number }[] {
  if (curve.length < 2) return []

  const start = startDate ? new Date(startDate) : null
  const end = endDate ? new Date(endDate) : null

  if (!start || !end || isNaN(start.getTime()) || isNaN(end.getTime())) {
    const totalReturn = curve[0] ? (curve[curve.length - 1] - curve[0]) / curve[0] : 0
    return [{ label: "Total", value: totalReturn }]
  }

  const totalMs = end.getTime() - start.getTime()
  if (totalMs <= 0) {
    const totalReturn = curve[0] ? (curve[curve.length - 1] - curve[0]) / curve[0] : 0
    return [{ label: "Total", value: totalReturn }]
  }

  const monthBuckets = new Map<string, { startIdx: number; endIdx: number }>()

  for (let i = 0; i < curve.length; i++) {
    const t = start.getTime() + (i / (curve.length - 1)) * totalMs
    const d = new Date(t)
    const key = `${d.getFullYear()}-${d.getMonth()}`
    const existing = monthBuckets.get(key)
    if (existing) {
      existing.endIdx = i
    } else {
      monthBuckets.set(key, { startIdx: i, endIdx: i })
    }
  }

  const results: { label: string; value: number }[] = []
  for (const [key, { startIdx, endIdx }] of monthBuckets) {
    const [year, monthStr] = key.split("-")
    const monthIdx = parseInt(monthStr, 10)
    const label = monthBuckets.size > 6
      ? `${MONTH_LABELS[monthIdx]} ${year.slice(2)}`
      : MONTH_LABELS[monthIdx]
    const sv = curve[startIdx]
    const ev = curve[endIdx]
    const ret = sv ? (ev - sv) / sv : 0
    results.push({ label, value: ret })
  }

  return results
}

export function MonthlyReturnsHeatmap({
  curve,
  startDate,
  endDate,
  emptyLabel,
  positiveLabel,
  negativeLabel,
}: {
  curve: number[]
  startDate?: string | null
  endDate?: string | null
  emptyLabel?: string
  positiveLabel?: string
  negativeLabel?: string
}) {
  if (curve.length < 2) {
    return <p className="text-sm text-muted-foreground text-center py-8">{emptyLabel ?? "—"}</p>
  }

  const values = computeMonthlyReturns(curve, startDate, endDate)

  if (values.length === 0) {
    return <p className="text-sm text-muted-foreground text-center py-8">{emptyLabel ?? "—"}</p>
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4 text-[11px] text-muted-foreground">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" />
          <span>{positiveLabel}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-red-400/80" />
          <span>{negativeLabel}</span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
        {values.map((item) => {
          const intensity = Math.min(1, Math.abs(item.value) * 8)
          const background = item.value >= 0
            ? `rgba(16, 185, 129, ${0.18 + intensity * 0.4})`
            : `rgba(239, 68, 68, ${0.18 + intensity * 0.4})`
          return (
            <div key={item.label} className="rounded-xl border border-border/70 p-3 shadow-sm" style={{ backgroundColor: background }}>
              <div className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">{item.label}</div>
              <div className="mt-2 text-lg font-semibold font-mono text-foreground">{(item.value * 100).toFixed(2)}%</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ---------- Buy & Hold baseline generator ---------- */

export function generateBuyHoldCurve(equityCurve: number[]): number[] {
  if (equityCurve.length < 2) return []
  const start = equityCurve[0]
  const end = equityCurve[equityCurve.length - 1]
  const totalReturn = end / start
  return equityCurve.map((_, i) => {
    const progress = i / (equityCurve.length - 1)
    return start * (1 + (totalReturn - 1) * progress)
  })
}
