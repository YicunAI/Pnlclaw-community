"use client"

import React, { useEffect, useState, useMemo, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { TrendingUp, TrendingDown } from "lucide-react"
import {
  getTicker,
  getKlines,
  getOrderbook,
  type TickerData,
  type KlineData,
  type OrderbookData,
} from "@/lib/api-client"

const SYMBOLS = [
  { value: "BTC/USDT", label: "BTC/USDT" },
  { value: "ETH/USDT", label: "ETH/USDT" },
]

const INTERVALS = [
  { value: "1h", label: "1H" },
  { value: "4h", label: "4H" },
  { value: "1d", label: "1D" },
]

function KlineChart({ data }: { data: KlineData[] }) {
  const { width, height, chartH, volH } = {
    width: 700,
    height: 360,
    chartH: 260,
    volH: 80,
  }
  const padX = 50
  const padY = 20

  const prices = data.map((d) => d.close)
  const volumes = data.map((d) => d.volume)
  const minP = Math.min(...prices)
  const maxP = Math.max(...prices)
  const maxV = Math.max(...volumes)
  const rangeP = maxP - minP || 1

  const barW = Math.max(1, (width - padX * 2) / data.length)

  const pricePath = data
    .map((d, i) => {
      const x = padX + (i / (data.length - 1 || 1)) * (width - padX * 2)
      const y = padY + (1 - (d.close - minP) / rangeP) * (chartH - padY * 2)
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(" ")

  const [hover, setHover] = useState<number | null>(null)
  const hovered = hover !== null ? data[hover] : null

  return (
    <div className="relative">
      {hovered && (
        <div className="absolute top-1 left-14 z-10 bg-card border border-border rounded-md px-3 py-2 text-xs space-y-0.5">
          <div>
            <span className="text-muted-foreground">O</span>{" "}
            {hovered.open.toFixed(2)}{" "}
            <span className="text-muted-foreground">H</span>{" "}
            {hovered.high.toFixed(2)}{" "}
            <span className="text-muted-foreground">L</span>{" "}
            {hovered.low.toFixed(2)}{" "}
            <span className="text-muted-foreground">C</span>{" "}
            {hovered.close.toFixed(2)}
          </div>
          <div className="text-muted-foreground">
            Vol {hovered.volume.toLocaleString()}
          </div>
        </div>
      )}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        onMouseLeave={() => setHover(null)}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
          const y = padY + pct * (chartH - padY * 2)
          const price = maxP - pct * rangeP
          return (
            <g key={pct}>
              <line
                x1={padX}
                y1={y}
                x2={width - padX}
                y2={y}
                stroke="rgba(255,255,255,0.05)"
              />
              <text
                x={padX - 6}
                y={y + 4}
                textAnchor="end"
                className="fill-muted-foreground"
                fontSize={10}
              >
                {price.toFixed(0)}
              </text>
            </g>
          )
        })}

        <path d={pricePath} fill="none" stroke="#22d3ee" strokeWidth={1.5} />

        {data.map((d, i) => {
          const x = padX + (i / (data.length - 1 || 1)) * (width - padX * 2)
          const volPct = maxV > 0 ? d.volume / maxV : 0
          const barHeight = volPct * volH * 0.8
          const barY = chartH + volH - barHeight
          const isUp = d.close >= d.open
          return (
            <g key={i}>
              <rect
                x={x - barW / 2}
                y={barY}
                width={Math.max(1, barW - 1)}
                height={barHeight}
                fill={isUp ? "rgba(16,185,129,0.4)" : "rgba(239,68,68,0.4)"}
              />
              <rect
                x={x - barW / 2}
                y={padY}
                width={Math.max(1, barW)}
                height={height - padY}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
              />
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function OrderbookPanel({ data }: { data: OrderbookData | null }) {
  if (!data) return <Skeleton className="h-48" />

  const bids = data.bids.slice(0, 10)
  const asks = data.asks.slice(0, 10).reverse()
  const maxQty = Math.max(
    ...bids.map((b) => b[1]),
    ...asks.map((a) => a[1]),
    1
  )

  return (
    <div className="text-xs font-mono space-y-0.5">
      <div className="flex justify-between text-muted-foreground px-1 mb-1">
        <span>Price</span>
        <span>Quantity</span>
      </div>
      {asks.map(([price, qty], i) => (
        <div key={`a-${i}`} className="flex justify-between relative px-1 py-0.5">
          <div
            className="absolute inset-0 bg-red-500/10"
            style={{ width: `${(qty / maxQty) * 100}%`, right: 0, left: "auto" }}
          />
          <span className="text-red-400 relative z-10">
            {price.toFixed(2)}
          </span>
          <span className="relative z-10">{qty.toFixed(4)}</span>
        </div>
      ))}
      <div className="border-t border-border my-1" />
      {bids.map(([price, qty], i) => (
        <div key={`b-${i}`} className="flex justify-between relative px-1 py-0.5">
          <div
            className="absolute inset-0 bg-emerald-500/10"
            style={{ width: `${(qty / maxQty) * 100}%`, right: 0, left: "auto" }}
          />
          <span className="text-emerald-400 relative z-10">
            {price.toFixed(2)}
          </span>
          <span className="relative z-10">{qty.toFixed(4)}</span>
        </div>
      ))}
    </div>
  )
}

export default function MarketsPage() {
  const [symbol, setSymbol] = useState("BTC/USDT")
  const [interval, setInterval] = useState("1h")
  const [ticker, setTicker] = useState<TickerData | null>(null)
  const [klines, setKlines] = useState<KlineData[]>([])
  const [orderbook, setOrderbook] = useState<OrderbookData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)

    const [t, k, o] = await Promise.all([
      getTicker(symbol),
      getKlines(symbol, interval, 100),
      getOrderbook(symbol, 10),
    ])

    if (t.error && k.error) {
      setError("Cannot reach API server. Start `pnlclaw` or the local API.")
      setLoading(false)
      return
    }

    if (t.data) setTicker(t.data)
    if (k.data) setKlines(k.data)
    if (o.data) setOrderbook(o.data)
    setLoading(false)
  }, [symbol, interval])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Markets</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Live market data and charts
          </p>
        </div>
        <div className="flex gap-2">
          {SYMBOLS.map((s) => (
            <button
              key={s.value}
              onClick={() => setSymbol(s.value)}
              className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                symbol === s.value
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <p>{error}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-[1fr_300px] gap-6">
          <div className="space-y-4">
            <Card>
              <CardHeader className="pb-2 flex flex-row items-center justify-between">
                <CardTitle className="text-base">
                  {symbol} Price Chart
                </CardTitle>
                <div className="flex gap-1">
                  {INTERVALS.map((iv) => (
                    <button
                      key={iv.value}
                      onClick={() => setInterval(iv.value)}
                      className={`px-2 py-1 text-xs rounded-md transition-colors ${
                        interval === iv.value
                          ? "bg-primary/20 text-primary"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {iv.label}
                    </button>
                  ))}
                </div>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <Skeleton className="h-[360px] w-full" />
                ) : klines.length > 0 ? (
                  <KlineChart data={klines} />
                ) : (
                  <div className="h-[360px] flex items-center justify-center text-sm text-muted-foreground">
                    No kline data available
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="space-y-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Ticker</CardTitle>
              </CardHeader>
              <CardContent>
                {loading || !ticker ? (
                  <div className="space-y-3">
                    <Skeleton className="h-8 w-32" />
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-4 w-20" />
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="text-2xl font-bold font-mono">
                      ${ticker.price?.toLocaleString()}
                    </div>
                    <div className="flex items-center gap-2">
                      {(ticker.change_24h ?? 0) >= 0 ? (
                        <TrendingUp className="h-4 w-4 text-emerald-400" />
                      ) : (
                        <TrendingDown className="h-4 w-4 text-red-400" />
                      )}
                      <Badge
                        variant={
                          (ticker.change_24h ?? 0) >= 0 ? "success" : "destructive"
                        }
                      >
                        {(ticker.change_24h ?? 0) >= 0 ? "+" : ""}
                        {((ticker.change_24h ?? 0) * 100).toFixed(2)}%
                      </Badge>
                    </div>
                    <div className="space-y-1 text-xs text-muted-foreground">
                      <div className="flex justify-between">
                        <span>24h High</span>
                        <span className="text-foreground font-mono">
                          ${ticker.high_24h?.toLocaleString()}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span>24h Low</span>
                        <span className="text-foreground font-mono">
                          ${ticker.low_24h?.toLocaleString()}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span>24h Volume</span>
                        <span className="text-foreground font-mono">
                          {ticker.volume_24h?.toLocaleString()}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Order Book</CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <Skeleton className="h-48" />
                ) : (
                  <OrderbookPanel data={orderbook} />
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
