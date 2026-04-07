"use client"

import React, { useEffect, useState, useMemo, useCallback } from "react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import {
  ArrowLeft,
  ExternalLink,
  Globe2,
  DollarSign,
  BarChart3,
  Activity,
  BookOpen,
  Clock,
  X,
  TrendingUp,
  ArrowUpDown,
  Calendar,
  CheckCircle2,
  Loader2,
} from "lucide-react"
import {
  getPolymarketEvent,
  getPolymarketOrderbook,
  type PolymarketEvent,
  type PolymarketSubMarket,
  type PolymarketOutcome,
  type PolymarketOrderbookData,
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
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return iso
  }
}

const CATEGORY_ICONS: Record<string, string> = {
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
// Probability Bar — larger variant for detail page
// ---------------------------------------------------------------------------

function ProbBar({ outcomes }: { outcomes: PolymarketOutcome[] }) {
  const yes = outcomes.find((o) => o.outcome.toLowerCase() === "yes")
  const no = outcomes.find((o) => o.outcome.toLowerCase() === "no")

  if (yes && no) {
    const yPct = Math.round(yes.price * 100)
    return (
      <div className="space-y-2">
        <div className="flex justify-between text-sm font-semibold">
          <span className="text-emerald-400">Yes {yPct}¢</span>
          <span className="text-red-400">No {100 - yPct}¢</span>
        </div>
        <div className="h-3 rounded-full bg-red-500/30 overflow-hidden">
          <div
            className="h-full rounded-full bg-emerald-500 transition-all"
            style={{ width: `${yPct}%` }}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-wrap gap-2">
      {outcomes.map((o) => (
        <Badge key={o.token_id} variant="outline" className="text-sm px-3 py-1">
          {o.outcome}: {fmtPct(o.price)}
        </Badge>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Full Orderbook Panel (expanded for detail page)
// ---------------------------------------------------------------------------

function DetailOrderbook({
  tokenId,
  outcome,
  wsState,
  onClose,
}: {
  tokenId: string
  outcome: string
  wsState: ReturnType<typeof usePolymarketWS>
  onClose: () => void
}) {
  const { t } = useI18n()
  const [book, setBook] = useState<PolymarketOrderbookData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      const res = await getPolymarketOrderbook(tokenId)
      if (!cancelled && res.data) setBook(res.data)
      setLoading(false)
    }
    if (tokenId) load()
    return () => {
      cancelled = true
    }
  }, [tokenId])

  const liveBook = wsState.books[tokenId]
  const displayBook = liveBook
    ? ({ ...book, bids: liveBook.bids, asks: liveBook.asks } as PolymarketOrderbookData)
    : book

  if (loading) {
    return <Skeleton className="h-60 w-full" />
  }
  if (!displayBook) {
    return (
      <p className="text-sm text-muted-foreground py-4 text-center">
        No orderbook data available
      </p>
    )
  }

  const bids = (displayBook.bids || []).slice(0, 12)
  const asks = (displayBook.asks || []).slice(0, 12)
  const maxBidSize = Math.max(...bids.map((b) => parseFloat(b.size)), 1)
  const maxAskSize = Math.max(...asks.map((a) => parseFloat(a.size)), 1)

  return (
    <Card className="border-primary/20">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <BookOpen className="h-4 w-4" />
            {outcome} — {t("polymarket.detail.orderbook")}
            {wsState.connected && (
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            )}
          </CardTitle>
          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="grid grid-cols-2 gap-4">
          {/* Bids */}
          <div>
            <div className="flex justify-between text-xs text-muted-foreground mb-2 px-1 font-medium">
              <span>{t("polymarket.detail.price")}</span>
              <span>{t("polymarket.detail.size")}</span>
            </div>
            <div className="space-y-0.5">
              {bids.map((b, i) => {
                const price = parseFloat(b.price)
                const size = parseFloat(b.size)
                const pct = (size / maxBidSize) * 100
                return (
                  <div key={i} className="flex justify-between px-1.5 py-1 relative rounded-sm">
                    <div
                      className="absolute inset-0 bg-emerald-500/10 rounded-sm"
                      style={{ width: `${pct}%` }}
                    />
                    <span className="relative text-emerald-400 font-mono text-xs">
                      {fmtPct(price)}
                    </span>
                    <span className="relative font-mono text-xs">{size.toFixed(1)}</span>
                  </div>
                )
              })}
              {bids.length === 0 && (
                <p className="text-xs text-muted-foreground text-center py-3">—</p>
              )}
            </div>
            <p className="text-[10px] text-emerald-500/70 font-medium mt-2 px-1">
              {t("polymarket.detail.bidSide")}
            </p>
          </div>

          {/* Asks */}
          <div>
            <div className="flex justify-between text-xs text-muted-foreground mb-2 px-1 font-medium">
              <span>{t("polymarket.detail.price")}</span>
              <span>{t("polymarket.detail.size")}</span>
            </div>
            <div className="space-y-0.5">
              {asks.map((a, i) => {
                const price = parseFloat(a.price)
                const size = parseFloat(a.size)
                const pct = (size / maxAskSize) * 100
                return (
                  <div key={i} className="flex justify-between px-1.5 py-1 relative rounded-sm">
                    <div
                      className="absolute inset-0 bg-red-500/10 rounded-sm right-0"
                      style={{ width: `${pct}%` }}
                    />
                    <span className="relative text-red-400 font-mono text-xs">
                      {fmtPct(price)}
                    </span>
                    <span className="relative font-mono text-xs">{size.toFixed(1)}</span>
                  </div>
                )
              })}
              {asks.length === 0 && (
                <p className="text-xs text-muted-foreground text-center py-3">—</p>
              )}
            </div>
            <p className="text-[10px] text-red-500/70 font-medium mt-2 px-1">
              {t("polymarket.detail.askSide")}
            </p>
          </div>
        </div>

        {/* Last trade */}
        {displayBook.last_trade_price && (
          <div className="flex items-center justify-center gap-2 mt-3 pt-3 border-t">
            <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">
              {t("polymarket.detail.lastTrade")}:
            </span>
            <span className="text-sm font-semibold font-mono">
              {fmtPct(parseFloat(displayBook.last_trade_price))}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Sub-market Card
// ---------------------------------------------------------------------------

function SubMarketCard({
  market,
  eventSlug,
  wsState,
}: {
  market: PolymarketSubMarket
  eventSlug: string
  wsState: ReturnType<typeof usePolymarketWS>
}) {
  const { t } = useI18n()
  const [selectedToken, setSelectedToken] = useState<{
    id: string
    outcome: string
  } | null>(null)

  function getPrice(o: PolymarketOutcome): number {
    return wsState.prices[o.token_id] ?? o.price
  }

  const marketUrl = market.slug
    ? `https://polymarket.com/event/${eventSlug}/${market.slug}`
    : `https://polymarket.com/event/${eventSlug}`

  return (
    <Card className="hover:border-primary/30 transition-colors">
      <CardContent className="p-4 space-y-4">
        {/* Market title (bilingual) */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <a
              href={marketUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="group"
            >
              <h3 className="text-sm font-semibold group-hover:text-primary transition-colors">
                {market.question_zh}
                <ExternalLink className="h-3 w-3 inline ml-1 opacity-0 group-hover:opacity-100 transition-opacity" />
              </h3>
            </a>
            <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1">
              <Globe2 className="h-3 w-3 shrink-0" />
              {market.question}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {market.active && !market.closed ? (
              <Badge variant="outline" className="text-[10px] text-emerald-400 border-emerald-500/30">
                {t("polymarket.detail.active")}
              </Badge>
            ) : (
              <Badge variant="outline" className="text-[10px] text-red-400 border-red-500/30">
                {t("polymarket.detail.closed")}
              </Badge>
            )}
          </div>
        </div>

        {/* Probability bar */}
        <ProbBar
          outcomes={market.outcomes.map((o) => ({
            ...o,
            price: getPrice(o),
          }))}
        />

        {/* Stats grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="rounded-lg bg-muted/40 p-2">
            <p className="text-muted-foreground">{t("polymarket.detail.totalVol")}</p>
            <p className="font-semibold">{fmtVol(market.volume)}</p>
          </div>
          <div className="rounded-lg bg-muted/40 p-2">
            <p className="text-muted-foreground">{t("polymarket.detail.vol24h")}</p>
            <p className="font-semibold">{fmtVol(market.volume_24h ?? 0)}</p>
          </div>
          <div className="rounded-lg bg-muted/40 p-2">
            <p className="text-muted-foreground">{t("polymarket.detail.liquidity")}</p>
            <p className="font-semibold">{fmtVol(market.liquidity)}</p>
          </div>
          <div className="rounded-lg bg-muted/40 p-2">
            <p className="text-muted-foreground">{t("polymarket.detail.spread")}</p>
            <p className="font-semibold">
              {market.spread != null ? `${(market.spread * 100).toFixed(1)}%` : "—"}
            </p>
          </div>
        </div>

        {/* Best bid / ask row */}
        {(market.best_bid != null || market.best_ask != null) && (
          <div className="flex items-center gap-4 text-xs">
            <span className="text-muted-foreground">{t("polymarket.detail.bestBid")}:</span>
            <span className="font-mono text-emerald-400">
              {market.best_bid ? fmtPct(market.best_bid) : "—"}
            </span>
            <span className="text-muted-foreground">{t("polymarket.detail.bestAsk")}:</span>
            <span className="font-mono text-red-400">
              {market.best_ask ? fmtPct(market.best_ask) : "—"}
            </span>
            {market.last_trade_price != null && market.last_trade_price > 0 && (
              <>
                <span className="text-muted-foreground">{t("polymarket.detail.lastTrade")}:</span>
                <span className="font-mono">{fmtPct(market.last_trade_price)}</span>
              </>
            )}
          </div>
        )}

        {/* Orderbook buttons */}
        <div className="flex items-center justify-between pt-1">
          <div className="flex gap-1.5 flex-wrap">
            {market.outcomes.map((o) => (
              <Button
                key={o.token_id}
                variant={selectedToken?.id === o.token_id ? "default" : "outline"}
                size="sm"
                className="text-xs h-7 px-3"
                onClick={() =>
                  setSelectedToken(
                    selectedToken?.id === o.token_id
                      ? null
                      : { id: o.token_id, outcome: o.outcome }
                  )
                }
              >
                <BookOpen className="h-3 w-3 mr-1" />
                {o.outcome} {t("polymarket.detail.orderbook")}
              </Button>
            ))}
          </div>
          <a
            href={marketUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            Polymarket <ExternalLink className="h-3.5 w-3.5" />
          </a>
        </div>

        {/* Expanded orderbook */}
        {selectedToken &&
          market.outcomes.some((o) => o.token_id === selectedToken.id) && (
            <DetailOrderbook
              tokenId={selectedToken.id}
              outcome={selectedToken.outcome}
              wsState={wsState}
              onClose={() => setSelectedToken(null)}
            />
          )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Main Event Detail Page
// ---------------------------------------------------------------------------

export default function PolymarketEventPage() {
  const { t } = useI18n()
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const paramId = params?.id as string
  const eventId = searchParams.get("id") || (paramId !== "placeholder" ? paramId : "")

  const [event, setEvent] = useState<PolymarketEvent | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchEvent = useCallback(async () => {
    if (!eventId) return
    setLoading(true)
    setError(null)
    const res = await getPolymarketEvent(eventId)
    if (res.error || !res.data) {
      setError(res.error ?? t("polymarket.detail.error"))
    } else {
      setEvent(res.data)
    }
    setLoading(false)
  }, [eventId, t])

  useEffect(() => {
    fetchEvent()
  }, [fetchEvent])

  const allTokenIds = useMemo(() => {
    if (!event) return []
    const ids: string[] = []
    for (const m of event.markets) {
      for (const o of m.outcomes) {
        if (o.token_id) ids.push(o.token_id)
      }
    }
    return ids
  }, [event])

  const wsState = usePolymarketWS(allTokenIds)

  // --- Loading skeleton ---
  if (loading) {
    return (
      <div className="space-y-5">
        <div className="flex items-center gap-3">
          <Skeleton className="h-8 w-8 rounded" />
          <Skeleton className="h-6 w-48" />
        </div>
        <Skeleton className="h-48 w-full rounded-xl" />
        <div className="grid grid-cols-2 gap-4">
          <Skeleton className="h-56 w-full rounded-xl" />
          <Skeleton className="h-56 w-full rounded-xl" />
        </div>
      </div>
    )
  }

  // --- Error state ---
  if (error || !event) {
    return (
      <div className="space-y-5">
        <Button variant="ghost" size="sm" onClick={() => router.push("/polymarket")}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          {t("polymarket.detail.back")}
        </Button>
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm text-destructive">
              {error || t("polymarket.detail.noData")}
            </p>
            <Button variant="outline" size="sm" className="mt-4" onClick={fetchEvent}>
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const polyUrl = `https://polymarket.com/event/${event.slug}`

  return (
    <div className="space-y-5">
      {/* ---- Navigation ---- */}
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={() => router.push("/polymarket")}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          {t("polymarket.detail.back")}
        </Button>
        <a
          href={polyUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
        >
          {t("polymarket.detail.viewOnPoly")}
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>

      {/* ---- Event Header ---- */}
      <Card>
        <CardContent className="p-5 space-y-4">
          <div className="flex items-start gap-4">
            {event.icon && (
              <img
                src={event.icon}
                alt=""
                className="h-14 w-14 rounded-xl object-cover shrink-0"
                onError={(e) => {
                  ;(e.target as HTMLImageElement).style.display = "none"
                }}
              />
            )}
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-bold leading-snug">{event.title_zh}</h1>
              <p className="text-sm text-muted-foreground mt-1 flex items-center gap-1.5">
                <Globe2 className="h-3.5 w-3.5 shrink-0" />
                {event.title}
              </p>
            </div>
            <div className="flex flex-col items-end gap-2 shrink-0">
              <Badge variant="outline" className="text-xs">
                {CATEGORY_ICONS[event.category] || "📋"} {event.category_zh}
              </Badge>
              {event.active && !event.closed ? (
                <Badge className="text-[10px] bg-emerald-500/20 text-emerald-400 border-emerald-500/30">
                  <CheckCircle2 className="h-3 w-3 mr-1" />
                  {t("polymarket.detail.active")}
                </Badge>
              ) : (
                <Badge className="text-[10px] bg-red-500/20 text-red-400 border-red-500/30">
                  {t("polymarket.detail.closed")}
                </Badge>
              )}
              {wsState.connected && (
                <Badge variant="outline" className="text-[10px] text-emerald-400 border-emerald-500/40 gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  WS Live
                </Badge>
              )}
            </div>
          </div>

          {/* Description */}
          {event.description && (
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground leading-relaxed">
                {event.description_zh || event.description}
              </p>
              {event.description_zh && event.description_zh !== event.description && (
                <p className="text-xs text-muted-foreground/60">{event.description}</p>
              )}
            </div>
          )}

          <Separator />

          {/* Stats grid */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <div className="rounded-lg bg-muted/40 p-3 space-y-1">
              <p className="text-[11px] text-muted-foreground flex items-center gap-1">
                <DollarSign className="h-3 w-3" />
                {t("polymarket.detail.totalVol")}
              </p>
              <p className="text-base font-bold">{fmtVol(event.volume)}</p>
            </div>
            <div className="rounded-lg bg-muted/40 p-3 space-y-1">
              <p className="text-[11px] text-muted-foreground flex items-center gap-1">
                <BarChart3 className="h-3 w-3" />
                {t("polymarket.detail.vol24h")}
              </p>
              <p className="text-base font-bold">{fmtVol(event.volume_24h)}</p>
            </div>
            <div className="rounded-lg bg-muted/40 p-3 space-y-1">
              <p className="text-[11px] text-muted-foreground flex items-center gap-1">
                <Activity className="h-3 w-3" />
                {t("polymarket.detail.liquidity")}
              </p>
              <p className="text-base font-bold">{fmtVol(event.liquidity)}</p>
            </div>
            <div className="rounded-lg bg-muted/40 p-3 space-y-1">
              <p className="text-[11px] text-muted-foreground flex items-center gap-1">
                <TrendingUp className="h-3 w-3" />
                {t("polymarket.detail.marketCount")}
              </p>
              <p className="text-base font-bold">{event.market_count}</p>
            </div>
            <div className="rounded-lg bg-muted/40 p-3 space-y-1">
              <p className="text-[11px] text-muted-foreground flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {t("polymarket.detail.endDate")}
              </p>
              <p className="text-sm font-semibold">{fmtDate(event.end_date)}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ---- Sub-Markets Section ---- */}
      <div className="space-y-3">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <BookOpen className="h-5 w-5" />
          {t("polymarket.detail.allMarkets")}
          <Badge variant="secondary" className="text-xs">
            {event.market_count}
          </Badge>
        </h2>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {event.markets.map((m) => (
            <SubMarketCard
              key={m.id || m.condition_id}
              market={m}
              eventSlug={event.slug}
              wsState={wsState}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
