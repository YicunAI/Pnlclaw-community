"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import {
  Percent,
  Search,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  ChevronDown,
  ChevronUp,
  ArrowUpDown,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useI18n } from "@/components/i18n/use-i18n"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8080"

interface FundingRateRow {
  exchange: string
  symbol: string
  funding_rate: number
  mark_price: number
  index_price: number
  next_funding_time: number
  timestamp: number
}

type SortField = "symbol" | "funding_rate" | "mark_price" | "exchange" | "next_funding_time"
type SortDir = "asc" | "desc"

function formatRate(rate: number): string {
  return `${(rate * 100).toFixed(4)}%`
}

function formatPrice(price: number): string {
  if (price <= 0) return "—"
  if (price >= 10000) return price.toLocaleString(undefined, { maximumFractionDigits: 0 })
  if (price >= 1) return price.toLocaleString(undefined, { maximumFractionDigits: 2 })
  return price.toLocaleString(undefined, { maximumFractionDigits: 6 })
}

function formatCountdown(nextFunding: number): string {
  const diff = nextFunding - Date.now()
  if (diff <= 0) return "—"
  const h = Math.floor(diff / 3_600_000)
  const m = Math.floor((diff % 3_600_000) / 60_000)
  return `${h}h ${m}m`
}

export default function FundingRatePage() {
  const { t } = useI18n()
  const [rates, setRates] = useState<FundingRateRow[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [exchangeFilter, setExchangeFilter] = useState<"all" | "binance" | "okx">("all")
  const [sortField, setSortField] = useState<SortField>("funding_rate")
  const [sortDir, setSortDir] = useState<SortDir>("desc")

  const fetchRates = useCallback(async (force = false) => {
    try {
      const url = `${API_BASE}/api/v1/derivatives/funding-rates/all-exchanges?exchange=${exchangeFilter}${force ? "&force=true" : ""}`
      const resp = await fetch(url)
      const data = await resp.json()
      if (data.data?.rates) {
        setRates(data.data.rates)
      }
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [exchangeFilter])

  useEffect(() => {
    setLoading(true)
    void fetchRates()
    const interval = setInterval(() => void fetchRates(), 30_000)
    return () => clearInterval(interval)
  }, [fetchRates])

  const toggleSort = useCallback((field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortField(field)
      setSortDir(field === "funding_rate" ? "desc" : "asc")
    }
  }, [sortField])

  const filtered = useMemo(() => {
    let items = rates
    if (search) {
      const q = search.toUpperCase()
      items = items.filter((r) => r.symbol.toUpperCase().includes(q))
    }
    return items
  }, [rates, search])

  const sorted = useMemo(() => {
    const copy = [...filtered]
    copy.sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case "symbol":
          cmp = a.symbol.localeCompare(b.symbol)
          break
        case "funding_rate":
          cmp = a.funding_rate - b.funding_rate
          break
        case "mark_price":
          cmp = a.mark_price - b.mark_price
          break
        case "exchange":
          cmp = a.exchange.localeCompare(b.exchange)
          break
        case "next_funding_time":
          cmp = a.next_funding_time - b.next_funding_time
          break
      }
      return sortDir === "asc" ? cmp : -cmp
    })
    return copy
  }, [filtered, sortField, sortDir])

  const extremeCount = useMemo(
    () => rates.filter((r) => Math.abs(r.funding_rate) > 0.001).length,
    [rates],
  )
  const avgRate = useMemo(() => {
    if (rates.length === 0) return 0
    return rates.reduce((sum, r) => sum + r.funding_rate, 0) / rates.length
  }, [rates])

  const binanceCount = rates.filter((r) => r.exchange === "binance").length
  const okxCount = rates.filter((r) => r.exchange === "okx").length

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Percent className="h-6 w-6" />
            {t("funding.title")}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t("funding.subtitle")}
          </p>
        </div>
        <button
          onClick={() => { setLoading(true); void fetchRates(true) }}
          className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg bg-secondary hover:bg-secondary/80 transition-colors"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          {t("funding.refresh")}
        </button>
      </div>

      <Separator />

      <div className="grid grid-cols-4 gap-3">
        <Card className="border-0 bg-muted/40">
          <CardContent className="pt-4 pb-3 text-center">
            <div className="text-2xl font-bold font-mono">{rates.length}</div>
            <div className="text-xs text-muted-foreground">{t("funding.totalPairs")}</div>
          </CardContent>
        </Card>
        <Card className="border-0 bg-muted/40">
          <CardContent className="pt-4 pb-3 text-center">
            <div className={cn("text-2xl font-bold font-mono", avgRate > 0 ? "text-green-400" : "text-red-400")}>
              {formatRate(avgRate)}
            </div>
            <div className="text-xs text-muted-foreground">{t("funding.avgRate")}</div>
          </CardContent>
        </Card>
        <Card className="border-0 bg-yellow-500/10">
          <CardContent className="pt-4 pb-3 text-center">
            <div className="text-2xl font-bold font-mono text-yellow-400">{extremeCount}</div>
            <div className="text-xs text-muted-foreground">{t("funding.extremeCount")}</div>
          </CardContent>
        </Card>
        <Card className="border-0 bg-muted/40">
          <CardContent className="pt-4 pb-3 text-center">
            <div className="text-lg font-bold font-mono">
              <span className="text-yellow-400">{binanceCount}</span>
              <span className="text-muted-foreground mx-1">/</span>
              <span className="text-blue-400">{okxCount}</span>
            </div>
            <div className="text-xs text-muted-foreground">Binance / OKX</div>
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("funding.searchPlaceholder")}
            className="pl-9 h-9"
          />
        </div>
        <div className="flex gap-1">
          {(["all", "binance", "okx"] as const).map((ex) => (
            <button
              key={ex}
              onClick={() => setExchangeFilter(ex)}
              className={cn(
                "px-3 py-1.5 text-xs rounded-lg transition-colors",
                exchangeFilter === ex
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80",
              )}
            >
              {ex === "all" ? t("funding.allExchanges") : ex === "binance" ? "Binance" : "OKX"}
            </button>
          ))}
        </div>
        <div className="text-xs text-muted-foreground ml-auto">
          {t("funding.showing", { count: String(sorted.length), total: String(rates.length) })}
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="max-h-[calc(100vh-380px)] overflow-y-auto hover-scrollbar">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-card border-b z-10">
                <tr className="text-muted-foreground">
                  <th className="text-left px-3 py-2 font-medium w-10">#</th>
                  <SortHeader field="exchange" current={sortField} dir={sortDir} onClick={toggleSort}>
                    {t("funding.exchange")}
                  </SortHeader>
                  <SortHeader field="symbol" current={sortField} dir={sortDir} onClick={toggleSort}>
                    {t("funding.symbol")}
                  </SortHeader>
                  <SortHeader field="funding_rate" current={sortField} dir={sortDir} onClick={toggleSort} align="right">
                    {t("funding.rate")}
                  </SortHeader>
                  <SortHeader field="mark_price" current={sortField} dir={sortDir} onClick={toggleSort} align="right">
                    {t("funding.markPrice")}
                  </SortHeader>
                  <th className="text-right px-3 py-2 font-medium">{t("funding.indexPrice")}</th>
                  <SortHeader field="next_funding_time" current={sortField} dir={sortDir} onClick={toggleSort} align="right">
                    {t("funding.countdown")}
                  </SortHeader>
                </tr>
              </thead>
              <tbody>
                {loading && sorted.length === 0 ? (
                  <tr><td colSpan={7} className="text-center py-12 text-muted-foreground">{t("common.loading")}</td></tr>
                ) : sorted.length === 0 ? (
                  <tr><td colSpan={7} className="text-center py-12 text-muted-foreground">{t("funding.noData")}</td></tr>
                ) : (
                  sorted.map((r, i) => {
                    const isExtreme = Math.abs(r.funding_rate) > 0.001
                    const isPositive = r.funding_rate > 0
                    return (
                      <tr
                        key={`${r.exchange}:${r.symbol}`}
                        className={cn(
                          "border-b border-border/50 hover:bg-muted/30 transition-colors font-mono",
                          isExtreme && "bg-yellow-500/5",
                        )}
                      >
                        <td className="px-3 py-1.5 text-muted-foreground">{i + 1}</td>
                        <td className="px-3 py-1.5">
                          <span className={cn(
                            "inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold",
                            r.exchange === "binance" ? "bg-yellow-500/15 text-yellow-400" : "bg-blue-500/15 text-blue-400",
                          )}>
                            {r.exchange === "binance" ? "BN" : "OKX"}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 font-medium">{r.symbol}</td>
                        <td className={cn(
                          "px-3 py-1.5 text-right font-bold",
                          isExtreme ? "text-yellow-400" : isPositive ? "text-green-400" : "text-red-400",
                        )}>
                          {formatRate(r.funding_rate)}
                        </td>
                        <td className="px-3 py-1.5 text-right">{formatPrice(r.mark_price)}</td>
                        <td className="px-3 py-1.5 text-right">{formatPrice(r.index_price)}</td>
                        <td className="px-3 py-1.5 text-right text-muted-foreground">
                          {r.next_funding_time > 0 ? formatCountdown(r.next_funding_time) : "—"}
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function SortHeader({
  field,
  current,
  dir,
  onClick,
  align,
  children,
}: {
  field: SortField
  current: SortField
  dir: SortDir
  onClick: (f: SortField) => void
  align?: "left" | "right"
  children: React.ReactNode
}) {
  const isActive = current === field
  return (
    <th
      className={cn(
        "px-3 py-2 font-medium cursor-pointer select-none hover:text-foreground transition-colors",
        align === "right" ? "text-right" : "text-left",
        isActive && "text-foreground",
      )}
      onClick={() => onClick(field)}
    >
      <span className="inline-flex items-center gap-1">
        {children}
        {isActive ? (
          dir === "asc" ? (
            <ChevronUp className="h-3 w-3 text-primary" />
          ) : (
            <ChevronDown className="h-3 w-3 text-primary" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-20" />
        )}
      </span>
    </th>
  )
}
