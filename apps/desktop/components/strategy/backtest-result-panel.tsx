"use client"

import React, { useCallback, useEffect, useMemo, useState } from "react"
import {
  getKlines,
  type BacktestData,
  type BacktestTradeData,
  type KlineData,
  type StrategyData,
} from "@/lib/api-client"
import {
  CurveChart,
  MonthlyReturnsHeatmap,
  TradeDistribution,
  generateBuyHoldCurve,
} from "@/components/strategy/shared-charts"
import CandlestickChart, { type TradeMarker } from "@/components/trading/candlestick-chart"
import { BarChart3 } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { useI18n } from "@/components/i18n/use-i18n"

const ALL_TIMEFRAMES = [
  { value: "1m",  label: "1m" },
  { value: "3m",  label: "3m" },
  { value: "5m",  label: "5m" },
  { value: "15m", label: "15m" },
  { value: "30m", label: "30m" },
  { value: "1h",  label: "1H" },
  { value: "2h",  label: "2H" },
  { value: "4h",  label: "4H" },
  { value: "6h",  label: "6H" },
  { value: "8h",  label: "8H" },
  { value: "12h", label: "12H" },
  { value: "1d",  label: "1D" },
  { value: "3d",  label: "3D" },
  { value: "1w",  label: "1W" },
  { value: "1M",  label: "1M" },
] as const

type TradeDirection = "long" | "short"

interface RoundTripTrade {
  id: string
  side: TradeDirection
  entryTime: number
  exitTime: number
  entryPrice: number
  exitPrice: number
  quantity: number
  pnl: number
}

export interface BacktestResultPanelProps {
  result: BacktestData | null
  strategy?: StrategyData | null
  symbolOverride?: string
  intervalOverride?: string
  loading?: boolean
}

function normalizeDirection(side: string | undefined): TradeDirection | null {
  if (!side) return null
  const s = side.toLowerCase()
  if (s === "long") return "long"
  if (s === "short") return "short"
  return null
}

function normalizeKlinesResponse(data: unknown): KlineData[] {
  if (Array.isArray(data)) return data as KlineData[]
  const nested = (data as { klines?: KlineData[] } | null)?.klines
  return Array.isArray(nested) ? nested : []
}

function dedupeAndSortKlines(data: KlineData[]): KlineData[] {
  return data
    .filter((v, i, a) => a.findIndex((t) => t.timestamp === v.timestamp) === i)
    .sort((a, b) => a.timestamp - b.timestamp)
}

function toFiniteNumber(value: unknown): number | null {
  const num = typeof value === "number" ? value : Number(value)
  return Number.isFinite(num) ? num : null
}

function normalizeTrade(trade: BacktestTradeData, index: number): RoundTripTrade | null {
  const side = normalizeDirection(typeof trade.side === "string" ? trade.side : undefined)
  const entryTime = toFiniteNumber(trade.entry_time)
  const exitTime = toFiniteNumber(trade.exit_time)
  const entryPrice = toFiniteNumber(trade.entry_price)
  const exitPrice = toFiniteNumber(trade.exit_price)
  const quantity = toFiniteNumber(trade.quantity)
  const pnl = toFiniteNumber(trade.pnl)

  if (!side || entryTime == null || exitTime == null || entryPrice == null || exitPrice == null || quantity == null || pnl == null) {
    return null
  }

  return { id: `${side}-${entryTime}-${exitTime}-${index}`, side, entryTime, exitTime, entryPrice, exitPrice, quantity, pnl }
}

function pct(v: number) {
  return `${(v * 100).toFixed(2)}%`
}

function StatCell({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="min-w-0">
      <div className="truncate text-[10px] text-muted-foreground">{label}</div>
      <div className={`text-sm font-semibold tabular-nums ${color ?? "text-foreground"}`}>{value}</div>
    </div>
  )
}

