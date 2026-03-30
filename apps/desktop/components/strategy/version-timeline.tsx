"use client"

import { useCallback, useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import { getStrategyVersions } from "@/lib/api-client"
import { useI18n } from "@/components/i18n/use-i18n"
import { History, ChevronDown, RotateCcw } from "lucide-react"

interface BacktestSummary {
  id: string
  total_return: number
  sharpe_ratio: number
  max_drawdown: number
  win_rate: number
  trades_count: number
  created_at: number
}

interface VersionSnapshot {
  id: string
  strategy_id: string
  version: number
  config_snapshot: Record<string, unknown>
  note: string
  created_at: number
  backtests?: BacktestSummary[]
}

export interface VersionTimelineProps {
  strategyId: string
  currentVersion: number
  onRevert?: (config: Record<string, unknown>, version: number) => void
  refreshKey?: number
}

function formatTime(ms: number): string {
  const d = new Date(ms)
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`
}

export function VersionTimeline({
  strategyId,
  currentVersion,
  onRevert,
  refreshKey,
}: VersionTimelineProps) {
  const { t } = useI18n()
  const [versions, setVersions] = useState<VersionSnapshot[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getStrategyVersions(strategyId)
      if (res.data) setVersions(res.data as unknown as VersionSnapshot[])
    } finally {
      setLoading(false)
    }
  }, [strategyId])

  useEffect(() => {
    void load()
  }, [load, refreshKey])

  if (versions.length === 0) return null

  return (
    <div className="border-b border-border/60">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors hover:bg-muted/40"
      >
        <History className="h-3 w-3 text-muted-foreground" />
        <span className="font-medium text-muted-foreground">
          {t("strategies.studio.versionHistory") || "Version History"}
        </span>
        <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
          {versions.length}
        </span>
        <ChevronDown
          className={cn(
            "ml-auto h-3 w-3 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div className="max-h-48 overflow-y-auto px-3 pb-2">
          <div className="space-y-1">
            {versions.map((v) => {
              const isCurrent = v.version === currentVersion
              const best = v.backtests?.length
                ? v.backtests.reduce((a, b) => (a.total_return > b.total_return ? a : b))
                : null

              return (
                <div
                  key={v.id}
                  role={!isCurrent && onRevert ? "button" : undefined}
                  tabIndex={!isCurrent && onRevert ? 0 : undefined}
                  onClick={!isCurrent && onRevert ? () => onRevert(v.config_snapshot, v.version) : undefined}
                  onKeyDown={!isCurrent && onRevert ? (e) => { if (e.key === "Enter") onRevert(v.config_snapshot, v.version) } : undefined}
                  className={cn(
                    "group flex items-start gap-2 rounded-lg px-2 py-1.5 text-xs",
                    isCurrent
                      ? "border border-primary/20 bg-primary/5"
                      : "cursor-pointer hover:bg-muted/40",
                  )}
                >
                  <div className="flex flex-col items-center pt-0.5">
                    <div
                      className={cn(
                        "flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold",
                        isCurrent
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground",
                      )}
                    >
                      {v.version}
                    </div>
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate font-medium text-foreground">
                        {v.note || `v${v.version}`}
                      </span>
                      {isCurrent && (
                        <span className="shrink-0 rounded bg-primary/10 px-1 py-0.5 text-[9px] font-medium text-primary">
                          {t("strategies.ai.stepsCurrent") || "Current"}
                        </span>
                      )}
                      <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
                        {formatTime(v.created_at)}
                      </span>
                    </div>

                    {best && (
                      <div className="mt-0.5 flex gap-2 text-[10px] text-muted-foreground">
                        <span className={best.total_return >= 0 ? "text-emerald-400" : "text-red-400"}>
                          Return {formatPct(best.total_return)}
                        </span>
                        <span>Sharpe {best.sharpe_ratio.toFixed(2)}</span>
                        <span>DD {formatPct(best.max_drawdown)}</span>
                        <span>WR {formatPct(best.win_rate)}</span>
                      </div>
                    )}
                  </div>

                  {!isCurrent && onRevert && (
                    <div className="hidden shrink-0 items-center pt-0.5 text-[9px] text-muted-foreground group-hover:flex">
                      <RotateCcw className="mr-0.5 h-2.5 w-2.5" />
                      {t("strategies.studio.loadVersion") || "Load"}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          {loading && (
            <div className="py-2 text-center text-[10px] text-muted-foreground">Loading...</div>
          )}
        </div>
      )}
    </div>
  )
}
