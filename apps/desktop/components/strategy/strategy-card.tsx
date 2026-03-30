"use client"

import { useState, useMemo } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  ArrowRight,
  FlaskConical,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Trash2,
  Circle,
  Clock,
  Eye,
  Square,
  Loader2,
} from "lucide-react"
import { useRouter } from "next/navigation"
import { useI18n } from "@/components/i18n/use-i18n"
import { CurveChart } from "@/components/strategy/shared-charts"
import type {
  StrategyData,
  BacktestData,
  StrategyDeploymentData,
  PaperEquityPoint,
  PaperAccountData,
} from "@/lib/api-client"
import { cn } from "@/lib/utils"

export interface StrategyCardProps {
  strategy: StrategyData
  latestBacktest?: BacktestData | null
  deployment?: StrategyDeploymentData | null
  liveEquity?: PaperEquityPoint[]
  livePnl?: { realized: number; unrealized: number } | null
  liveAccount?: PaperAccountData | null
  onDelete?: (id: string) => void
  onStop?: (strategyId: string) => Promise<void>
}

function directionKey(direction: StrategyData["direction"]): string {
  if (direction === "short_only") return "strategies.card.dirShort"
  if (direction === "neutral") return "strategies.card.dirNeutral"
  return "strategies.card.dirLong"
}

function extractMetrics(bt: BacktestData) {
  const m = bt.result?.metrics
  const sharpe = m?.sharpe_ratio ?? bt.sharpe_ratio ?? 0
  const ret = m?.total_return ?? bt.total_return ?? 0
  const dd = m?.max_drawdown ?? bt.max_drawdown ?? 0
  return { sharpe, ret, dd }
}

function extractEquityCurve(bt: BacktestData): number[] {
  if (Array.isArray(bt.result?.equity_curve)) return bt.result.equity_curve ?? []
  if (Array.isArray(bt.equity_curve)) return bt.equity_curve ?? []
  return []
}

