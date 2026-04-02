"use client"

import React from "react"
import { RequireAuth } from "@/components/auth/require-auth"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Wifi,
  WifiOff,
  TrendingUp,
  TrendingDown,
  FlaskConical,
  Wallet,
  Landmark,
} from "lucide-react"
import {
  useHealth,
  useBacktestList,
  usePaperAccounts,
  useTradingModeData,
  useLiveBalances,
  useLivePositions,
} from "@/lib/hooks/use-api"
import type { BacktestData } from "@/lib/api-client"
import { useI18n } from "@/components/i18n/use-i18n"

function Sparkline({ curve }: { curve: number[] }) {
  if (curve.length < 2) return <span className="text-xs text-muted-foreground">—</span>
  const w = 110
  const h = 36
  const min = Math.min(...curve)
  const max = Math.max(...curve)
  const range = max - min || 1
  const pts = curve
    .map((v, i) => {
      const x = (i / (curve.length - 1)) * w
      const y = h - ((v - min) / range) * h
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")
  const isUp = curve[curve.length - 1] >= curve[0]
  const stroke = isUp ? "#22c55e" : "#ef4444"
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} style={{ display: "block" }}>
      <polyline points={pts} fill="none" stroke={stroke} strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

function StatusCard({
  label,
  value,
  ok,
}: {
  label: string
  value: string
  ok: boolean | null
}) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between p-4">
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-sm font-medium mt-1">{value}</p>
        </div>
        {ok === null ? (
          <Skeleton className="h-8 w-8 rounded-full" />
        ) : ok ? (
          <Wifi className="h-5 w-5 text-emerald-400" />
        ) : (
          <WifiOff className="h-5 w-5 text-red-400" />
        )}
      </CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const { locale, t } = useI18n()

  const { data: health } = useHealth()
  const { data: allBacktests, isLoading: btLoading } = useBacktestList()
  const { data: accounts, isLoading: accLoading } = usePaperAccounts()
  const { data: tradingMode } = useTradingModeData()

  const apiOk = health === undefined ? null : health ? health.status === "ok" : false
  const backtests = allBacktests ? allBacktests.slice(0, 5) : []
  const safeAccounts = accounts ?? []
  const isLive = tradingMode?.mode === "live"
  const loading = btLoading || accLoading

  const { data: liveBalances } = useLiveBalances(isLive)
  const { data: livePositions } = useLivePositions(isLive)

  const safeLiveBalances = liveBalances ?? []
  const safeLivePositions = livePositions ?? []

  const paperTotalPnl = safeAccounts.reduce(
    (sum, a) => sum + (a.realized_pnl ?? a.total_realized_pnl ?? 0) + (a.unrealized_pnl ?? 0),
    0
  )
  const paperTotalBalance = safeAccounts.reduce(
    (sum, a) => sum + (a.equity ?? (a.initial_balance + (a.total_realized_pnl ?? 0) - (a.total_fee ?? 0) + (a.unrealized_pnl ?? 0))),
    0
  )

  const liveTotalBalance = safeLiveBalances.reduce(
    (sum, b) => sum + (b.free ?? 0) + (b.locked ?? 0),
    0
  )
  const liveTotalPnl = safeLivePositions.reduce(
    (sum, p) => sum + (p.unrealized_pnl ?? 0) + (p.realized_pnl ?? 0),
    0
  )

  return (
    <RequireAuth>
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t("dashboard.title")}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t("dashboard.subtitle")}</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <StatusCard
          label={t("dashboard.apiServer")}
          value={
            apiOk === null
              ? t("dashboard.checking")
              : apiOk
                ? t("dashboard.connected")
                : t("dashboard.offline")
          }
          ok={apiOk}
        />
        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="text-xs text-muted-foreground">{t("dashboard.liveBalance")}</p>
              <p className="text-sm font-medium mt-1">
                {loading
                  ? "..."
                  : isLive
                  ? `$${liveTotalBalance.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                  : t("dashboard.offline")}
              </p>
            </div>
            <Landmark className="h-5 w-5 text-amber-400" />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="text-xs text-muted-foreground">{t("dashboard.livePnl")}</p>
              {loading ? (
                <p className="text-sm font-medium mt-1">...</p>
              ) : isLive ? (
                <p
                  className={`text-sm font-medium mt-1 ${
                    liveTotalPnl >= 0 ? "text-emerald-400" : "text-red-400"
                  }`}
                >
                  {liveTotalPnl >= 0 ? "+" : ""}${liveTotalPnl.toFixed(2)}
                </p>
              ) : (
                <p className="text-sm font-medium mt-1 text-muted-foreground">
                  {t("dashboard.offline")}
                </p>
              )}
            </div>
            {isLive ? (
              liveTotalPnl >= 0 ? (
                <TrendingUp className="h-5 w-5 text-emerald-400" />
              ) : (
                <TrendingDown className="h-5 w-5 text-red-400" />
              )
            ) : (
              <TrendingDown className="h-5 w-5 text-muted-foreground" />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="text-xs text-muted-foreground">{t("dashboard.backtests")}</p>
              <p className="text-sm font-medium mt-1">
                {loading ? "..." : backtests.length}
              </p>
            </div>
            <FlaskConical className="h-5 w-5 text-primary" />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="text-xs text-muted-foreground">{t("dashboard.paperBalance")}</p>
              <p className="text-sm font-medium mt-1">
                {loading ? "..." : `$${paperTotalBalance.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
              </p>
            </div>
            <Wallet className="h-5 w-5 text-primary" />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="text-xs text-muted-foreground">{t("dashboard.paperPnl")}</p>
              <p
                className={`text-sm font-medium mt-1 ${
                  paperTotalPnl >= 0 ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {loading
                  ? "..."
                  : `${paperTotalPnl >= 0 ? "+" : ""}$${paperTotalPnl.toFixed(2)}`}
              </p>
            </div>
            {paperTotalPnl >= 0 ? (
              <TrendingUp className="h-5 w-5 text-emerald-400" />
            ) : (
              <TrendingDown className="h-5 w-5 text-red-400" />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t("dashboard.recentBacktests")}</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : backtests.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                {t("dashboard.noBacktests")}
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("dashboard.strategy")}</TableHead>
                    <TableHead>{t("dashboard.return")}</TableHead>
                    <TableHead>{t("dashboard.sharpe")}</TableHead>
                    <TableHead className="w-[120px]">{t("dashboard.equityCurve") || "收益曲线"}</TableHead>
                    <TableHead>{t("dashboard.status")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {backtests.map((bt: BacktestData) => {
                    const curve: number[] = Array.isArray(bt.result?.equity_curve)
                      ? bt.result!.equity_curve!
                      : Array.isArray(bt.equity_curve)
                        ? bt.equity_curve
                        : []
                    return (
                    <TableRow key={bt.id}>
                      <TableCell className="font-medium text-xs">
                        {bt.strategy_name}
                      </TableCell>
                      <TableCell
                        className={`text-xs ${
                          bt.total_return >= 0
                            ? "text-emerald-400"
                            : "text-red-400"
                        }`}
                      >
                        {(bt.total_return * 100).toFixed(1)}%
                      </TableCell>
                      <TableCell className="text-xs">
                        {bt.sharpe_ratio?.toFixed(2) ?? "-"}
                      </TableCell>
                      <TableCell className="py-1">
                        {curve.length >= 2 ? (
                          <Sparkline curve={curve} />
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            bt.status === "completed" ? "success" : "secondary"
                          }
                        >
                          {bt.status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t("dashboard.paperAccounts")}</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                {[1, 2].map((i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : safeAccounts.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                {t("dashboard.noAccounts")}
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("dashboard.name")}</TableHead>
                    <TableHead>{t("dashboard.balance")}</TableHead>
                    <TableHead>{t("dashboard.pnl")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {safeAccounts.map((acc) => {
                    const pnl =
                      (acc.realized_pnl ?? acc.total_realized_pnl ?? 0) + (acc.unrealized_pnl ?? 0)
                    const equity = acc.equity ?? (acc.initial_balance + (acc.total_realized_pnl ?? 0) - (acc.total_fee ?? 0) + (acc.unrealized_pnl ?? 0))
                    return (
                      <TableRow key={acc.id}>
                        <TableCell className="font-medium text-xs">
                          {acc.name}
                        </TableCell>
                        <TableCell className="text-xs font-mono">
                          ${equity.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </TableCell>
                        <TableCell
                          className={`text-xs font-mono ${
                            pnl >= 0 ? "text-emerald-400" : "text-red-400"
                          }`}
                        >
                          {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

    </div>
    </RequireAuth>
  )
}
