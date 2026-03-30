"use client"

import { useDashboardRealtime } from "@/components/providers/dashboard-realtime-provider"

function formatAge(lastMessageAt: number | null): string {
  if (!lastMessageAt) return "n/a"
  const age = Math.max(0, Date.now() - lastMessageAt)
  return `${Math.floor(age)}ms`
}

export function RealtimeDebugPanel() {
  if (process.env.NODE_ENV === "production") return null

  const { trading, market, marketSubscription } = useDashboardRealtime()

  return (
    <div className="fixed bottom-3 left-3 z-50 rounded-md border border-border bg-card/95 px-3 py-2 text-[11px] shadow-lg backdrop-blur-sm">
      <p className="font-semibold text-foreground mb-1">Realtime Debug</p>
      <div className="space-y-1 text-muted-foreground">
        <p>
          trading: {trading.streamState} · {trading.connected ? "connected" : "disconnected"} · age {formatAge(trading.lastMessageAt)}
        </p>
        <p>
          market: {market.streamState} · {market.connected ? "connected" : "disconnected"} · age {formatAge(market.lastMessageAt)}
        </p>
        <p>
          sub: {marketSubscription.exchange}/{marketSubscription.marketType}/{marketSubscription.symbol}
        </p>
      </div>
    </div>
  )
}
