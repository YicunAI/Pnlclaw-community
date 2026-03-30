"use client"

import React, { useMemo, useState, useCallback, useRef } from "react"
import { createPortal } from "react-dom"
import { Skeleton } from "@/components/ui/skeleton"
import type { OrderbookData } from "@/lib/api-client"
import { useI18n } from "@/components/i18n/use-i18n"

function formatPrice(price: number): string {
  if (price >= 10000) return price.toFixed(1)
  if (price >= 100) return price.toFixed(2)
  if (price >= 1) return price.toFixed(3)
  if (price >= 0.01) return price.toFixed(4)
  return price.toFixed(6)
}

function formatQty(qty: number): string {
  if (qty >= 1000) return qty.toFixed(2)
  if (qty >= 1) return qty.toFixed(4)
  return qty.toFixed(5)
}

function formatUsdt(val: number): string {
  if (val >= 1_000_000) return (val / 1_000_000).toFixed(2) + "M"
  if (val >= 10_000) return (val / 1_000).toFixed(1) + "K"
  if (val >= 1_000) return (val / 1_000).toFixed(2) + "K"
  if (val >= 1) return val.toFixed(2)
  return val.toFixed(4)
}

interface OrderbookPanelProps {
  data: OrderbookData | null
  maxRows?: number
  title?: string
  baseCurrency?: string
  quoteCurrency?: string
}

interface DisplayRow {
  price: number
  qty: number
  levelUsdt: number
  cumUsdt: number
  cumQty: number
}

function buildDisplayRows(
  levels: { price: number; quantity: number }[],
  max: number,
): DisplayRow[] {
  const rows: DisplayRow[] = []
  let cumUsdt = 0
  let cumQty = 0
  for (let i = 0; i < Math.min(levels.length, max); i++) {
    const { price, quantity } = levels[i]
    const levelUsdt = price * quantity
    cumUsdt += levelUsdt
    cumQty += quantity
    rows.push({ price, qty: quantity, levelUsdt, cumUsdt, cumQty })
  }
  return rows
}

type HoverState = { side: "ask" | "bid"; displayIndex: number } | null

