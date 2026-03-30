"use client"

import React, { useEffect, useState, useCallback, useRef, useId, useMemo } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { getPaperEquityHistory, type PaperEquityPoint } from "@/lib/api-client"
import { useI18n } from "@/components/i18n/use-i18n"
import { TrendingUp, TrendingDown, Activity } from "lucide-react"

interface PNLCurvePanelProps {
  accountId: string
  className?: string
  noWrapper?: boolean
  compact?: boolean
  /** WS-driven equity points from the parent (appended in real-time). */
  wsEquityPoints?: PaperEquityPoint[]
  /** Called after the initial REST history is loaded so the parent can seed the WS hook. */
  onHistoryLoaded?: (points: PaperEquityPoint[]) => void
  /** Real-time equity (walletBalance + unrealizedPnl) driven by WS ticker. */
  liveEquity?: number
  /** Initial capital (e.g. 100000 USDT). Used as the baseline for PnL% calculation,
   *  matching the OKX-style return = (equity - initial) / initial. */
  initialBalance?: number
  /** @deprecated Use wsEquityPoints instead. Changing this value forces a re-fetch. */
  refreshTrigger?: number
}

export function PNLCurvePanel({
  accountId,
  className,
  noWrapper = false,
  compact = false,
  wsEquityPoints,
  onHistoryLoaded,
  liveEquity,
  initialBalance,
  refreshTrigger,
}: PNLCurvePanelProps) {
  const { t } = useI18n()
  const [restHistory, setRestHistory] = useState<PaperEquityPoint[]>([])
  const [loading, setLoading] = useState(true)
  const prevAccountId = useRef(accountId)

  const fetchHistory = useCallback(async () => {
    if (!accountId) return
    try {
      const res = await getPaperEquityHistory(accountId, 200)
      if (res.data) {
        setRestHistory(res.data)
        onHistoryLoaded?.(res.data)
      }
    } finally {
      setLoading(false)
    }
  }, [accountId, onHistoryLoaded])

  useEffect(() => {
    if (prevAccountId.current !== accountId) {
      setRestHistory([])
      setLoading(true)
      prevAccountId.current = accountId
    }
    fetchHistory()
  }, [fetchHistory, accountId])

  // --- Live equity sampling: record a data point every 10s ---
  const [liveSamples, setLiveSamples] = useState<PaperEquityPoint[]>([])
  const liveEquityRef = useRef(liveEquity)
  liveEquityRef.current = liveEquity
  const hasLiveEquity = liveEquity !== undefined

  useEffect(() => {
    setLiveSamples([])
  }, [accountId])

  useEffect(() => {
    if (refreshTrigger !== undefined && refreshTrigger > 0) {
      setRestHistory([])
      setLiveSamples([])
      setLoading(true)
      fetchHistory()
    }
  }, [refreshTrigger]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!hasLiveEquity) return
    const id = setInterval(() => {
      const val = liveEquityRef.current
      if (val === undefined) return
      setLiveSamples((prev) => [
        ...prev.slice(-60),
        { timestamp: new Date().toISOString(), equity: val },
      ])
    }, 10_000)
    return () => clearInterval(id)
  }, [accountId, hasLiveEquity])

  const history = useMemo(() => {
    let merged: PaperEquityPoint[]

    if (!wsEquityPoints || wsEquityPoints.length === 0) {
      merged = [...restHistory]
    } else if (restHistory.length === 0) {
      merged = [...wsEquityPoints]
    } else {
      const lastRestTs = restHistory[restHistory.length - 1]?.timestamp ?? ""
      const newer = wsEquityPoints.filter((p) => p.timestamp > lastRestTs)
      merged = newer.length > 0 ? [...restHistory, ...newer] : [...restHistory]
    }

    if (liveSamples.length > 0) {
      const lastTs = merged.length > 0 ? (merged[merged.length - 1]?.timestamp ?? "") : ""
      for (const s of liveSamples) {
        if (!lastTs || s.timestamp > lastTs) merged.push(s)
      }
    }

    if (liveEquity !== undefined) {
      merged.push({ timestamp: new Date().toISOString(), equity: liveEquity })
    }

    return merged.slice(-200)
  }, [restHistory, wsEquityPoints, liveSamples, liveEquity])

  if (loading && history.length === 0) {
    return noWrapper ? (
      <div className={className}>
        <div className="h-[120px] flex items-center justify-center">
          <Activity className="h-5 w-5 animate-pulse text-muted-foreground opacity-20" />
        </div>
      </div>
    ) : (
      <Card className={className}>
        <CardContent className="h-[120px] flex items-center justify-center">
          <Activity className="h-5 w-5 animate-pulse text-muted-foreground opacity-20" />
        </CardContent>
      </Card>
    )
  }

  const curve = history.map(p => p.equity)
  const currentEquity = curve.length > 0 ? curve[curve.length - 1] : 0
  const baseline = initialBalance && initialBalance > 0 ? initialBalance : (curve.length > 0 ? curve[0] : 0)
  const isProfit = currentEquity >= baseline

  const pnlValue = currentEquity - baseline
  const pnlPct = baseline > 0 ? (pnlValue / baseline) * 100 : 0

  const content = (
    <>
      <div className={`flex flex-row items-center justify-between pb-2 ${noWrapper ? "px-0" : "px-4 pt-2"}`}>
        <div className="text-xs font-medium flex items-center gap-1.5">
          {isProfit ? (
            <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <TrendingDown className="h-3.5 w-3.5 text-red-400" />
          )}
          {t("paper.equityCurveTitle") || "\u6536\u76ca\u66f2\u7ebf"}
        </div>
        {curve.length > 0 && (
          <div className="flex items-center gap-3 text-[11px] font-mono">
            <span className="text-muted-foreground">{baseline.toFixed(0)} \u2192</span>
            <span className={isProfit ? "text-emerald-400" : "text-red-400"}>
              {currentEquity.toFixed(2)}
            </span>
            <span className={`px-1.5 py-0.5 rounded text-[10px] ${isProfit ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"}`}>
              {pnlValue >= 0 ? "+" : ""}{pnlValue.toFixed(2)} ({pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%)
            </span>
          </div>
        )}
      </div>
      <div className={compact ? "h-[120px] w-full" : "h-[180px] w-full"}>
        {curve.length > 1 ? (
          <EquityCurveSVG curve={curve} />
        ) : (
          <div className="h-full flex items-center justify-center text-[10px] text-muted-foreground opacity-50">
            {t("paper.noEquityHistory") || "\u6682\u65e0\u5386\u53f2\u6570\u636e"}
          </div>
        )}
      </div>
    </>
  )

  if (noWrapper) {
    return <div className={className}>{content}</div>
  }

  return (
    <Card className={className}>
      <CardContent className="p-0 pb-1">
        {content}
      </CardContent>
    </Card>
  )
}

function EquityCurveSVG({ curve }: { curve: number[] }) {
  const gradientId = useId()
  const w = 300
  const h = 100
  const padX = 5
  const padY = 10
  const min = Math.min(...curve)
  const max = Math.max(...curve)
  const range = max - min || 1

  const path = curve
    .map((v, i) => {
      const x = padX + (i / (curve.length - 1)) * (w - padX * 2)
      const y = padY + (1 - (v - min) / range) * (h - padY * 2)
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(" ")

  const areaPath = `${path} L ${(w - padX).toFixed(1)} ${(h - padY).toFixed(1)} L ${padX.toFixed(1)} ${(h - padY).toFixed(1)} Z`
  const isProfit = curve[curve.length - 1] >= curve[0]

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={isProfit ? "#10b981" : "#ef4444"} stopOpacity={0.2} />
          <stop offset="100%" stopColor={isProfit ? "#10b981" : "#ef4444"} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} />
      <path d={path} fill="none" stroke={isProfit ? "#10b981" : "#ef4444"} strokeWidth={1} />
    </svg>
  )
}
