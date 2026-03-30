"use client"

import React from "react"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { TrendingUp, TrendingDown } from "lucide-react"
import type { TickerData } from "@/lib/api-client"
import { useI18n } from "@/components/i18n/use-i18n"

interface TickerPanelProps {
  ticker: TickerData | null
  /** Override title label. Defaults to markets.ticker i18n key. */
  title?: string
}

export function TickerPanel({ ticker, title }: TickerPanelProps) {
  const { locale, t } = useI18n()

  return (
    <div>
      <h3 className="text-base font-semibold mb-3">{title ?? t("markets.ticker")}</h3>
      {!ticker ? (
        <div className="space-y-3">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-20" />
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-2xl font-bold font-mono">
            ${ticker.last_price?.toLocaleString(locale)}
          </div>
          <div className="flex items-center gap-2">
            {(ticker.change_24h_pct ?? 0) >= 0 ? (
              <TrendingUp className="h-4 w-4 text-emerald-400" />
            ) : (
              <TrendingDown className="h-4 w-4 text-red-400" />
            )}
            <Badge
              variant={
                (ticker.change_24h_pct ?? 0) >= 0 ? "success" : "destructive"
              }
            >
              {(ticker.change_24h_pct ?? 0) >= 0 ? "+" : ""}
              {(ticker.change_24h_pct ?? 0).toFixed(2)}%
            </Badge>
          </div>
          <div className="space-y-1 text-xs text-muted-foreground">
            <div className="flex justify-between">
              <span>{t("markets.high24h")}</span>
              <span className="text-foreground font-mono">
                {ticker.high_24h ? `$${ticker.high_24h.toLocaleString(locale)}` : "--"}
              </span>
            </div>
            <div className="flex justify-between">
              <span>{t("markets.low24h")}</span>
              <span className="text-foreground font-mono">
                {ticker.low_24h ? `$${ticker.low_24h.toLocaleString(locale)}` : "--"}
              </span>
            </div>
            <div className="flex justify-between">
              <span>{t("markets.volume24h")}</span>
              <span className="text-foreground font-mono">
                {ticker.quote_volume_24h
                  ? `${ticker.quote_volume_24h.toLocaleString(locale, { maximumFractionDigits: 0 })} USDT`
                  : `${ticker.volume_24h?.toLocaleString(locale)} (Base)`}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
