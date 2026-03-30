"use client"

import { useEffect, useState } from "react"
import { getTradeHistory, type TradingFill } from "@/lib/api-client"
import { useI18n } from "@/components/i18n/use-i18n"

interface TradeHistoryProps {
  wsFills: TradingFill[]
}

export function TradeHistory({ wsFills }: TradeHistoryProps) {
  const { t } = useI18n()
  const [fills, setFills] = useState<TradingFill[]>([])

  useEffect(() => {
    getTradeHistory().then((res) => {
      if (res.data) setFills(res.data)
    })
  }, [])

  const merged = [...wsFills]
  for (const f of fills) {
    if (!merged.find((w) => w.id === f.id)) merged.push(f)
  }
  merged.sort((a, b) => b.timestamp - a.timestamp)

  return (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-xs">
            <th className="text-left py-2 px-2 font-medium">{t("trading.orderId")}</th>
            <th className="text-right py-2 px-2 font-medium">{t("trading.price")}</th>
            <th className="text-right py-2 px-2 font-medium">{t("trading.qty")}</th>
            <th className="text-right py-2 px-2 font-medium">{t("trading.fee")}</th>
            <th className="text-right py-2 px-2 font-medium">{t("trading.time")}</th>
          </tr>
        </thead>
        <tbody>
          {merged.length === 0 && (
            <tr>
              <td colSpan={5} className="py-8 text-center text-muted-foreground text-xs">
                {t("trading.noHistory")}
              </td>
            </tr>
          )}
          {merged.map((f) => (
            <tr key={f.id} className="border-b border-border/50 hover:bg-muted/30">
              <td className="py-2 px-2 font-mono text-xs text-muted-foreground">{f.order_id.slice(0, 12)}</td>
              <td className="py-2 px-2 text-right font-mono text-xs">{f.price.toFixed(2)}</td>
              <td className="py-2 px-2 text-right font-mono text-xs">{f.quantity}</td>
              <td className="py-2 px-2 text-right font-mono text-xs text-muted-foreground">
                {f.fee.toFixed(4)} {f.fee_currency}
              </td>
              <td className="py-2 px-2 text-right text-xs text-muted-foreground">
                {new Date(f.timestamp).toLocaleTimeString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
