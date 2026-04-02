"use client"

import { useEffect, useMemo, useState } from "react"
import { Flame } from "lucide-react"
import { cn } from "@/lib/utils"
import { useI18n } from "@/components/i18n/use-i18n"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8080"

interface LiquidationStats {
  window: string
  long_liquidated_usd: number
  short_liquidated_usd: number
  total_liquidated_usd: number
  long_count: number
  short_count: number
  largest_single_usd: number
}

interface LiquidationEvent {
  exchange: string
  symbol: string
  side: "long" | "short"
  quantity: number
  price: number
  notional_usd: number
  timestamp: number
}

function formatUSD(val: number): string {
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(2)}M`
  if (val >= 1_000) return `$${(val / 1_000).toFixed(1)}K`
  return `$${val.toFixed(0)}`
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

const WINDOWS = ["15m", "30m", "1h", "4h", "24h"] as const
const TRACKED_SYMBOLS = new Set(["BTC/USDT", "BTC/USD", "ETH/USDT", "ETH/USD"])

export function LiquidationPanel() {
  const { t } = useI18n()
  const [allStats, setAllStats] = useState<Record<string, LiquidationStats>>({})
  const [events, setEvents] = useState<LiquidationEvent[]>([])
  const [selectedWindow, setSelectedWindow] = useState<string>("1h")

  useEffect(() => {
    const fetchStats = () => {
      fetch(`${API_BASE}/api/v1/derivatives/liquidation-stats/all`)
        .then((r) => r.json())
        .then((d) => { if (d.data?.windows) setAllStats(d.data.windows) })
        .catch(() => {})
    }
    fetchStats()
    const interval = setInterval(fetchStats, 5000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/derivatives/liquidations/recent?limit=200`)
      .then((r) => r.json())
      .then((d) => {
        if (d.data?.events) {
          const filtered = d.data.events.filter((e: LiquidationEvent) => TRACKED_SYMBOLS.has(e.symbol))
          setEvents([...filtered].reverse())
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://127.0.0.1:8080"
    const ws = new WebSocket(`${wsBase}/api/v1/ws/markets`)

    ws.onopen = () => {
      ws.send(JSON.stringify({ action: "subscribe", symbols: ["ALL"], exchange: "binance", market_type: "futures" }))
      ws.send(JSON.stringify({ action: "subscribe", symbols: ["ALL"], exchange: "okx", market_type: "futures" }))
    }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type === "liquidation" && TRACKED_SYMBOLS.has(msg.data?.symbol ?? "")) {
          setEvents((prev) => [msg.data, ...prev].slice(0, 200))
        }
        if (msg.type === "liquidation_stats") {
          setAllStats((prev) => ({ ...prev, [msg.data.window]: msg.data }))
        }
      } catch {}
    }

    return () => ws.close()
  }, [])

  const stats = allStats[selectedWindow]

  return (
    <div className="space-y-3">
      <div className="flex gap-1">
        {WINDOWS.map((w) => (
          <button
            key={w}
            onClick={() => setSelectedWindow(w)}
            className={cn(
              "px-2 py-1 text-xs rounded transition-colors",
              selectedWindow === w
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/80"
            )}
          >
            {w}
          </button>
        ))}
      </div>

      {stats ? (
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="bg-red-500/10 rounded p-2 text-center">
            <div className="text-red-400 font-mono font-bold">{formatUSD(stats.long_liquidated_usd)}</div>
            <div className="text-muted-foreground">{t("tactical.longLiq")} ({stats.long_count})</div>
          </div>
          <div className="bg-green-500/10 rounded p-2 text-center">
            <div className="text-green-400 font-mono font-bold">{formatUSD(stats.short_liquidated_usd)}</div>
            <div className="text-muted-foreground">{t("tactical.shortLiq")} ({stats.short_count})</div>
          </div>
          <div className="bg-yellow-500/10 rounded p-2 text-center">
            <Flame className="h-3 w-3 text-yellow-400 mx-auto mb-0.5" />
            <div className="text-yellow-400 font-mono font-bold">{formatUSD(stats.total_liquidated_usd)}</div>
            <div className="text-muted-foreground">{t("tactical.total")}</div>
          </div>
        </div>
      ) : (
        <div className="text-center text-muted-foreground text-xs py-4">{t("tactical.noData")}</div>
      )}

      <div className="max-h-[300px] overflow-y-auto space-y-1 hover-scrollbar">
        {events.length === 0 ? (
          <div className="text-center text-muted-foreground text-xs py-4">
            {t("tactical.waitingLiq")}
          </div>
        ) : (
          events.map((e, i) => (
            <div
              key={`liq-${e.timestamp}-${i}`}
              className={cn(
                "flex items-center gap-2 px-2 py-1 rounded text-xs font-mono",
                e.notional_usd >= 1_000_000 ? "bg-yellow-500/10 border border-yellow-500/20" :
                e.notional_usd >= 100_000 ? "bg-orange-500/5" : "bg-muted/30",
              )}
            >
              <Flame className={cn(
                "h-3 w-3 shrink-0",
                e.notional_usd >= 1_000_000 ? "text-yellow-400" : "text-orange-400"
              )} />
              <span className="text-muted-foreground w-14">{formatTime(e.timestamp)}</span>
              <span className="w-20 truncate">{e.symbol}</span>
              {e.side === "long" ? (
                <span className="text-red-400 w-10">LONG</span>
              ) : (
                <span className="text-green-400 w-10">SHORT</span>
              )}
              <span className="w-20 text-right">{e.price.toLocaleString()}</span>
              <span className={cn(
                "w-20 text-right font-bold",
                e.notional_usd >= 1_000_000 ? "text-yellow-400" : "text-foreground"
              )}>
                {formatUSD(e.notional_usd)}
              </span>
              <span className="text-muted-foreground w-14 text-right">{e.exchange}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
