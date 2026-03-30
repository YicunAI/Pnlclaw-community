"use client"

import React, { useEffect, useState, useCallback, useMemo, useRef } from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Separator } from "@/components/ui/separator"
import {
  TrendingUp,
  RefreshCw,
  ExternalLink,
  Search,
  Activity,
  DollarSign,
  BarChart3,
  X,
  BookOpen,
  Globe2,
  ChevronDown,
  ChevronUp,
  Bitcoin,
  Timer,
  Flame,
} from "lucide-react"
import {
  getPolymarketEvents,
  getPolymarketOrderbook,
  getPolymarketCryptoPredictions,
  type PolymarketEvent,
  type PolymarketSubMarket,
  type PolymarketOutcome,
  type PolymarketCategory,
  type PolymarketOrderbookData,
  type CryptoPrediction,
  type CryptoPredictionsResponse,
} from "@/lib/api-client"
import { usePolymarketWS } from "@/lib/use-polymarket-ws"
import { useI18n } from "@/components/i18n/use-i18n"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtVol(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}K`
  return `$${v.toFixed(0)}`
}

function fmtPct(p: number): string {
  return `${Math.round(p * 100)}%`
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—"
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    })
  } catch {
    return iso
  }
}

const CATEGORY_ICONS: Record<string, string> = {
  all: "🌐",
  crypto: "₿",
  politics: "🏛️",
  sports: "⚽",
  finance: "📈",
  entertainment: "🎬",
  geopolitics: "🌍",
  tech: "💻",
  science: "🔬",
  other: "📋",
}

// ---------------------------------------------------------------------------
// Probability Bar
// ---------------------------------------------------------------------------

function ProbBar({ outcomes }: { outcomes: PolymarketOutcome[] }) {
  const yes = outcomes.find((o) => o.outcome.toLowerCase() === "yes")
  const no = outcomes.find((o) => o.outcome.toLowerCase() === "no")

  if (yes && no) {
    const yPct = Math.round(yes.price * 100)
    return (
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs font-medium">
          <span className="text-emerald-400">Yes {yPct}¢</span>
          <span className="text-red-400">No {100 - yPct}¢</span>
        </div>
        <div className="h-2 rounded-full bg-red-500/30 overflow-hidden">
          <div
            className="h-full rounded-full bg-emerald-500 transition-all"
            style={{ width: `${yPct}%` }}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {outcomes.map((o) => (
        <Badge key={o.token_id} variant="outline" className="text-xs">
          {o.outcome}: {fmtPct(o.price)}
        </Badge>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Orderbook Panel
// ---------------------------------------------------------------------------

// Format price as cents (0.63 → "63¢")
function fmtCents(p: number): string {
  const cents = Math.round(p * 100)
  return `${cents}¢`
}

// Normalize orderbook levels: handle both [price, size] arrays and {price, size} objects
function normalizeBookLevels(
  raw: Array<{ price: string; size: string } | [string, string] | unknown>
): Array<{ price: number; size: number }> {
  return raw.map((lvl) => {
    if (Array.isArray(lvl)) {
      return { price: parseFloat(String(lvl[0]) || "0"), size: parseFloat(String(lvl[1]) || "0") }
    }
    const o = lvl as Record<string, unknown>
    return { price: parseFloat(String(o.price ?? "0")), size: parseFloat(String(o.size ?? "0")) }
  })
}

function OrderbookPanel({
  tokenId,
  outcome,
  onClose,
  wsState,
}: {
  tokenId: string
  outcome: string
  onClose: () => void
  wsState: ReturnType<typeof usePolymarketWS>
}) {
  const [book, setBook] = useState<PolymarketOrderbookData | null>(null)
  const [loading, setLoading] = useState(true)

  const ws = wsState

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      const res = await getPolymarketOrderbook(tokenId)
      if (!cancelled && res.data) setBook(res.data)
      setLoading(false)
    }
    if (tokenId) load()
    return () => { cancelled = true }
  }, [tokenId])

  // Merge WS live data with REST snapshot
  const liveBook = ws.books[tokenId]
  const rawBids = liveBook ? liveBook.bids : (book?.bids || [])
  const rawAsks = liveBook ? liveBook.asks : (book?.asks || [])

  // Normalize and sort: bids descending, asks ascending
  const bids = normalizeBookLevels(rawBids)
    .filter((l) => l.price > 0 && l.size > 0)
    .sort((a, b) => b.price - a.price)
    .slice(0, 8)
  const asks = normalizeBookLevels(rawAsks)
    .filter((l) => l.price > 0 && l.size > 0)
    .sort((a, b) => a.price - b.price)
    .slice(0, 8)

  // Max size for depth bar scaling
  const maxSize = Math.max(
    ...bids.map((b) => b.size),
    ...asks.map((a) => a.size),
    1
  )

  const bestBid = bids.length > 0 ? bids[0].price : 0
  const bestAsk = asks.length > 0 ? asks[0].price : 0
  const spread = bestBid > 0 && bestAsk > 0 ? bestAsk - bestBid : 0

  const lastTradeRaw = ws.lastTrades[tokenId]
    ?? (book?.last_trade_price ? parseFloat(book.last_trade_price) : 0)

  if (loading && !liveBook) return <Skeleton className="h-48 w-full" />
  if (bids.length === 0 && asks.length === 0) {
    return <p className="text-xs text-muted-foreground">No orderbook data</p>
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold flex items-center gap-1.5">
          <BookOpen className="h-3.5 w-3.5" />
          {outcome} Orderbook
          <span
            className={`h-1.5 w-1.5 rounded-full ${ws.connected ? (ws.stale ? "bg-yellow-500" : "bg-emerald-500 animate-pulse") : "bg-red-500"}`}
            title={
              ws.connected
                ? ws.stale
                  ? (ws.streamState === "recovering" ? "WS recovering" : "WS stale")
                  : "WS live"
                : "WS disconnected"
            }
          />
        </h4>
        <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={onClose}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Header row */}
      <div className="grid grid-cols-[1fr_1fr] gap-2 text-[10px]">
        <div className="flex justify-between text-muted-foreground px-1">
          <span>Price</span>
          <span>Shares</span>
          <span>Total</span>
        </div>
        <div className="flex justify-between text-muted-foreground px-1">
          <span>Price</span>
          <span>Shares</span>
          <span>Total</span>
        </div>
      </div>

      <div className="grid grid-cols-[1fr_1fr] gap-2 text-xs font-mono">
        {/* Bids (green, sorted high→low) */}
        <div className="space-y-0">
          <div className="text-[9px] text-emerald-500 font-sans font-medium mb-0.5 px-1">Bids</div>
          {bids.map((b, i) => {
            const total = b.price * b.size
            const depthPct = Math.min((b.size / maxSize) * 100, 100)
            return (
              <div key={i} className="flex justify-between px-1 py-[2px] relative items-center">
                <div
                  className="absolute inset-y-0 left-0 bg-emerald-500/10 rounded-sm"
                  style={{ width: `${depthPct}%` }}
                />
                <span className="relative text-emerald-400 w-[3.5em] text-right">{fmtCents(b.price)}</span>
                <span className="relative text-right w-[4.5em]">{b.size.toFixed(2)}</span>
                <span className="relative text-right text-muted-foreground w-[4.5em]">${total.toFixed(2)}</span>
              </div>
            )
          })}
          {bids.length === 0 && (
            <p className="text-muted-foreground text-center py-2 font-sans">—</p>
          )}
        </div>

        {/* Asks (red, sorted low→high) */}
        <div className="space-y-0">
          <div className="text-[9px] text-red-500 font-sans font-medium mb-0.5 px-1">Asks</div>
          {asks.map((a, i) => {
            const total = a.price * a.size
            const depthPct = Math.min((a.size / maxSize) * 100, 100)
            return (
              <div key={i} className="flex justify-between px-1 py-[2px] relative items-center">
                <div
                  className="absolute inset-y-0 right-0 bg-red-500/10 rounded-sm"
                  style={{ width: `${depthPct}%` }}
                />
                <span className="relative text-red-400 w-[3.5em] text-right">{fmtCents(a.price)}</span>
                <span className="relative text-right w-[4.5em]">{a.size.toFixed(2)}</span>
                <span className="relative text-right text-muted-foreground w-[4.5em]">${total.toFixed(2)}</span>
              </div>
            )
          })}
          {asks.length === 0 && (
            <p className="text-muted-foreground text-center py-2 font-sans">—</p>
          )}
        </div>
      </div>

      {/* Spread & Last Trade */}
      <div className="flex items-center justify-center gap-4 text-[10px] text-muted-foreground pt-1 border-t border-border/40">
        {lastTradeRaw > 0 && (
          <span>Last: <span className="text-foreground font-mono">{fmtCents(lastTradeRaw)}</span></span>
        )}
        {spread > 0 && (
          <span>Spread: <span className="text-foreground font-mono">{fmtCents(spread)}</span></span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Event Card (bilingual, with expandable markets + orderbook)
// ---------------------------------------------------------------------------

function EventCard({
  event,
  wsState,
}: {
  event: PolymarketEvent
  wsState: ReturnType<typeof usePolymarketWS>
}) {
  const { t } = useI18n()
  const router = useRouter()
  const [expanded, setExpanded] = useState(false)
  const [selectedToken, setSelectedToken] = useState<{
    id: string
    outcome: string
  } | null>(null)

  function getPrice(outcome: PolymarketOutcome): number {
    return wsState.prices[outcome.token_id] ?? outcome.price
  }

  return (
    <Card className="hover:border-primary/30 transition-colors">
      <CardContent className="p-4 space-y-3">
        {/* Header: bilingual title — click to open detail */}
        <div className="flex items-start gap-3">
          {event.icon && (
            <img
              src={event.icon}
              alt=""
              className="h-10 w-10 rounded-lg object-cover shrink-0 mt-0.5 cursor-pointer"
              onClick={() => router.push(`/polymarket/${event.id}`)}
              onError={(e) => { (e.target as HTMLImageElement).style.display = "none" }}
            />
          )}
          <div
            className="flex-1 min-w-0 cursor-pointer group"
            onClick={() => router.push(`/polymarket/${event.id}`)}
          >
            <h3 className="text-sm font-semibold leading-snug line-clamp-2 group-hover:text-primary transition-colors">
              {event.title_zh}
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1 flex items-center gap-1">
              <Globe2 className="h-3 w-3 shrink-0" />
              {event.title}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            <Badge variant="outline" className="text-[10px]">
              {CATEGORY_ICONS[event.category] || "📋"}{" "}
              {event.category_zh}
            </Badge>
            {event.markets.length > 1 && (
              <span className="text-[10px] text-muted-foreground">
                {event.market_count} {t("polymarket.subMarkets")}
              </span>
            )}
          </div>
        </div>

        {/* First market outcomes inline */}
        {event.markets.length > 0 && (
          <ProbBar
            outcomes={event.markets[0].outcomes.map((o) => ({
              ...o,
              price: getPrice(o),
            }))}
          />
        )}

        {/* Volume / Liquidity / Date row */}
        <div className="grid grid-cols-3 gap-3 text-xs">
          <div>
            <p className="text-muted-foreground flex items-center gap-1">
              <DollarSign className="h-3 w-3" /> {t("polymarket.vol")}
            </p>
            <p className="font-medium">{fmtVol(event.volume)}</p>
          </div>
          <div>
            <p className="text-muted-foreground flex items-center gap-1">
              <BarChart3 className="h-3 w-3" /> 24h
            </p>
            <p className="font-medium">{fmtVol(event.volume_24h)}</p>
          </div>
          <div>
            <p className="text-muted-foreground flex items-center gap-1">
              <Activity className="h-3 w-3" /> {t("polymarket.liq")}
            </p>
            <p className="font-medium">{fmtVol(event.liquidity)}</p>
          </div>
        </div>

        <Separator />

        {/* Expand / Collapse for sub-markets */}
        <div className="flex items-center justify-between">
          <Button
            variant="ghost"
            size="sm"
            className="text-xs h-7 px-2"
            onClick={() => {
              setExpanded(!expanded)
              setSelectedToken(null)
            }}
          >
            {expanded ? (
              <>
                <ChevronUp className="h-3.5 w-3.5 mr-1" />
                {t("polymarket.collapse")}
              </>
            ) : (
              <>
                <ChevronDown className="h-3.5 w-3.5 mr-1" />
                {t("polymarket.expandMarkets")} ({event.market_count})
              </>
            )}
          </Button>
          <a
            href={`https://polymarket.com/event/${event.slug}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] text-primary hover:underline flex items-center gap-1"
          >
            Polymarket <ExternalLink className="h-3 w-3" />
          </a>
        </div>

        {/* Expanded: sub-markets */}
        {expanded && (
          <div className="space-y-3 pt-1">
            {event.markets.map((m) => {
              const marketUrl = m.slug
                ? `https://polymarket.com/event/${event.slug}/${m.slug}`
                : `https://polymarket.com/event/${event.slug}`
              return (
                <div
                  key={m.id || m.condition_id}
                  className="rounded-lg border p-3 space-y-2 bg-muted/30 hover:border-primary/30 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <a
                      href={marketUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex-1 min-w-0 group"
                    >
                      <p className="text-xs font-medium group-hover:text-primary transition-colors">
                        {m.question_zh}
                        <ExternalLink className="h-3 w-3 inline ml-1 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </p>
                      <p className="text-[11px] text-muted-foreground flex items-center gap-1">
                        <Globe2 className="h-3 w-3 shrink-0" /> {m.question}
                      </p>
                    </a>
                  </div>

                  <ProbBar
                    outcomes={m.outcomes.map((o) => ({
                      ...o,
                      price: getPrice(o),
                    }))}
                  />

                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-muted-foreground">
                      Vol: {fmtVol(m.volume)} · Liq: {fmtVol(m.liquidity)}
                    </span>
                    <div className="flex gap-1">
                      {m.outcomes.map((o) => (
                        <Button
                          key={o.token_id}
                          variant={
                            selectedToken?.id === o.token_id
                              ? "default"
                              : "outline"
                          }
                          size="sm"
                          className="text-[10px] h-6 px-2"
                          onClick={() =>
                            setSelectedToken(
                              selectedToken?.id === o.token_id
                                ? null
                                : { id: o.token_id, outcome: o.outcome }
                            )
                          }
                        >
                          <BookOpen className="h-3 w-3 mr-1" />
                          {o.outcome}
                        </Button>
                      ))}
                      <a
                        href={marketUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-[10px] text-primary hover:underline h-6 px-1.5"
                      >
                        Poly <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                  </div>

                  {selectedToken &&
                    m.outcomes.some((o) => o.token_id === selectedToken.id) && (
                      <OrderbookPanel
                        tokenId={selectedToken.id}
                        outcome={selectedToken.outcome}
                        onClose={() => setSelectedToken(null)}
                        wsState={wsState}
                      />
                    )}
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Crypto Price Predictions — pinned at top (real data from /crypto-predictions)
// ---------------------------------------------------------------------------

const TF_ORDER = ["5m", "15m", "1h", "daily", "other"]
const TF_COLORS: Record<string, string> = {
  "5m": "text-red-400 border-red-500/30 bg-red-500/10",
  "15m": "text-orange-400 border-orange-500/30 bg-orange-500/10",
  "1h": "text-yellow-400 border-yellow-500/30 bg-yellow-500/10",
  daily: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  other: "text-muted-foreground border-border bg-muted/30",
}

// Countdown hook: returns "MM:SS" until endDate; fires onExpired once when it hits zero
function useCountdown(endDate: string, onExpired?: () => void): string {
  const [remaining, setRemaining] = useState("")
  const firedRef = useRef(false)
  useEffect(() => {
    firedRef.current = false
    if (!endDate) { setRemaining(""); return }
    function tick() {
      const end = new Date(endDate).getTime()
      const diff = end - Date.now()
      if (diff <= 0) {
        setRemaining("00:00")
        if (!firedRef.current) {
          firedRef.current = true
          onExpired?.()
        }
        return
      }
      const m = Math.floor(diff / 60000)
      const s = Math.floor((diff % 60000) / 1000)
      setRemaining(`${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`)
    }
    tick()
    const iv = setInterval(tick, 1000)
    return () => clearInterval(iv)
  }, [endDate, onExpired])
  return remaining
}

function ExpandedOrderbook({
  pred,
  onClose,
  wsState,
}: {
  pred: CryptoPrediction
  onClose: () => void
  wsState: ReturnType<typeof usePolymarketWS>
}) {
  const [selectedIdx, setSelectedIdx] = useState(0)
  const selected = pred.outcomes[selectedIdx] || pred.outcomes[0]
  if (!selected) return null

  return (
    <div className="ml-11 mr-2 mt-1 mb-1 p-2 border rounded-lg bg-muted/20">
      <div className="flex gap-1 mb-2">
        {pred.outcomes.map((o, i) => (
          <Button
            key={o.token_id}
            variant={selectedIdx === i ? "default" : "outline"}
            size="sm"
            className="text-[10px] h-6 px-2"
            onClick={() => setSelectedIdx(i)}
          >
            <BookOpen className="h-3 w-3 mr-1" />
            {o.outcome}
          </Button>
        ))}
      </div>
      <OrderbookPanel
        tokenId={selected.token_id}
        outcome={selected.outcome}
        onClose={onClose}
        wsState={wsState}
      />
    </div>
  )
}

function PredictionRow({
  pred,
  isExpanded,
  onToggle,
  locale,
  wsState,
  onExpired,
}: {
  pred: CryptoPrediction
  isExpanded: boolean
  onToggle: () => void
  locale: string
  wsState: ReturnType<typeof usePolymarketWS>
  onExpired?: () => void
}) {
  const countdown = useCountdown(pred.end_date, onExpired)
  const yesOutcome = pred.outcomes.find(
    (o) => o.outcome.toLowerCase() === "yes" || o.outcome.toLowerCase() === "up"
  )
  const noOutcome = pred.outcomes.find(
    (o) => o.outcome.toLowerCase() === "no" || o.outcome.toLowerCase() === "down"
  )

  // Derive price from WS: prefer explicit price_change, fallback to book midpoint
  const yesPriceWs = yesOutcome ? wsState.prices[yesOutcome.token_id] : undefined
  const noPriceWs = noOutcome ? wsState.prices[noOutcome.token_id] : undefined

  const yesPrice = yesOutcome
    ? (yesPriceWs ?? yesOutcome.price)
    : 0
  const noPrice = noOutcome
    ? (noPriceWs ?? noOutcome.price)
    : 0
  const tfColor = TF_COLORS[pred.timeframe] || TF_COLORS.other

  return (
    <div className="space-y-0">
      <div
        className="flex items-center gap-3 rounded-lg border bg-background/50 p-2.5 cursor-pointer hover:border-primary/40 transition-colors"
        onClick={onToggle}
      >
        <div className="h-8 w-8 rounded-full bg-orange-500/10 flex items-center justify-center shrink-0">
          <Bitcoin className="h-4 w-4 text-orange-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <p className="text-xs font-medium truncate">{pred.title_zh}</p>
            <Badge variant="outline" className={`text-[9px] h-4 px-1 shrink-0 ${tfColor}`}>
              {locale === "zh-CN" ? pred.timeframe_label.zh : pred.timeframe_label.en}
            </Badge>
          </div>
          <p className="text-[10px] text-muted-foreground truncate flex items-center gap-1">
            <Globe2 className="h-3 w-3 shrink-0" />
            {pred.title}
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0 text-xs">
          {countdown && (
            <span className={`font-mono text-[10px] rounded px-1.5 py-0.5 ${
              countdown === "00:00"
                ? "text-red-400 bg-red-500/10 border border-red-500/20 animate-pulse"
                : "text-amber-400 bg-amber-500/10 border border-amber-500/20"
            }`}>
              {countdown === "00:00" ? "⏳" : "⏱"} {countdown === "00:00" ? (locale === "zh-CN" ? "切换中..." : "Switching...") : countdown}
            </span>
          )}
          {yesOutcome && (
            <span className={`font-mono font-medium ${yesPrice > 0.5 ? "text-emerald-400" : "text-muted-foreground"}`}>
              Up: {fmtCents(yesPrice)}
            </span>
          )}
          {noOutcome && (
            <span className={`font-mono font-medium ${noPrice > 0.5 ? "text-red-400" : "text-muted-foreground"}`}>
              Down: {fmtCents(noPrice)}
            </span>
          )}
          <span className="text-muted-foreground">{fmtVol(pred.volume)}</span>
        </div>
        <a
          href={pred.polymarket_url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0"
          onClick={(e) => e.stopPropagation()}
        >
          <ExternalLink className="h-3.5 w-3.5 text-muted-foreground hover:text-primary" />
        </a>
      </div>

      {isExpanded && pred.outcomes.length > 0 && (
        <ExpandedOrderbook pred={pred} onClose={onToggle} wsState={wsState} />
      )}
    </div>
  )
}

function CryptoPriceBanner({
  wsState,
  onTokenIdsChange,
}: {
  wsState: ReturnType<typeof usePolymarketWS>
  onTokenIdsChange: (tokenIds: string[]) => void
}) {
  const { t, locale } = useI18n()
  const [data, setData] = useState<CryptoPredictionsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTf, setActiveTf] = useState<string>("all")
  const [activeAsset, setActiveAsset] = useState<string>("all")
  const [selectedPred, setSelectedPred] = useState<string | null>(null)
  const retryCount = useRef(0)
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const loadData = useCallback(async (isRetry = false) => {
    if (!isRetry) setLoading(true)
    setError(null)
    try {
      const res = await getPolymarketCryptoPredictions(50)
      if (res.data) {
        setData(res.data)
        retryCount.current = 0
      } else if (res.error) {
        throw new Error(res.error || "API error")
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      if (retryCount.current < 3) {
        retryCount.current += 1
        const delay = 2000 * Math.pow(2, retryCount.current - 1)
        setTimeout(() => loadData(true), delay)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  // When a prediction expires, wait 3s for new window to settle, then refetch
  const handleExpired = useCallback(() => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current)
    refreshTimer.current = setTimeout(() => {
      loadData()
    }, 3000)
  }, [loadData])

  useEffect(() => {
    loadData()
    return () => {
      if (refreshTimer.current) clearTimeout(refreshTimer.current)
    }
  }, [loadData])

  // Safety net: auto-refresh every 60s to catch any missed transitions
  useEffect(() => {
    const iv = setInterval(() => {
      if (!data) return
      const now = Date.now()
      const anyExpired = data.predictions.some(
        (p) => p.end_date && new Date(p.end_date).getTime() <= now
      )
      if (anyExpired) loadData()
    }, 60000)
    return () => clearInterval(iv)
  }, [data, loadData])

  const predictions = useMemo(() => {
    if (!data) return []
    let result = data.predictions
    if (activeAsset !== "all") {
      result = result.filter((p) => p.asset === activeAsset)
    }
    if (activeTf !== "all") {
      result = result.filter((p) => p.timeframe === activeTf)
    }
    return result
  }, [data, activeAsset, activeTf])

  // Collect all token IDs from visible predictions for WS subscription
  const allTokenIds = useMemo(() => {
    const ids: string[] = []
    for (const pred of predictions) {
      for (const o of pred.outcomes) {
        if (o.token_id) ids.push(o.token_id)
      }
    }
    return ids
  }, [predictions])

  useEffect(() => {
    onTokenIdsChange(allTokenIds)
  }, [allTokenIds, onTokenIdsChange])

  if (loading && !data) {
    return (
      <Card className="border-primary/30">
        <CardContent className="p-4">
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    )
  }

  if (error && !data) {
    return (
      <Card className="border-red-500/30">
        <CardContent className="p-4 flex flex-col items-center gap-2 py-6">
          <p className="text-sm text-red-400">
            {locale === "zh-CN" ? "加密预测市场加载失败" : "Failed to load crypto predictions"}
          </p>
          <p className="text-xs text-muted-foreground">{error}</p>
          {retryCount.current >= 3 && (
            <Button variant="outline" size="sm" onClick={() => { retryCount.current = 0; loadData() }}>
              <RefreshCw className="h-3 w-3 mr-1" />
              {locale === "zh-CN" ? "重新加载" : "Retry"}
            </Button>
          )}
          {retryCount.current < 3 && (
            <p className="text-xs text-amber-400 animate-pulse">
              {locale === "zh-CN" ? `重试中 (${retryCount.current}/3)...` : `Retrying (${retryCount.current}/3)...`}
            </p>
          )}
        </CardContent>
      </Card>
    )
  }

  if (!data || data.count === 0) return null

  const availableTfs = TF_ORDER.filter((tf) => data.by_timeframe[tf]?.length)
  const availableAssets = data.available_assets || []

  return (
    <Card className="border-primary/30 bg-gradient-to-r from-orange-500/5 via-transparent to-amber-500/5">
      <CardContent className="p-4 space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold flex items-center gap-2">
            <Flame className="h-4 w-4 text-orange-400" />
            {t("polymarket.cryptoPredictions")}
            <Badge variant="outline" className="text-[10px] font-normal">
              {data.count} {locale === "zh-CN" ? "个市场" : "markets"}
            </Badge>
            {wsState.connected ? (
              <span
                className={`h-2 w-2 rounded-full ${wsState.stale ? "bg-yellow-500" : "bg-emerald-500 animate-pulse"}`}
                title={wsState.stale ? (wsState.streamState === "recovering" ? "WS recovering" : "WS stale") : "WS Live"}
              />
            ) : allTokenIds.length > 0 ? (
              <span className="h-2 w-2 rounded-full bg-red-500" title="WS disconnected" />
            ) : null}
          </h2>
          <div className="flex items-center gap-1">
            <Button
              variant={activeTf === "all" ? "default" : "outline"}
              size="sm"
              className="text-[10px] h-6 px-2"
              onClick={() => setActiveTf("all")}
            >
              {locale === "zh-CN" ? "全部" : "All"}
            </Button>
            {availableTfs.map((tf) => {
              const label = data.timeframe_labels[tf]
              return (
                <Button
                  key={tf}
                  variant={activeTf === tf ? "default" : "outline"}
                  size="sm"
                  className="text-[10px] h-6 px-2"
                  onClick={() => setActiveTf(tf)}
                >
                  {locale === "zh-CN" ? label?.zh : label?.en}
                </Button>
              )
            })}
          </div>
        </div>

        {/* Asset filter */}
        {availableAssets.length > 1 && (
          <div className="flex gap-1 flex-wrap">
            <Button
              variant={activeAsset === "all" ? "default" : "outline"}
              size="sm"
              className="text-[10px] h-6 px-2"
              onClick={() => setActiveAsset("all")}
            >
              {locale === "zh-CN" ? "全部币种" : "All Assets"}
            </Button>
            {availableAssets.map((a) => (
              <Button
                key={a}
                variant={activeAsset === a ? "default" : "outline"}
                size="sm"
                className="text-[10px] h-6 px-2"
                onClick={() => setActiveAsset(a)}
              >
                {a}
              </Button>
            ))}
          </div>
        )}

        {/* Prediction rows */}
        <div className="grid grid-cols-1 gap-2 max-h-[400px] overflow-y-auto">
          {predictions.map((pred) => (
            <PredictionRow
              key={pred.id}
              pred={pred}
              isExpanded={selectedPred === pred.id}
              onToggle={() => setSelectedPred(selectedPred === pred.id ? null : pred.id)}
              locale={locale}
              wsState={wsState}
              onExpired={handleExpired}
            />
          ))}
        </div>

        {predictions.length === 0 && (
          <p className="text-xs text-muted-foreground text-center py-4">
            {locale === "zh-CN"
              ? "当前没有活跃的加密货币预测市场，请稍后刷新"
              : "No active crypto prediction markets right now"}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function PolymarketPage() {
  const { t } = useI18n()
  const [events, setEvents] = useState<PolymarketEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [activeCategory, setActiveCategory] = useState<string>("all")
  const [categoriesZh, setCategoriesZh] = useState<Record<string, string>>({})

  const [bannerTokenIds, setBannerTokenIds] = useState<string[]>([])

  const evRetry = useRef(0)
  const fetchEvents = useCallback(
    async (showRefresh = false) => {
      if (showRefresh) setRefreshing(true)
      else setLoading(true)
      setError(null)

      const catFilter = activeCategory === "all" ? "" : activeCategory
      try {
        const res = await getPolymarketEvents(50, true, catFilter)
        if (res.error || !res.data) {
          throw new Error(res.error || "Failed to load events")
        }
        setEvents(res.data.events)
        if (res.data.categories_zh) setCategoriesZh(res.data.categories_zh)
        evRetry.current = 0
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err)
        setError(msg)
        if (evRetry.current < 3) {
          evRetry.current += 1
          const delay = 2000 * Math.pow(2, evRetry.current - 1)
          setTimeout(() => fetchEvents(showRefresh), delay)
        }
      }

      setLoading(false)
      setRefreshing(false)
    },
    [activeCategory]
  )

  useEffect(() => {
    fetchEvents()
  }, [fetchEvents])

  const filtered = useMemo(() => {
    if (!search.trim()) return events
    const q = search.toLowerCase()
    return events.filter(
      (e) =>
        e.title.toLowerCase().includes(q) ||
        e.title_zh.includes(q) ||
        e.description.toLowerCase().includes(q)
    )
  }, [events, search])

  const pageTokenIds = useMemo(() => {
    const ids: string[] = []
    for (const event of filtered) {
      for (const market of event.markets) {
        for (const outcome of market.outcomes) {
          if (outcome.token_id) ids.push(outcome.token_id)
        }
      }
    }
    for (const tokenId of bannerTokenIds) {
      if (tokenId) ids.push(tokenId)
    }
    return ids
  }, [filtered, bannerTokenIds])

  const wsState = usePolymarketWS(pageTokenIds)

  const totalVolume = events.reduce((s, e) => s + e.volume, 0)
  const total24h = events.reduce((s, e) => s + e.volume_24h, 0)

  const CATEGORIES: string[] = [
    "all",
    "crypto",
    "politics",
    "sports",
    "finance",
    "geopolitics",
    "tech",
    "entertainment",
    "science",
    "other",
  ]

  return (
    <div className="space-y-5">
      {/* Title */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("polymarket.title")}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {t("polymarket.subtitle")}
          </p>
          {process.env.NODE_ENV !== "production" && (
            <p className="text-[11px] text-muted-foreground mt-1">
              ws: {wsState.streamState} · {wsState.connected ? "connected" : "disconnected"} · age {wsState.lastMessageAt ? `${Math.max(0, Date.now() - wsState.lastMessageAt)}ms` : "n/a"}
            </p>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fetchEvents(true)}
          disabled={refreshing}
        >
          <RefreshCw
            className={`h-4 w-4 mr-2 ${refreshing ? "animate-spin" : ""}`}
          />
          {t("polymarket.refresh")}
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        <Card>
          <CardContent className="flex items-center justify-between p-3">
            <div>
              <p className="text-[11px] text-muted-foreground">
                {t("polymarket.totalEvents")}
              </p>
              <p className="text-lg font-semibold">
                {loading ? "..." : events.length}
              </p>
            </div>
            <TrendingUp className="h-4 w-4 text-primary" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center justify-between p-3">
            <div>
              <p className="text-[11px] text-muted-foreground">
                {t("polymarket.totalVolume")}
              </p>
              <p className="text-lg font-semibold">
                {loading ? "..." : fmtVol(totalVolume)}
              </p>
            </div>
            <DollarSign className="h-4 w-4 text-primary" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center justify-between p-3">
            <div>
              <p className="text-[11px] text-muted-foreground">
                {t("polymarket.vol24h")}
              </p>
              <p className="text-lg font-semibold">
                {loading ? "..." : fmtVol(total24h)}
              </p>
            </div>
            <BarChart3 className="h-4 w-4 text-emerald-400" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center justify-between p-3">
            <div>
              <p className="text-[11px] text-muted-foreground">
                {t("polymarket.subMarketsTotal")}
              </p>
              <p className="text-lg font-semibold">
                {loading
                  ? "..."
                  : events.reduce((s, e) => s + e.market_count, 0)}
              </p>
            </div>
            <Activity className="h-4 w-4 text-primary" />
          </CardContent>
        </Card>
      </div>

      {/* Crypto Price Predictions Banner */}
      {!loading && (
        <CryptoPriceBanner
          wsState={wsState}
          onTokenIdsChange={setBannerTokenIds}
        />
      )}

      {/* Category Tabs */}
      <div className="flex gap-1.5 flex-wrap">
        {CATEGORIES.map((cat) => {
          const label =
            cat === "all"
              ? t("polymarket.allCategories")
              : categoriesZh[cat] || cat
          return (
            <Button
              key={cat}
              variant={activeCategory === cat ? "default" : "outline"}
              size="sm"
              className="text-xs h-7"
              onClick={() => setActiveCategory(cat)}
            >
              {CATEGORY_ICONS[cat]} {label}
            </Button>
          )
        })}
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder={t("polymarket.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-10"
        />
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg border border-red-500/30 bg-red-500/5">
          <p className="text-sm text-destructive flex-1">{error}</p>
          {evRetry.current >= 3 && (
            <Button variant="outline" size="sm" onClick={() => { evRetry.current = 0; fetchEvents() }}>
              <RefreshCw className="h-3 w-3 mr-1" />
              {t("polymarket.refresh")}
            </Button>
          )}
          {evRetry.current > 0 && evRetry.current < 3 && (
            <span className="text-xs text-amber-400 animate-pulse shrink-0">
              {`重试 ${evRetry.current}/3...`}
            </span>
          )}
        </div>
      )}

      {/* Event Grid */}
      {loading ? (
        <div className="grid grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-56 w-full rounded-xl" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm text-muted-foreground">
              {search
                ? t("polymarket.noResults")
                : t("polymarket.noMarkets")}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {filtered.map((event) => (
            <EventCard key={event.id} event={event} wsState={wsState} />
          ))}
        </div>
      )}
    </div>
  )
}