export function BacktestResultPanel({ result, strategy, symbolOverride, intervalOverride, loading }: BacktestResultPanelProps) {
  const { t } = useI18n()
  const [klineHistory, setKlineHistory] = useState<KlineData[]>([])
  const [isLoadingKlines, setIsLoadingKlines] = useState(false)
  const [noMoreKlines, setNoMoreKlines] = useState(false)
  const [selectedTradeId, setSelectedTradeId] = useState<string | null>(null)
  const [chartTimeframe, setChartTimeframe] = useState<string>("")

  const metrics = result?.result?.metrics
  const equityCurve: number[] = Array.isArray(result?.result?.equity_curve)
    ? result?.result?.equity_curve ?? []
    : Array.isArray(result?.equity_curve)
      ? result?.equity_curve ?? []
      : []
  const trades: BacktestTradeData[] = Array.isArray(result?.result?.trades)
    ? result?.result?.trades ?? []
    : Array.isArray(result?.trades)
      ? result?.trades ?? []
      : []

  const strategyLabel = strategy?.name ?? result?.strategy_name ?? "—"

  const tradeSymbolFallback = useMemo(() => {
    if (trades.length === 0) return ""
    const sym = trades.find((t) => t.symbol)?.symbol
    return sym ?? ""
  }, [trades])

  const chartSymbol = strategy?.symbols?.[0] || strategy?.symbol || symbolOverride || result?.symbol || tradeSymbolFallback
  const defaultInterval = strategy?.interval || intervalOverride || result?.interval || "1h"
  const chartInterval = chartTimeframe || defaultInterval
  const shouldShowPriceChart = Boolean(chartSymbol && chartInterval)

  useEffect(() => { setChartTimeframe("") }, [strategy?.interval])

  const totalReturn = metrics?.total_return ?? result?.total_return ?? 0
  const annualReturn = metrics?.annual_return ?? result?.annual_return ?? 0
  const sharpe = metrics?.sharpe_ratio ?? result?.sharpe_ratio ?? 0
  const maxDD = metrics?.max_drawdown ?? result?.max_drawdown ?? 0
  const winRate = metrics?.win_rate ?? result?.win_rate ?? 0
  const profitFactor = metrics?.profit_factor ?? result?.profit_factor ?? 0
  const totalTrades = metrics?.total_trades ?? result?.total_trades ?? 0
  const calmar = metrics?.calmar_ratio ?? result?.calmar_ratio ?? 0
  const sortino = metrics?.sortino_ratio ?? result?.sortino_ratio ?? 0

  const buyHoldCurve = useMemo(() => {
    const backendCurve = result?.result?.buy_hold_curve ?? result?.buy_hold_curve
    if (Array.isArray(backendCurve) && backendCurve.length >= 2) return backendCurve
    return generateBuyHoldCurve(equityCurve)
  }, [result, equityCurve])

  const normalizedTrades = useMemo(
    () => trades.map((trade, index) => normalizeTrade(trade, index)).filter((trade): trade is RoundTripTrade => trade !== null),
    [trades]
  )

  const selectedTrade = useMemo(
    () => normalizedTrades.find((trade) => trade.id === selectedTradeId) ?? normalizedTrades[0] ?? null,
    [normalizedTrades, selectedTradeId]
  )

  const tradeActions = useMemo(() => {
    const actions: {
      id: string
      type: "open" | "close"
      side: TradeDirection
      time: number
      price: number
      quantity: number
      pnl: number | null
      returnPct: number | null
    }[] = []
    for (const tr of normalizedTrades) {
      actions.push({
        id: `${tr.id}-open`,
        type: "open",
        side: tr.side,
        time: tr.entryTime,
        price: tr.entryPrice,
        quantity: tr.quantity,
        pnl: null,
        returnPct: null,
      })
      const ret = tr.entryPrice !== 0 ? (tr.pnl / (tr.entryPrice * tr.quantity)) * 100 : 0
      actions.push({
        id: `${tr.id}-close`,
        type: "close",
        side: tr.side,
        time: tr.exitTime,
        price: tr.exitPrice,
        quantity: tr.quantity,
        pnl: tr.pnl,
        returnPct: ret,
      })
    }
    return actions.sort((a, b) => b.time - a.time)
  }, [normalizedTrades])

  const positionRecords = useMemo(() => {
    return [...normalizedTrades]
      .sort((a, b) => b.exitTime - a.exitTime)
      .map((tr) => {
        const durationMs = tr.exitTime - tr.entryTime
        const hours = Math.floor(durationMs / 3_600_000)
        const mins = Math.floor((durationMs % 3_600_000) / 60_000)
        const holdingTime = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`
        const returnPct = tr.entryPrice !== 0 ? (tr.pnl / (tr.entryPrice * tr.quantity)) * 100 : 0
        return {
          id: tr.id,
          side: tr.side,
          entryTime: tr.entryTime,
          exitTime: tr.exitTime,
          avgEntry: tr.entryPrice,
          exitPrice: tr.exitPrice,
          totalQty: tr.quantity,
          realizedPnl: tr.pnl,
          holdingTime,
          returnPct,
        }
      })
  }, [normalizedTrades])

  useEffect(() => {
    if (normalizedTrades.length === 0) { setSelectedTradeId(null); return }
    setSelectedTradeId((cur) => cur && normalizedTrades.some((t) => t.id === cur) ? cur : normalizedTrades[0].id)
  }, [normalizedTrades])

  useEffect(() => {
    if (!shouldShowPriceChart) { setKlineHistory([]); setNoMoreKlines(false); return }
    let cancelled = false
    setNoMoreKlines(false)
    ;(async () => {
      setIsLoadingKlines(true)
      const res = await getKlines(chartSymbol, chartInterval, 500)
      if (!cancelled) { setKlineHistory(dedupeAndSortKlines(normalizeKlinesResponse(res.data))); setIsLoadingKlines(false) }
    })()
    return () => { cancelled = true }
  }, [chartInterval, chartSymbol, shouldShowPriceChart, result?.id, result?.task_id])

  const handleLoadMoreKlines = useCallback(async () => {
    if (!shouldShowPriceChart || isLoadingKlines || noMoreKlines || klineHistory.length === 0) return
    setIsLoadingKlines(true)
    try {
      const oldestTs = klineHistory[0].timestamp
      const res = await getKlines(chartSymbol, chartInterval, 500, undefined, oldestTs - 1)
      const batch = normalizeKlinesResponse(res.data)
      if (batch.length === 0) { setNoMoreKlines(true) } else { setKlineHistory((prev) => dedupeAndSortKlines([...batch, ...prev])) }
    } finally { setIsLoadingKlines(false) }
  }, [chartInterval, chartSymbol, isLoadingKlines, klineHistory, noMoreKlines, shouldShowPriceChart])

  const chartMarkers: TradeMarker[] = useMemo(() => {
    return normalizedTrades.flatMap((trade) => {
      const isLong = trade.side === "long"
      return [
        {
          time: Math.floor(trade.entryTime / 1000),
          position: isLong ? ("belowBar" as const) : ("aboveBar" as const),
          color: isLong ? "#10b981" : "#ef4444",
          shape: isLong ? ("arrowUp" as const) : ("arrowDown" as const),
          text: t(isLong ? "strategies.studio.longEntry" : "strategies.studio.shortEntry"),
        },
        {
          time: Math.floor(trade.exitTime / 1000),
          position: isLong ? ("aboveBar" as const) : ("belowBar" as const),
          color: isLong ? "#34d399" : "#f87171",
          shape: "square" as const,
          text: t(isLong ? "strategies.studio.longExit" : "strategies.studio.shortExit"),
        },
      ]
    })
  }, [normalizedTrades, t])

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-[360px] w-full rounded-lg" />
      </div>
    )
  }

  return (
    <div className="space-y-3 overflow-hidden">
      {/* Metrics bar — only when backtest result exists */}
      {result && (
        <div className="grid grid-cols-3 gap-x-4 gap-y-2 rounded-lg border border-border/70 bg-card/60 px-3 py-2.5 sm:grid-cols-5 lg:grid-cols-9">
          <StatCell label={t("backtests.totalReturn")} value={pct(totalReturn)} color={totalReturn >= 0 ? "text-emerald-400" : "text-red-400"} />
          <StatCell label={t("strategies.studio.annualReturn")} value={pct(annualReturn)} color={annualReturn >= 0 ? "text-emerald-400" : "text-red-400"} />
          <StatCell label={t("backtests.maxDrawdown")} value={pct(maxDD)} color="text-red-400" />
          <StatCell label={t("backtests.sharpeRatio")} value={Number.isFinite(sharpe) ? sharpe.toFixed(2) : "—"} />
          <StatCell label={t("backtests.winRate")} value={pct(winRate)} />
          <StatCell label={t("backtests.profitFactor")} value={Number.isFinite(profitFactor) ? profitFactor.toFixed(2) : "—"} />
          <StatCell label={t("backtests.totalTrades")} value={String(totalTrades)} />
          <StatCell label={t("strategies.studio.calmar")} value={Number.isFinite(calmar) ? calmar.toFixed(2) : "—"} />
          <StatCell label={t("strategies.studio.sortino")} value={Number.isFinite(sortino) ? sortino.toFixed(2) : "—"} />
        </div>
      )}

      {/* Candlestick chart — always visible when symbol exists */}
      <Card className="overflow-hidden border-border/80 bg-card/95 shadow-[0_0_0_1px_rgba(255,255,255,0.02)]">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="text-sm">
              {chartSymbol || strategyLabel}
              <span className="ml-2 text-xs text-muted-foreground font-normal">{chartInterval}</span>
            </CardTitle>
            <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
              <span className="text-emerald-300">↑ {t("strategies.studio.longEntry")}</span>
              <span className="text-emerald-200">□ {t("strategies.studio.longExit")}</span>
              <span className="text-red-300">↓ {t("strategies.studio.shortEntry")}</span>
              <span className="text-rose-200">□ {t("strategies.studio.shortExit")}</span>
            </div>
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {ALL_TIMEFRAMES.map((tf) => (
              <button
                key={tf.value}
                type="button"
                onClick={() => setChartTimeframe(tf.value === defaultInterval ? "" : tf.value)}
                className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors ${
                  chartInterval === tf.value
                    ? "bg-primary/15 text-primary border border-primary/30"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground border border-transparent"
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {selectedTrade && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 rounded-md border border-border/60 bg-background/40 px-3 py-2 text-xs">
              <Badge variant={selectedTrade.side === "long" ? "success" : "destructive"} className="text-[10px]">
                {selectedTrade.side === "long" ? t("strategies.studio.longEntry") : t("strategies.studio.shortEntry")}
              </Badge>
              <span className="font-mono text-muted-foreground">{new Date(selectedTrade.entryTime).toLocaleString()} → {new Date(selectedTrade.exitTime).toLocaleString()}</span>
              <span className="font-mono">{selectedTrade.entryPrice.toFixed(2)} → {selectedTrade.exitPrice.toFixed(2)}</span>
              <span className={`font-mono font-semibold ${selectedTrade.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                PnL {selectedTrade.pnl.toFixed(2)}
              </span>
              <span className="font-mono text-muted-foreground">Qty {selectedTrade.quantity.toFixed(4)}</span>
            </div>
          )}

          {!shouldShowPriceChart ? (
            <div className="flex h-[380px] items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
              {t("strategies.studio.chartUnavailable")}
            </div>
          ) : klineHistory.length === 0 && isLoadingKlines ? (
            <Skeleton className="h-[380px] w-full rounded-lg" />
          ) : klineHistory.length === 0 ? (
            <div className="flex h-[380px] items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
              {t("strategies.studio.noKlines")}
            </div>
          ) : (
            <div className="h-[380px] w-full">
              <CandlestickChart
                data={klineHistory}
                interval={chartInterval}
                markers={chartMarkers}
                onLoadMore={handleLoadMoreKlines}
                isLoadingMore={isLoadingKlines}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Below sections only render when backtest result exists */}
      {result && (<>
      {/* Equity curve */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">{t("strategies.studio.equityCurve")}</CardTitle>
          <p className="text-[11px] text-muted-foreground">{t("strategies.studio.equityCurveHint")}</p>
        </CardHeader>
        <CardContent>
          <CurveChart
            curve={equityCurve}
            baselineCurve={buyHoldCurve}
            baselineLabel="Buy & Hold"
            emptyLabel="—"
            height={220}
          />
        </CardContent>
      </Card>

      <div className="grid gap-3 xl:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t("strategies.studio.monthlyReturns")}</CardTitle>
          </CardHeader>
          <CardContent>
            <MonthlyReturnsHeatmap
              curve={equityCurve}
              startDate={result?.result?.start_date}
              endDate={result?.result?.end_date}
              emptyLabel={t("strategies.studio.noMonthlyReturns")}
              positiveLabel={t("strategies.studio.positiveReturns")}
              negativeLabel={t("strategies.studio.negativeReturns")}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t("strategies.studio.tradeDistribution")}</CardTitle>
          </CardHeader>
          <CardContent>
            <TradeDistribution
              trades={trades}
              emptyLabel={t("strategies.studio.noTradeDistribution")}
              rangeLabel={t("strategies.studio.tradeBuckets")}
            />
          </CardContent>
        </Card>
      </div>

      {/* Trade records + Position records */}
      <div className="grid gap-3 xl:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t("strategies.studio.tradeRecords")}</CardTitle>
          </CardHeader>
          <CardContent>
            {tradeActions.length === 0 ? (
              <p className="py-6 text-center text-xs text-muted-foreground">{t("strategies.studio.noTrades")}</p>
            ) : (
              <div className="max-h-[320px] overflow-auto">
                <table className="w-full text-[11px]">
                  <thead className="sticky top-0 bg-card text-muted-foreground">
                    <tr className="border-b border-border/60">
                      <th className="px-2 py-1.5 text-left font-medium">{t("strategies.trades.action")}</th>
                      <th className="px-2 py-1.5 text-left font-medium">{t("strategies.trades.side")}</th>
                      <th className="px-2 py-1.5 text-left font-medium">{t("strategies.trades.time")}</th>
                      <th className="px-2 py-1.5 text-right font-medium">{t("strategies.trades.price")}</th>
                      <th className="px-2 py-1.5 text-right font-medium">{t("strategies.trades.qty")}</th>
                      <th className="px-2 py-1.5 text-right font-medium">{t("strategies.trades.pnl")}</th>
                      <th className="px-2 py-1.5 text-right font-medium">{t("strategies.trades.returnPct")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tradeActions.slice(0, 200).map((action) => {
                      const isOpen = action.type === "open"
                      const actionLabel = isOpen
                        ? t("strategies.trades.open")
                        : t("strategies.trades.close")
                      return (
                        <tr
                          key={action.id}
                          className="border-b border-border/40 transition-colors hover:bg-muted/40"
                        >
                          <td className="px-2 py-1.5">
                            <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold ${isOpen ? "bg-sky-500/15 text-sky-400" : "bg-amber-500/15 text-amber-400"}`}>
                              {actionLabel}
                            </span>
                          </td>
                          <td className="px-2 py-1.5">
                            <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold ${action.side === "long" ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"}`}>
                              {action.side === "long" ? "LONG" : "SHORT"}
                            </span>
                          </td>
                          <td className="whitespace-nowrap px-2 py-1.5 font-mono text-muted-foreground">
                            {new Date(action.time).toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                          </td>
                          <td className="px-2 py-1.5 text-right font-mono">{action.price.toFixed(2)}</td>
                          <td className="px-2 py-1.5 text-right font-mono text-muted-foreground">{action.quantity.toFixed(4)}</td>
                          <td className="px-2 py-1.5 text-right font-mono font-semibold">
                            {action.pnl != null ? (
                              <span className={action.pnl >= 0 ? "text-emerald-400" : "text-red-400"}>
                                {action.pnl >= 0 ? "+" : ""}{action.pnl.toFixed(2)}
                              </span>
                            ) : (
                              <span className="text-muted-foreground/50">—</span>
                            )}
                          </td>
                          <td className="px-2 py-1.5 text-right font-mono">
                            {action.returnPct != null ? (
                              <span className={action.returnPct >= 0 ? "text-emerald-400" : "text-red-400"}>
                                {action.returnPct >= 0 ? "+" : ""}{action.returnPct.toFixed(2)}%
                              </span>
                            ) : (
                              <span className="text-muted-foreground/50">—</span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t("strategies.studio.positionRecords")}</CardTitle>
          </CardHeader>
          <CardContent>
            {positionRecords.length === 0 ? (
              <p className="py-6 text-center text-xs text-muted-foreground">{t("strategies.studio.noPositions")}</p>
            ) : (
              <div className="max-h-[320px] overflow-auto">
                <table className="w-full text-[10px]">
                  <thead className="sticky top-0 bg-card text-muted-foreground">
                    <tr className="border-b border-border/60">
                      <th className="whitespace-nowrap px-1.5 py-1 text-left font-medium">{t("strategies.trades.side")}</th>
                      <th className="whitespace-nowrap px-1.5 py-1 text-left font-medium">{t("strategies.trades.entryTime")}</th>
                      <th className="whitespace-nowrap px-1.5 py-1 text-left font-medium">{t("strategies.trades.exitTime")}</th>
                      <th className="whitespace-nowrap px-1.5 py-1 text-right font-medium">{t("strategies.trades.avgEntry")}</th>
                      <th className="whitespace-nowrap px-1.5 py-1 text-right font-medium">{t("strategies.trades.exitPrice")}</th>
                      <th className="whitespace-nowrap px-1.5 py-1 text-right font-medium">{t("strategies.trades.qty")}</th>
                      <th className="whitespace-nowrap px-1.5 py-1 text-right font-medium">{t("strategies.trades.realizedPnl")}</th>
                      <th className="whitespace-nowrap px-1.5 py-1 text-right font-medium">{t("strategies.trades.returnPct")}</th>
                      <th className="whitespace-nowrap px-1.5 py-1 text-right font-medium">{t("strategies.trades.holdingTime")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positionRecords.map((pos) => {
                      const fmtTime = (ts: number) => {
                        const d = new Date(ts)
                        const mm = String(d.getMonth() + 1).padStart(2, "0")
                        const dd = String(d.getDate()).padStart(2, "0")
                        const hh = String(d.getHours()).padStart(2, "0")
                        const mi = String(d.getMinutes()).padStart(2, "0")
                        return `${mm}/${dd} ${hh}:${mi}`
                      }
                      return (
                        <tr key={pos.id} className="border-b border-border/40 transition-colors hover:bg-muted/40">
                          <td className="px-1.5 py-1">
                            <span className={`inline-block rounded px-1 py-0.5 text-[9px] font-semibold ${pos.side === "long" ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"}`}>
                              {pos.side === "long" ? "LONG" : "SHORT"}
                            </span>
                          </td>
                          <td className="whitespace-nowrap px-1.5 py-1 font-mono text-muted-foreground">
                            {fmtTime(pos.entryTime)}
                          </td>
                          <td className="whitespace-nowrap px-1.5 py-1 font-mono text-muted-foreground">
                            {fmtTime(pos.exitTime)}
                          </td>
                          <td className="px-1.5 py-1 text-right font-mono">{pos.avgEntry.toFixed(2)}</td>
                          <td className="px-1.5 py-1 text-right font-mono">{pos.exitPrice.toFixed(2)}</td>
                          <td className="px-1.5 py-1 text-right font-mono text-muted-foreground">{pos.totalQty.toFixed(4)}</td>
                          <td className={`whitespace-nowrap px-1.5 py-1 text-right font-mono font-semibold ${pos.realizedPnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                            {pos.realizedPnl >= 0 ? "+" : ""}{pos.realizedPnl.toFixed(2)}
                          </td>
                          <td className={`whitespace-nowrap px-1.5 py-1 text-right font-mono ${pos.returnPct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                            {pos.returnPct >= 0 ? "+" : ""}{pos.returnPct.toFixed(2)}%
                          </td>
                          <td className="whitespace-nowrap px-1.5 py-1 text-right font-mono text-muted-foreground">{pos.holdingTime}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
      </>)}
    </div>
  )
}
