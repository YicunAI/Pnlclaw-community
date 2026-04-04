"use client"

import React, { useEffect, useState, useMemo, useCallback, useRef } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Input } from "@/components/ui/input"
import { Activity, Flame } from "lucide-react"
import {
  type KlineData,
  type OrderbookData,
  type ExchangeProvider,
  type MarketType,
} from "@/lib/api-client"
import { useAppSettings } from "@/lib/hooks/use-api"
import { useKlineHistory } from "@/lib/hooks/use-klines"
import { useI18n } from "@/components/i18n/use-i18n"
import { useDashboardRealtime } from "@/components/providers/dashboard-realtime-provider"
import { LargeTradeFeed } from "@/components/tactical/large-trade-feed"
import { LiquidationPanel } from "@/components/tactical/liquidation-panel"
import { TickerPanel } from "@/components/trading/ticker-panel"
import { OrderbookPanel } from "@/components/trading/orderbook-panel"
import dynamic from "next/dynamic"
import { perf } from "@/lib/perf"

const CandlestickChart = dynamic(
  () => import("@/components/trading/candlestick-chart"),
  {
    ssr: false,
    loading: () => <Skeleton className="h-[420px] w-full" />
  }
)

const SYMBOLS = [
  { value: "BTC/USDT", label: "BTC/USDT" },
  { value: "ETH/USDT", label: "ETH/USDT" },
]

const INTERVALS = [
  { value: "1m", label: "1m" },
  { value: "5m", label: "5m" },
  { value: "15m", label: "15m" },
  { value: "30m", label: "30m" },
  { value: "1h", label: "1H" },
  { value: "4h", label: "4H" },
  { value: "1d", label: "1D" },
]

const INTERVAL_MS: Record<string, number> = {
  "1m": 60_000,
  "5m": 300_000,
  "15m": 900_000,
  "30m": 1_800_000,
  "1h": 3_600_000,
  "2h": 7_200_000,
  "4h": 14_400_000,
  "1d": 86_400_000,
  "1w": 604_800_000,
}

const RECENT_SYMBOLS_KEY = "pnlclaw-recent-symbols"
const MAX_RECENT_SYMBOLS = 8

