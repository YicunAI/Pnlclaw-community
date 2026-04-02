"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { ArrowDown, ArrowUp } from "lucide-react"
import { cn } from "@/lib/utils"
import { useI18n } from "@/components/i18n/use-i18n"

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8080" : "")

interface LargeTradeEvent {
  exchange: string
  symbol: string
  market_type: "spot" | "futures"
  side: "buy" | "sell"
  price: number
  quantity: number
  notional_usd: number
  trade_id: string
  timestamp: number
}

const EXCHANGES = ["all", "binance", "okx"] as const

function formatUSD(val: number): string {
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(2)}M`
  if (val >= 1_000) return `$${(val / 1_000).toFixed(1)}K`
  return `$${val.toFixed(0)}`
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

function sizeCategory(usd: number): string {
  if (usd >= 1_000_000) return "whale"
  if (usd >= 500_000) return "large"
  if (usd >= 100_000) return "medium"
  return "normal"
}

export function LargeTradeFeed() {
  const { t } = useI18n()
  const [trades, setTrades] = useState<LargeTradeEvent[]>([])
  const [stats, setStats] = useState<{ buy_count: number; sell_count: number; buy_volume_usd: number; sell_volume_usd: number } | null>(null)
  const [exchangeFilter, setExchangeFilter] = useState<string>("all")
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/derivatives/large-trades/recent?limit=50`)
      .then((r) => r.json())
      .then((d) => { if (d.data?.events) setTrades([...d.data.events].reverse()) })
      .catch(() => {})

    fetch(`${API_BASE}/api/v1/derivatives/large-trades/stats`)
      .then((r) => r.json())
      .then((d) => { if (d.data) setStats(d.data) })
      .catch(() => {})
  }, [])

  useEffect(() => {
    const wsBase =
      process.env.NEXT_PUBLIC_WS_URL ||
      (process.env.NODE_ENV === "development"
        ? "ws://127.0.0.1:8080"
        : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`)
    const ws = new WebSocket(`${wsBase}/api/v1/ws/markets`)
    wsRef.current = ws

    ws.onopen = () => {
      ws.send(JSON.stringify({ action: "subscribe", symbols: ["ALL"], exchange: "binance", market_type: "spot" }))
      ws.send(JSON.stringify({ action: "subscribe", symbols: ["ALL"], exchange: "binance", market_type: "futures" }))
      ws.send(JSON.stringify({ action: "subscribe", symbols: ["ALL"], exchange: "okx", market_type: "spot" }))
      ws.send(JSON.stringify({ action: "subscribe", symbols: ["ALL"], exchange: "okx", market_type: "futures" }))
    }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type === "large_trade") {
          setTrades((prev) => [msg.data, ...prev].slice(0, 200))
        }
      } catch {}
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [])

  const filtered = useMemo(() => {
    if (exchangeFilter === "all") return trades
    return trades.filter((tr) => tr.exchange === exchangeFilter)
  }, [trades, exchangeFilter])

  const buyCount = stats?.buy_count ?? 0
  const sellCount = stats?.sell_count ?? 0
  const buyVol = stats?.buy_volume_usd ?? 0
  const sellVol = stats?.sell_volume_usd ?? 0

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-4 gap-2 text-xs">
        <div className="bg-green-500/10 rounded p-2 text-center">
          <div className="text-green-400 font-mono font-bold">{buyCount}</div>
          <div className="text-muted-foreground">{t("tactical.buyTrades")}</div>
        </div>
        <div className="bg-red-500/10 rounded p-2 text-center">
          <div className="text-red-400 font-mono font-bold">{sellCount}</div>
          <div className="text-muted-foreground">{t("tactical.sellTrades")}</div>
        </div>
        <div className="bg-green-500/10 rounded p-2 text-center">
          <div className="text-green-400 font-mono font-bold">{formatUSD(buyVol)}</div>
          <div className="text-muted-foreground">{t("tactical.buyVolume")}</div>
        </div>
        <div className="bg-red-500/10 rounded p-2 text-center">
          <div className="text-red-400 font-mono font-bold">{formatUSD(sellVol)}</div>
          <div className="text-muted-foreground">{t("tactical.sellVolume")}</div>
        </div>
      </div>

      {/* Exchange filter only */}
      <div className="flex items-center gap-1.5">
        {EXCHANGES.map((ex) => (
          <button
            key={ex}
            onClick={() => setExchangeFilter(ex)}
            className={cn(
              "px-2.5 py-0.5 text-[11px] rounded transition-colors",
              exchangeFilter === ex
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/80"
            )}
          >
            {ex === "all" ? t("tactical.allExchanges") : ex}
          </button>
        ))}
      </div>

      <div className="max-h-[400px] overflow-y-auto space-y-1 hover-scrollbar">
        {filtered.length === 0 ? (
          <div className="text-center text-muted-foreground text-xs py-8">
            {t("tactical.waitingTrades")}
          </div>
        ) : (
          filtered.map((tr, i) => {
            const cat = sizeCategory(tr.notional_usd)
            return (
              <div
                key={`${tr.trade_id}-${i}`}
                className={cn(
                  "flex items-center gap-2 px-2 py-1.5 rounded text-xs font-mono transition-colors",
                  cat === "whale" && "bg-yellow-500/10 border border-yellow-500/30",
                  cat === "large" && "bg-orange-500/5",
                  cat === "medium" && "bg-muted/50",
                  cat === "normal" && "",
                )}
              >
                {tr.side === "buy" ? (
                  <ArrowUp className="h-3 w-3 text-green-500 shrink-0" />
                ) : (
                  <ArrowDown className="h-3 w-3 text-red-500 shrink-0" />
                )}
                <span className="text-muted-foreground w-14">{formatTime(tr.timestamp)}</span>
                <span className="w-20 truncate">{tr.symbol}</span>
                <span className={cn("w-20 text-right", tr.side === "buy" ? "text-green-400" : "text-red-400")}>
                  {tr.price.toLocaleString()}
                </span>
                <span className="w-16 text-right">{tr.quantity.toFixed(4)}</span>
                <span className={cn(
                  "w-20 text-right font-bold",
                  cat === "whale" ? "text-yellow-400" :
                  cat === "large" ? "text-orange-400" :
                  "text-foreground"
                )}>
                  {formatUSD(tr.notional_usd)}
                </span>
                <span className="text-muted-foreground w-24 text-right flex items-center justify-end gap-1">
                  <span className={cn(
                    "text-[10px] px-1 rounded",
                    tr.market_type === "futures" ? "bg-purple-500/20 text-purple-400" : "bg-blue-500/20 text-blue-400"
                  )}>
                    {tr.market_type === "futures" ? t("tactical.futures") : t("tactical.spot")}
                  </span>
                  {tr.exchange}
                </span>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
