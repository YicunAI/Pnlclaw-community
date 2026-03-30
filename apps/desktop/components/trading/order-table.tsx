"use client"

import { useEffect, useState } from "react"
import { getOrders, cancelOrder, type TradingOrder } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { useI18n } from "@/components/i18n/use-i18n"
import { cn } from "@/lib/utils"
import { X } from "lucide-react"

interface OrderTableProps {
  wsOrders: TradingOrder[]
}

const statusColor: Record<string, string> = {
  created: "text-yellow-500",
  accepted: "text-blue-500",
  partial: "text-orange-500",
  filled: "text-green-500",
  cancelled: "text-muted-foreground",
  rejected: "text-destructive",
}

export function OrderTable({ wsOrders }: OrderTableProps) {
  const { t } = useI18n()
  const [orders, setOrders] = useState<TradingOrder[]>([])

  useEffect(() => {
    getOrders().then((res) => {
      if (res.data) setOrders(res.data)
    })
  }, [])

  // Merge WS updates with REST snapshot
  const merged = [...wsOrders]
  for (const o of orders) {
    if (!merged.find((w) => w.id === o.id)) merged.push(o)
  }
  merged.sort((a, b) => b.created_at - a.created_at)

  async function handleCancel(orderId: string) {
    await cancelOrder(orderId)
  }

  const openStatuses = new Set(["created", "accepted", "partial"])

  return (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-xs">
            <th className="text-left py-2 px-2 font-medium">{t("trading.symbol")}</th>
            <th className="text-left py-2 px-2 font-medium">{t("trading.side")}</th>
            <th className="text-left py-2 px-2 font-medium">{t("trading.type")}</th>
            <th className="text-right py-2 px-2 font-medium">{t("trading.qty")}</th>
            <th className="text-right py-2 px-2 font-medium">{t("trading.price")}</th>
            <th className="text-right py-2 px-2 font-medium">{t("trading.filled")}</th>
            <th className="text-left py-2 px-2 font-medium">{t("trading.status")}</th>
            <th className="py-2 px-2"></th>
          </tr>
        </thead>
        <tbody>
          {merged.length === 0 && (
            <tr>
              <td colSpan={8} className="py-8 text-center text-muted-foreground text-xs">
                {t("trading.noOrders")}
              </td>
            </tr>
          )}
          {merged.map((o) => (
            <tr key={o.id} className="border-b border-border/50 hover:bg-muted/30">
              <td className="py-2 px-2 font-mono text-xs">{o.symbol}</td>
              <td className={cn("py-2 px-2 uppercase text-xs font-medium", o.side === "buy" ? "text-green-500" : "text-red-500")}>
                {o.side}
              </td>
              <td className="py-2 px-2 text-xs">{o.type}</td>
              <td className="py-2 px-2 text-right font-mono text-xs">{o.quantity}</td>
              <td className="py-2 px-2 text-right font-mono text-xs">{o.price ?? "-"}</td>
              <td className="py-2 px-2 text-right font-mono text-xs">{o.filled_quantity}</td>
              <td className={cn("py-2 px-2 text-xs capitalize", statusColor[o.status] || "")}>
                {o.status}
              </td>
              <td className="py-2 px-2">
                {openStatuses.has(o.status) && (
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => handleCancel(o.id)}>
                    <X className="h-3 w-3" />
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