function normalizeSymbolInput(input: string): string {
  const cleaned = input
    .trim()
    .toUpperCase()
    .replace(/[\s_-]+/g, "/")
    .replace(/\/+/, "/")

  if (!cleaned) return ""
  if (cleaned.includes("/")) return cleaned
  if (cleaned.endsWith("USDT") && cleaned.length > 4) {
    return `${cleaned.slice(0, -4)}/USDT`
  }
  return cleaned
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------



export default function MarketsPage() {
  const perfMarkedRef = useRef(false)
  if (!perfMarkedRef.current) {
    perf.mark("route_change")
    perfMarkedRef.current = true
  }

  const { locale, t } = useI18n()
  const { market: ws, marketSubscription, setMarketSubscription } = useDashboardRealtime()
  const [symbol, setSymbol] = useState(marketSubscription.symbol)
  const [customSymbol, setCustomSymbol] = useState("")
  const [recentSymbols, setRecentSymbols] = useState<string[]>(() => {
    if (typeof window === "undefined") return []
    try {
      const raw = localStorage.getItem(RECENT_SYMBOLS_KEY)
      if (!raw) return []
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      return parsed
        .filter((item): item is string => typeof item === "string")
        .map((item) => normalizeSymbolInput(item))
        .filter(Boolean)
        .slice(0, MAX_RECENT_SYMBOLS)
    } catch {
      return []
    }
  })
  const [interval, setKlineInterval] = useState("1h")
  const [exchange, setExchange] = useState<ExchangeProvider>(marketSubscription.exchange)
  const [marketType, setMarketType] = useState<MarketType>("futures")
  const {
    klines: historyKlines,
    error: klineError,
    isLoading: loading,
    isLoadingMore,
    noMoreData,
    loadMore: loadMoreKlines,
  } = useKlineHistory(symbol, interval, exchange, marketType)

  const error = useMemo(() => {
    if (!klineError) return null
    if (klineError.includes("not available yet"))
      return t("markets.sourceUnavailable", { exchange, marketType })
    if (klineError.startsWith("HTTP "))
      return t("markets.exchangeNoData", { exchange: exchange.toUpperCase(), marketType })
    return t("markets.apiUnreachable")
  }, [klineError, exchange, marketType, t])

  const ticker = ws.ticker
  const orderbook = ws.orderbook
  const { stale, streamState } = ws

  const klines = useMemo(() => {
    if (historyKlines.length === 0) return []
    const matchingWsKlines = ws.klines.filter(
      (k) => !k.wsInterval || k.wsInterval === interval
    )
    if (matchingWsKlines.length === 0) return historyKlines
    const map = new Map<number, KlineData>()
    for (const k of historyKlines) map.set(k.timestamp, k)
    for (const k of matchingWsKlines) map.set(k.timestamp, k)
    return Array.from(map.values())
      .filter((k) => k && typeof k.timestamp === "number" && !isNaN(k.timestamp))
      .sort((a, b) => a.timestamp - b.timestamp)
  }, [historyKlines, ws.klines, interval])

  // Performance: track first data arrival and WS connection
  const firstDataMarkedRef = useRef(false)
  useEffect(() => {
    if (klines.length > 0 && !firstDataMarkedRef.current) {
      firstDataMarkedRef.current = true
      perf.mark("first_data")
      perf.measure("time_to_data", "route_change", "first_data")
    }
  }, [klines.length])

  useEffect(() => {
    if (ws.connected) {
      perf.mark("ws_ready")
      perf.measure("time_to_ws", "route_change", "ws_ready")
    }
  }, [ws.connected])

  const quickSymbols = useMemo(() => {
    return [...new Set([...SYMBOLS.map((s) => s.value), ...recentSymbols])]
  }, [recentSymbols])

  const addRecentSymbol = useCallback((nextSymbol: string) => {
    setRecentSymbols((prev) => {
      const next = [nextSymbol, ...prev.filter((s) => s !== nextSymbol)].slice(
        0,
        MAX_RECENT_SYMBOLS
      )
      localStorage.setItem(RECENT_SYMBOLS_KEY, JSON.stringify(next))
      return next
    })
  }, [])

  const selectSymbol = useCallback((nextSymbol: string) => {
    setSymbol(nextSymbol)
    addRecentSymbol(nextSymbol)
  }, [addRecentSymbol])

  useEffect(() => {
    setMarketSubscription({ symbol, exchange, marketType })
  }, [symbol, exchange, marketType, setMarketSubscription])

  useEffect(() => {
    try {
      const raw = localStorage.getItem(RECENT_SYMBOLS_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return
      const cleaned = parsed
        .filter((item): item is string => typeof item === "string")
        .map((item) => normalizeSymbolInput(item))
        .filter(Boolean)
        .slice(0, MAX_RECENT_SYMBOLS)
      setRecentSymbols(cleaned)
    } catch {
      // ignore parse errors
    }
  }, [])

  const { data: appSettings } = useAppSettings()
  useEffect(() => {
    if (!appSettings) return
    const provider = appSettings.exchange?.provider
    const type = appSettings.exchange?.market_type
    if (provider === "binance" || provider === "okx") setExchange(provider)
    if (type === "futures") setMarketType(type)
  }, [appSettings])



  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold">{t("markets.title")}</h1>
            <span
              className={`inline-block h-2 w-2 rounded-full ${ws.connected ? (stale ? "bg-yellow-400" : "bg-emerald-400 animate-pulse") : "bg-red-400"}`}
              title={
                ws.connected
                  ? stale
                    ? (streamState === "recovering" ? "WebSocket recovering" : "Market data stale")
                    : "WebSocket connected"
                  : "WebSocket disconnected"
              }
            />
          </div>
          <p className="text-sm text-muted-foreground mt-1">{t("markets.subtitle")}</p>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          <div className="flex gap-2">
            <select
              value={exchange}
              onChange={(e) => setExchange(e.target.value as ExchangeProvider)}
              className="h-9 min-w-[110px] rounded-lg border border-input bg-background px-3 text-sm"
              aria-label={t("markets.exchange")}
            >
              <option value="binance">Binance</option>
              <option value="okx">OKX</option>
            </select>
            <span className="h-9 flex items-center min-w-[80px] rounded-lg border border-input bg-background px-3 text-sm text-muted-foreground">
              {t("markets.futures")}
            </span>
          </div>
          {quickSymbols.map((value) => (
            <button
              key={value}
              onClick={() => selectSymbol(value)}
              className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                symbol === value
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
              }`}
            >
              {value}
            </button>
          ))}
          <div className="flex gap-2">
            <Input
              value={customSymbol}
              onChange={(e) => setCustomSymbol(e.target.value)}
              placeholder={t("markets.customSymbol")}
              className="h-9 w-48"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  const normalized = normalizeSymbolInput(customSymbol)
                  if (normalized) {
                    selectSymbol(normalized)
                    setCustomSymbol("")
                  }
                }
              }}
            />
            <button
              onClick={() => {
                const normalized = normalizeSymbolInput(customSymbol)
                if (normalized) {
                  selectSymbol(normalized)
                  setCustomSymbol("")
                }
              }}
              className="px-3 py-1.5 text-sm rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80"
            >
              {t("markets.add")}
            </button>
          </div>
        </div>
      </div>

      {error ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <p>{error}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {/* Row 1: Chart + Ticker + Orderbook */}
          <div className="grid grid-cols-[1fr_300px] gap-6">
            <Card>
              <CardHeader className="pb-2 flex flex-row items-center justify-between">
                <CardTitle className="text-base">
                  {t("markets.priceChart", { symbol })}
                </CardTitle>
                <div className="flex gap-0.5">
                  {INTERVALS.map((iv) => (
                    <button
                      key={iv.value}
                      onClick={() => { setKlineInterval(iv.value); setMarketSubscription({ interval: iv.value }) }}
                      className={`px-2 py-1 text-xs rounded-md transition-colors ${
                        interval === iv.value
                          ? "bg-primary/20 text-primary font-semibold"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {iv.label}
                    </button>
                  ))}
                </div>
              </CardHeader>
              <CardContent>
                <div className="h-[650px] w-full relative">
                  {/* Chart container always mounted — never destroy/recreate canvas */}
                  <CandlestickChart
                    data={klines}
                    interval={interval}
                    onLoadMore={loadMoreKlines}
                    isLoadingMore={isLoadingMore}
                  />
                  {/* Overlay states — chart stays alive underneath */}
                  {loading && (
                    <div className="absolute inset-0 z-20 flex items-center justify-center bg-background/80">
                      <Skeleton className="h-full w-full" />
                    </div>
                  )}
                  {!loading && klines.length === 0 && (
                    <div className="absolute inset-0 z-20 flex items-center justify-center text-sm text-muted-foreground bg-background/60">
                      {t("markets.noKline")}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            <div className="flex flex-col gap-4">
              <Card className="shrink-0">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{t("markets.ticker")}</CardTitle>
                </CardHeader>
                <CardContent>
                  <TickerPanel ticker={ticker} />
                </CardContent>
              </Card>

              <Card className="flex-1 min-h-0 overflow-hidden">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{t("markets.orderBook")}</CardTitle>
                </CardHeader>
                <CardContent className="overflow-y-auto">
                  <OrderbookPanel data={orderbook} baseCurrency={symbol.split("/")[0]} quoteCurrency={symbol.split("/")[1] || "USDT"} />
                </CardContent>
              </Card>
            </div>
          </div>

          {/* Row 2: Large Trades + Liquidation */}
          <div className="grid grid-cols-2 gap-6">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Activity className="h-4 w-4 text-blue-400" />
                  {t("tactical.largeTrades")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <LargeTradeFeed />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Flame className="h-4 w-4 text-orange-400" />
                  {t("tactical.liquidationMonitor")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <LiquidationPanel />
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
