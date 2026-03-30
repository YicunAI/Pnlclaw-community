"use client"

import { useEffect, useState } from "react"
import { getPositions, type TradingPosition } from "@/lib/api-client"
import { useI18n } from "@/components/i18n/use-i18n"
import { cn } from "@/lib/utils"

interface PositionPanelProps {
  wsPositions: TradingPosition[]
}

export function PositionPanel({ wsPositions }: PositionPanelProps) {
  const { t } = useI18n()
  const [positions, setPositions] = useState<TradingPosition[]>([])

  useEffect(() => {
    getPositions().then((res) => {
      if (res.data) setPositions(res.data)
    })
  }, [])

  const merged = [...wsPositions]
  for (const p of positions) {
    if (!merged.find((w) => w.symbol === p.symbol)) merged.push(p)
  }

  return (
    <div className="space-y-2">
      {merged.length === 0 && (
        <p className="text-center text-sm text-muted-foreground py-6">{t("trading.noPositions")}</p>
      )}
      {merged.map((p) => (
        <div key={p.symbol} className="rounded-lg border border-border p-3 space-y-1">
          <div className="flex items-center justify-between">
            <span className="font-mono text-sm font-medium">{p.symbol}</span>
            <span className={cn(
              "text-xs font-medium uppercase",
              p.side === "buy" ? "text-green-500" : "text-red-500"
            )}>
              {p.side === "buy" ? t("trading.long") : t("trading.short")}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
            <div>
              <span>{t("trading.qty")}: </span>
              <span className="font-mono text-foreground">{p.quantity}</span>
            </div>
            <div>
              <span>{t("trading.entry")}: </span>
              <span className="font-mono text-foreground">{p.avg_entry_price.toFixed(2)}</span>
            </div>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">{t("trading.unrealizedPnl")}</span>
            <span className={cn(
              "font-mono font-medium",
              p.unrealized_pnl >= 0 ? "text-green-500" : "text-red-500"
            )}>
              {p.unrealized_pnl >= 0 ? "+" : ""}{p.unrealized_pnl.toFixed(2)}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
