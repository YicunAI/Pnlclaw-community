"use client"

import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import { useI18n } from "@/components/i18n/use-i18n"

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8080"

interface FundingRateData {
  exchange: string
  symbol: string
  funding_rate: number
  mark_price: number
  index_price: number
  next_funding_time: number
  timestamp: number
}

function formatRate(rate: number): string {
  return `${(rate * 100).toFixed(4)}%`
}

function formatCountdown(nextFunding: number): string {
  const diff = nextFunding - Date.now()
  if (diff <= 0) return "Now"
  const h = Math.floor(diff / 3_600_000)
  const m = Math.floor((diff % 3_600_000) / 60_000)
  return `${h}h ${m}m`
}

export function FundingRatePanel() {
  const { t } = useI18n()
  const [rates, setRates] = useState<Record<string, FundingRateData>>({})

  useEffect(() => {
    const fetchRates = () => {
      fetch(`${API_BASE}/api/v1/derivatives/funding-rates`)
        .then((r) => r.json())
        .then((d) => { if (d.data?.rates) setRates(d.data.rates) })
        .catch(() => {})
    }
    fetchRates()
    const interval = setInterval(fetchRates, 3000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const wsBase =
      process.env.NEXT_PUBLIC_WS_URL ||
      (process.env.NODE_ENV === "development"
        ? "ws://127.0.0.1:8080"
        : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`)
    const ws = new WebSocket(`${wsBase}/api/v1/ws/markets`)

    ws.onopen = () => {
      ws.send(JSON.stringify({ action: "subscribe", symbols: ["ALL"], exchange: "binance", market_type: "futures" }))
    }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type === "funding_rate") {
          const key = `${msg.data.exchange}:${msg.data.symbol}`
          setRates((prev) => ({ ...prev, [key]: msg.data }))
        }
      } catch {}
    }

    return () => ws.close()
  }, [])

  const entries = Object.entries(rates)

  return (
    <div className="space-y-2">
      {entries.length === 0 ? (
        <div className="text-center text-muted-foreground text-xs py-4">
          {t("tactical.waitingFunding")}
        </div>
      ) : (
        <div className="space-y-1">
          <div className="grid grid-cols-5 gap-2 text-xs text-muted-foreground px-2 py-1">
            <span>{t("tactical.symbol")}</span>
            <span className="text-right">{t("tactical.rate")}</span>
            <span className="text-right">{t("tactical.markPrice")}</span>
            <span className="text-right">{t("tactical.indexPrice")}</span>
            <span className="text-right">{t("tactical.next")}</span>
          </div>
          {entries.map(([key, r]) => {
            const isPositive = r.funding_rate > 0
            const isExtreme = Math.abs(r.funding_rate) > 0.001
            return (
              <div
                key={key}
                className={cn(
                  "grid grid-cols-5 gap-2 text-xs font-mono px-2 py-1.5 rounded",
                  isExtreme ? "bg-yellow-500/10" : "bg-muted/30",
                )}
              >
                <span className="truncate">{r.symbol}</span>
                <span className={cn(
                  "text-right font-bold",
                  isPositive ? "text-green-400" : "text-red-400",
                  isExtreme && "text-yellow-400"
                )}>
                  {formatRate(r.funding_rate)}
                </span>
                <span className="text-right">{r.mark_price.toLocaleString()}</span>
                <span className="text-right">{r.index_price > 0 ? r.index_price.toLocaleString() : "—"}</span>
                <span className="text-right text-muted-foreground">
                  {r.next_funding_time > 0 ? formatCountdown(r.next_funding_time) : "—"}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
