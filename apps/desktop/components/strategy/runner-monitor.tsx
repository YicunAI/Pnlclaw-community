"use client"

import { useMemo } from "react"
import { Activity, ArrowDown, ArrowUp, BarChart3, AlertTriangle, Wifi, WifiOff, TrendingUp } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { useI18n } from "@/components/i18n/use-i18n"
import { usePaperWS } from "@/lib/use-paper-ws"

interface RunnerMonitorPanelProps {
  strategyId: string
  accountId: string | null
  deploymentId?: string | null
  compact?: boolean
  maxSignals?: number
}

export function RunnerMonitorPanel({
  strategyId,
  accountId,
  deploymentId,
  compact = false,
  maxSignals = 20,
}: RunnerMonitorPanelProps) {
  const { t } = useI18n()
  const { connected, signals: wsSignals, slotStatus } = usePaperWS(accountId)

  const relevantSignals = useMemo(() => {
    return wsSignals
      .filter((s) => s.strategy_id === strategyId || s.deployment_id === deploymentId)
      .slice(0, maxSignals)
  }, [wsSignals, strategyId, deploymentId, maxSignals])

  const allSignals = useMemo(() => {
    return relevantSignals.map((s) => {
      const sig = typeof s.signal === "object" ? s.signal : { side: "", reason: String(s.signal) }
      return {
        ts: s.ts,
        side: sig.side || "",
        reason: sig.reason || "",
        strength: sig.strength,
        price: s.price ?? 0,
        symbol: s.symbol ?? "",
      }
    })
  }, [relevantSignals])

  if (!slotStatus && !connected) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
        <Activity className="h-4 w-4 animate-pulse" />
        {t("runner.loading")}
      </div>
    )
  }

  if (!slotStatus) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
        <AlertTriangle className="h-4 w-4" />
        {t("runner.noActiveDeployment")}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 text-xs">
      {/* Status bar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-green-500" />
          </span>
          <span className="font-medium text-foreground">{t("runner.running")}</span>
        </div>

        <Badge variant="outline" className="gap-1 text-[10px]">
          {connected ? <Wifi className="h-3 w-3 text-green-500" /> : <WifiOff className="h-3 w-3 text-red-400" />}
          {connected ? "WS" : t("runner.wsDisconnected")}
        </Badge>

        <span className="text-muted-foreground">
          {slotStatus.symbol} / {slotStatus.interval}
        </span>
      </div>

      {/* Counters */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <CounterCard
          label={t("runner.barCount")}
          value={slotStatus.bar_count}
          icon={<BarChart3 className="h-3.5 w-3.5 text-blue-400" />}
        />
        <CounterCard
          label={t("runner.signalCount")}
          value={slotStatus.signals_emitted}
          icon={<TrendingUp className="h-3.5 w-3.5 text-yellow-400" />}
        />
        <CounterCard
          label={t("runner.orderCount")}
          value={slotStatus.orders_placed}
          icon={<Activity className="h-3.5 w-3.5 text-green-400" />}
        />
        <CounterCard
          label={t("runner.position")}
          value={slotStatus.position}
          icon={
            slotStatus.position === "long" ? (
              <ArrowUp className="h-3.5 w-3.5 text-green-400" />
            ) : slotStatus.position === "short" ? (
              <ArrowDown className="h-3.5 w-3.5 text-red-400" />
            ) : (
              <Activity className="h-3.5 w-3.5 text-muted-foreground" />
            )
          }
        />
      </div>

      {/* Signal log */}
      {!compact && (
        <div className="mt-1">
          <div className="mb-1.5 font-medium text-muted-foreground">{t("runner.signalLog")}</div>
          {allSignals.length === 0 ? (
            <div className="py-4 text-center text-muted-foreground">{t("runner.noSignals")}</div>
          ) : (
            <div className="max-h-48 overflow-y-auto rounded border border-border/40 bg-background/50">
              <table className="w-full text-[11px]">
                <thead className="sticky top-0 bg-muted/80 backdrop-blur">
                  <tr className="text-left text-muted-foreground">
                    <th className="px-2 py-1">{t("runner.time")}</th>
                    <th className="px-2 py-1">{t("runner.side")}</th>
                    <th className="px-2 py-1">{t("runner.price")}</th>
                    <th className="px-2 py-1">{t("runner.reason")}</th>
                  </tr>
                </thead>
                <tbody>
                  {allSignals.map((sig, i) => (
                    <tr key={`${sig.ts}-${i}`} className="border-t border-border/20 hover:bg-muted/30">
                      <td className="whitespace-nowrap px-2 py-1 text-muted-foreground">
                        {new Date(sig.ts).toLocaleTimeString()}
                      </td>
                      <td className="px-2 py-1">
                        <span className={sig.side.toLowerCase().includes("buy") ? "text-green-400" : "text-red-400"}>
                          {sig.side.toLowerCase().includes("buy") ? "BUY" : "SELL"}
                        </span>
                      </td>
                      <td className="px-2 py-1 font-mono">
                        {typeof sig.price === "number" ? sig.price.toLocaleString() : "-"}
                      </td>
                      <td className="max-w-[200px] truncate px-2 py-1 text-muted-foreground">
                        {sig.reason || "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function CounterCard({ label, value, icon }: { label: string; value: string | number; icon: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border/40 bg-muted/30 px-2.5 py-1.5">
      {icon}
      <div className="flex flex-col">
        <span className="text-[10px] text-muted-foreground">{label}</span>
        <span className="font-mono font-medium text-foreground">{String(value)}</span>
      </div>
    </div>
  )
}