function formatDuration(ms: number): string {
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m`
  const hr = Math.floor(min / 60)
  const remMin = min % 60
  if (hr < 24) return remMin > 0 ? `${hr}h ${remMin}m` : `${hr}h`
  const days = Math.floor(hr / 24)
  const remHr = hr % 24
  return remHr > 0 ? `${days}d ${remHr}h` : `${days}d`
}

export function StrategyCard({
  strategy,
  latestBacktest,
  deployment,
  liveEquity,
  liveAccount,
  onDelete,
  onStop,
}: StrategyCardProps) {
  const router = useRouter()
  const { t } = useI18n()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [confirmStop, setConfirmStop] = useState(false)
  const [stopping, setStopping] = useState(false)
  const studioPath = `/strategies/${strategy.id}/studio`

  const isRunning = deployment?.status === "running"
  const isStopped = deployment?.status === "stopped"

  const runtimeMs = useMemo(() => {
    if (!deployment?.created_at) return 0
    return Date.now() - new Date(deployment.created_at).getTime()
  }, [deployment?.created_at])

  const liveEquityCurve = useMemo(() => {
    if (!liveEquity || liveEquity.length < 2) {
      if (liveAccount?.equity && liveAccount.equity > 0 && liveEquity && liveEquity.length === 1) {
        return [liveEquity[0].equity, liveAccount.equity]
      }
      return []
    }
    const curve = liveEquity.map((p) => p.equity)
    if (liveAccount?.equity && liveAccount.equity > 0) {
      curve.push(liveAccount.equity)
    }
    return curve
  }, [liveEquity, liveAccount?.equity])

  const accountMetrics = useMemo(() => {
    const initialBalance = liveAccount?.initial_balance ?? 0
    const currentEquity = liveAccount?.equity ?? 0
    const pnlAmount = currentEquity - initialBalance
    const pnlPercent = initialBalance > 0 ? (pnlAmount / initialBalance) * 100 : 0
    return { initialBalance, currentEquity, pnlAmount, pnlPercent, hasData: !!liveAccount }
  }, [liveAccount])

  const DirectionIcon =
    strategy.direction === "short_only"
      ? TrendingDown
      : strategy.direction === "neutral"
        ? BarChart3
        : TrendingUp

  const { sharpe, ret, dd } = latestBacktest
    ? extractMetrics(latestBacktest)
    : { sharpe: 0, ret: 0, dd: 0 }
  const backtestEquityCurve = latestBacktest ? extractEquityCurve(latestBacktest) : []

  const statusLabel = isRunning
    ? t("strategies.card.running")
    : isStopped
      ? t("strategies.card.stopped")
      : latestBacktest
        ? t("strategies.card.backtested")
        : t("strategies.card.draft")

  const handleStop = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirmStop) {
      setConfirmStop(true)
      return
    }
    if (!onStop) return
    setStopping(true)
    try {
      await onStop(strategy.id)
    } finally {
      setStopping(false)
      setConfirmStop(false)
    }
  }

  return (
    <Card
      className={cn(
        "transition-all cursor-pointer group bg-card",
        isRunning
          ? "border-emerald-500/50 hover:border-emerald-400/70 shadow-[0_0_12px_rgba(16,185,129,0.08)]"
          : "border-border hover:border-primary/40",
      )}
      onClick={() => router.push(studioPath)}
    >
      <CardContent className="p-4 space-y-3">
        {/* Header: name + status */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <h3 className="font-medium text-sm truncate">{strategy.name}</h3>
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
              {strategy.description ||
                `${strategy.type} on ${strategy.symbols?.join(", ") ?? ""}`}
            </p>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {strategy.source === "template" && (
              <Badge variant="secondary" className="text-[10px]">
                {t("strategies.card.template")}
              </Badge>
            )}
            {isRunning ? (
              <Badge className="text-[10px] gap-1 bg-emerald-600 hover:bg-emerald-600">
                <Circle className="h-2 w-2 fill-current animate-pulse" />
                {statusLabel}
              </Badge>
            ) : isStopped ? (
              <Badge variant="secondary" className="text-[10px] gap-1 text-amber-400">
                <Circle className="h-2 w-2 fill-current" />
                {statusLabel}
              </Badge>
            ) : (
              <Badge variant="outline" className="text-[10px]">
                {statusLabel}
              </Badge>
            )}
          </div>
        </div>

        {/* Running: capital metrics panel */}
        {isRunning && (
          <div className="rounded-md bg-emerald-500/5 border border-emerald-500/20 px-3 py-2 space-y-1.5">
            {/* Row 1: runtime + version */}
            <div className="flex items-center gap-3 text-[11px]">
              <span className="flex items-center gap-1 text-emerald-400">
                <Clock className="h-3 w-3" />
                {t("strategies.card.runtimeLabel")}: {runtimeMs > 0 ? formatDuration(runtimeMs) : "—"}
              </span>
              <span className="text-muted-foreground">v{deployment?.strategy_version ?? strategy.version ?? 1}</span>
            </div>

            {/* Row 2: capital grid — initial / current / pnl / return */}
            {accountMetrics.hasData && (
              <div className="grid grid-cols-4 gap-1.5 pt-0.5">
                <div>
                  <div className="text-[9px] text-muted-foreground leading-tight">{t("strategies.card.initialCapital")}</div>
                  <div className="text-[11px] font-mono font-medium">{accountMetrics.initialBalance.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</div>
                </div>
                <div>
                  <div className="text-[9px] text-muted-foreground leading-tight">{t("strategies.card.currentCapital")}</div>
                  <div className="text-[11px] font-mono font-medium">{accountMetrics.currentEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                </div>
                <div>
                  <div className="text-[9px] text-muted-foreground leading-tight">{t("strategies.card.pnlAmount")}</div>
                  <div className={cn(
                    "text-[11px] font-mono font-medium",
                    accountMetrics.pnlAmount >= 0 ? "text-emerald-400" : "text-red-400",
                  )}>
                    {accountMetrics.pnlAmount >= 0 ? "+" : ""}{accountMetrics.pnlAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>
                <div>
                  <div className="text-[9px] text-muted-foreground leading-tight">{t("strategies.card.pnlPercent")}</div>
                  <div className={cn(
                    "text-[11px] font-mono font-medium",
                    accountMetrics.pnlPercent >= 0 ? "text-emerald-400" : "text-red-400",
                  )}>
                    {accountMetrics.pnlPercent >= 0 ? "+" : ""}{accountMetrics.pnlPercent.toFixed(2)}%
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tags row */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <Badge variant="outline" className="text-[10px] gap-0.5">
            <FlaskConical className="h-3 w-3 opacity-70" />
            {strategy.type}
          </Badge>
          <Badge variant="outline" className="text-[10px]">
            {strategy.interval}
          </Badge>
          <Badge variant="outline" className="text-[10px] gap-0.5">
            <DirectionIcon className="h-3 w-3" />
            {t(directionKey(strategy.direction) as Parameters<typeof t>[0])}
          </Badge>
          <Badge variant="outline" className="text-[10px]">
            v{strategy.version ?? 1}
          </Badge>
        </div>

        {/* Curve + metrics section — depends on running state */}
        {isRunning ? (
          // Running: show live equity from paper account
          liveEquityCurve.length >= 2 ? (
            <div className="pt-1">
              <div className="text-[10px] text-emerald-400/70 mb-1">{t("strategies.card.liveEquity")}</div>
              <CurveChart curve={liveEquityCurve} height={90} />
            </div>
          ) : (
            <div className="text-[10px] text-muted-foreground text-center py-3">
              {t("strategies.card.noTradesYet")}
            </div>
          )
        ) : latestBacktest ? (
          // Not running: show backtest metrics + curve
          <>
            <div className="grid grid-cols-3 gap-2 pt-1">
              <div className="text-center">
                <div className="text-[10px] text-muted-foreground">{t("strategies.card.sharpe")}</div>
                <div className="text-xs font-mono font-medium">{sharpe.toFixed(2)}</div>
              </div>
              <div className="text-center">
                <div className="text-[10px] text-muted-foreground">{t("strategies.card.return")}</div>
                <div className={cn("text-xs font-mono font-medium", ret >= 0 ? "text-emerald-400" : "text-red-400")}>
                  {ret >= 0 ? "+" : ""}{(ret * 100).toFixed(1)}%
                </div>
              </div>
              <div className="text-center">
                <div className="text-[10px] text-muted-foreground">{t("strategies.card.maxDD")}</div>
                <div className="text-xs font-mono font-medium text-red-400">{(dd * 100).toFixed(1)}%</div>
              </div>
            </div>
            {backtestEquityCurve.length >= 2 && (
              <div className="pt-1">
                <CurveChart curve={backtestEquityCurve} height={90} />
              </div>
            )}
          </>
        ) : (
          <div className="text-[10px] text-muted-foreground text-center py-2">
            {t("strategies.hub.noBacktestYet")}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 pt-1">
          {isRunning ? (
            <>
              <Button
                size="sm"
                variant="outline"
                className="flex-1 text-xs h-7 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10"
                onClick={(e) => {
                  e.stopPropagation()
                  router.push(`/paper?account=${deployment?.account_id ?? ""}`)
                }}
              >
                <Eye className="h-3 w-3 mr-1" />
                {t("strategies.card.viewPaper")}
              </Button>
              {/* Stop button */}
              {onStop && (
                confirmStop ? (
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="destructive"
                      className="text-xs h-7 px-2"
                      disabled={stopping}
                      onClick={handleStop}
                    >
                      {stopping ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        t("strategies.card.stopStrategy")
                      )}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-xs h-7 px-1.5"
                      onClick={(e) => {
                        e.stopPropagation()
                        setConfirmStop(false)
                      }}
                    >
                      ✕
                    </Button>
                  </div>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-xs h-7 px-2 border-red-500/30 text-red-400 hover:bg-red-500/10"
                    onClick={handleStop}
                    title={t("strategies.card.stopStrategy")}
                  >
                    <Square className="h-3 w-3" />
                  </Button>
                )
              )}
            </>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="flex-1 text-xs h-7"
              onClick={(e) => {
                e.stopPropagation()
                router.push(studioPath)
              }}
            >
              {t("strategies.hub.openStudio")}
              <ArrowRight className="h-3 w-3 ml-1" />
            </Button>
          )}
          {onDelete && !isRunning && (
            confirmDelete ? (
              <>
                <Button
                  size="sm"
                  variant="destructive"
                  className="text-xs h-7 px-2"
                  onClick={(e) => {
                    e.stopPropagation()
                    onDelete(strategy.id)
                  }}
                >
                  {t("strategies.hub.deleteStrategy")}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-xs h-7 px-2"
                  onClick={(e) => {
                    e.stopPropagation()
                    setConfirmDelete(false)
                  }}
                >
                  ✕
                </Button>
              </>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                onClick={(e) => {
                  e.stopPropagation()
                  setConfirmDelete(true)
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )
          )}
        </div>
      </CardContent>
    </Card>
  )
}