export function OrderbookPanel({
  data,
  maxRows = 15,
  title,
  baseCurrency,
  quoteCurrency = "USDT",
}: OrderbookPanelProps) {
  const { t } = useI18n()
  const [hover, setHover] = useState<HoverState>(null)
  // viewport-absolute position for the portal tooltip
  const [tipPos, setTipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const containerRef = useRef<HTMLDivElement>(null)

  const { askDisplayRows, bidDisplayRows, maxLevelUsdt } = useMemo(() => {
    if (!data) return { askDisplayRows: [], bidDisplayRows: [], maxLevelUsdt: 1 }

    const bidRows = buildDisplayRows(data.bids, maxRows)
    const askRows = buildDisplayRows(data.asks, maxRows)
    const askDisplay = [...askRows].reverse()

    const maxLvl = Math.max(
      ...bidRows.map((r) => r.levelUsdt),
      ...askRows.map((r) => r.levelUsdt),
      1,
    )
    return { askDisplayRows: askDisplay, bidDisplayRows: bidRows, maxLevelUsdt: maxLvl }
  }, [data, maxRows])

  const clearHover = useCallback(() => setHover(null), [])

  const handleRowHover = useCallback(
    (side: "ask" | "bid", displayIndex: number, e: React.MouseEvent) => {
      setHover({ side, displayIndex })
      const rowRect = (e.currentTarget as HTMLElement).getBoundingClientRect()
      setTipPos({
        x: rowRect.left,
        y: rowRect.top + rowRect.height / 2,
      })
    },
    [],
  )

  const hoverInfo = useMemo(() => {
    if (!hover) return null

    if (hover.side === "ask") {
      const rows = askDisplayRows
      const row = rows[hover.displayIndex]
      if (!row) return null
      let cumUsdt = 0
      let cumQty = 0
      for (let i = hover.displayIndex; i < rows.length; i++) {
        cumUsdt += rows[i].levelUsdt
        cumQty += rows[i].qty
      }
      const avgPrice = cumQty > 0 ? cumUsdt / cumQty : row.price
      return { avgPrice, levelUsdt: row.levelUsdt, cumUsdt }
    } else {
      const rows = bidDisplayRows
      const row = rows[hover.displayIndex]
      if (!row) return null
      const avgPrice = row.cumQty > 0 ? row.cumUsdt / row.cumQty : row.price
      return { avgPrice, levelUsdt: row.levelUsdt, cumUsdt: row.cumUsdt }
    }
  }, [hover, askDisplayRows, bidDisplayRows])

  const isAskHighlighted = useCallback(
    (i: number) => hover?.side === "ask" && i >= hover.displayIndex,
    [hover],
  )
  const isBidHighlighted = useCallback(
    (i: number) => hover?.side === "bid" && i <= hover.displayIndex,
    [hover],
  )

  const qtyLabel = baseCurrency
    ? `${t("markets.quantity")}(${baseCurrency})`
    : t("markets.quantity")
  const totalLabel = `${t("markets.total")}(${quoteCurrency})`
  const priceLabel = `${t("markets.price")}(${quoteCurrency})`

  return (
    <div ref={containerRef}>
      <h3 className="text-base font-semibold mb-3">{title ?? t("markets.orderBook")}</h3>
      {!data ? (
        <Skeleton className="h-48" />
      ) : (
        <div className="text-xs font-mono" onMouseLeave={clearHover}>
          <div className="grid grid-cols-3 text-muted-foreground px-1 pb-1 border-b border-border mb-0.5">
            <span>{priceLabel}</span>
            <span className="text-right">{qtyLabel}</span>
            <span className="text-right">{totalLabel}</span>
          </div>

          {askDisplayRows.map((row, i) => {
            const pct = (row.levelUsdt / maxLevelUsdt) * 100
            const highlighted = isAskHighlighted(i)
            return (
              <div
                key={`a-${i}`}
                className={`grid grid-cols-3 relative px-1 py-[3px] cursor-pointer transition-colors ${highlighted ? "bg-red-500/20" : "hover:bg-muted/30"}`}
                onMouseEnter={(e) => handleRowHover("ask", i, e)}
              >
                <div
                  className="absolute inset-y-0 right-0 bg-red-500/10 pointer-events-none"
                  style={{ width: `${pct}%` }}
                />
                <span className="text-red-400 relative z-10">{formatPrice(row.price)}</span>
                <span className="text-right relative z-10">{formatQty(row.qty)}</span>
                <span className="text-right relative z-10 text-muted-foreground">
                  {formatUsdt(row.cumUsdt)}
                </span>
              </div>
            )
          })}

          {askDisplayRows.length > 0 && bidDisplayRows.length > 0 && (
            <div className="flex items-center justify-center py-1 border-y border-border my-0.5 text-muted-foreground gap-2">
              <span className="text-sm font-semibold text-foreground">
                {formatPrice(askDisplayRows[askDisplayRows.length - 1].price)}
              </span>
              <span className="text-[10px]">
                ≈ ${askDisplayRows[askDisplayRows.length - 1].price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
          )}

          {bidDisplayRows.map((row, i) => {
            const pct = (row.levelUsdt / maxLevelUsdt) * 100
            const highlighted = isBidHighlighted(i)
            return (
              <div
                key={`b-${i}`}
                className={`grid grid-cols-3 relative px-1 py-[3px] cursor-pointer transition-colors ${highlighted ? "bg-emerald-500/20" : "hover:bg-muted/30"}`}
                onMouseEnter={(e) => handleRowHover("bid", i, e)}
              >
                <div
                  className="absolute inset-y-0 right-0 bg-emerald-500/10 pointer-events-none"
                  style={{ width: `${pct}%` }}
                />
                <span className="text-emerald-400 relative z-10">{formatPrice(row.price)}</span>
                <span className="text-right relative z-10">{formatQty(row.qty)}</span>
                <span className="text-right relative z-10 text-muted-foreground">
                  {formatUsdt(row.cumUsdt)}
                </span>
              </div>
            )
          })}
        </div>
      )}

      {/* Portal tooltip: rendered on document.body, immune to any parent overflow */}
      {hover && hoverInfo && typeof document !== "undefined" &&
        createPortal(
          <div
            className="fixed z-[9999] pointer-events-none"
            style={{
              left: `${tipPos.x - 8}px`,
              top: `${tipPos.y}px`,
              transform: "translate(-100%, -50%)",
            }}
          >
            <div className="bg-popover/95 backdrop-blur-sm border border-border rounded-md shadow-xl px-2.5 py-2 text-[11px] font-mono whitespace-nowrap space-y-1">
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">{t("markets.avgPrice")}</span>
                <span className="font-semibold">≈ {formatPrice(hoverInfo.avgPrice)}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">{t("markets.amount")} {quoteCurrency}</span>
                <span className="font-semibold">{formatUsdt(hoverInfo.levelUsdt)}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">{t("markets.total")} {quoteCurrency}</span>
                <span className="font-semibold">{formatUsdt(hoverInfo.cumUsdt)}</span>
              </div>
            </div>
          </div>,
          document.body,
        )
      }
    </div>
  )
}
