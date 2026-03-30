"use client"

import { useState } from "react"
import { placeOrder } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { useI18n } from "@/components/i18n/use-i18n"
import { cn } from "@/lib/utils"

export function OrderForm({ onOrderPlaced }: { onOrderPlaced?: () => void }) {
  const { t } = useI18n()
  const [symbol, setSymbol] = useState("BTC/USDT")
  const [side, setSide] = useState<"buy" | "sell">("buy")
  const [orderType, setOrderType] = useState<"market" | "limit" | "stop_market" | "stop_limit">("market")
  const [quantity, setQuantity] = useState("")
  const [price, setPrice] = useState("")
  const [stopPrice, setStopPrice] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const showPrice = orderType === "limit" || orderType === "stop_limit"
  const showStopPrice = orderType === "stop_market" || orderType === "stop_limit"

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)

    const params: Parameters<typeof placeOrder>[0] = {
      symbol,
      side,
      order_type: orderType,
      quantity: parseFloat(quantity),
    }
    if (showPrice && price) params.price = parseFloat(price)
    if (showStopPrice && stopPrice) params.stop_price = parseFloat(stopPrice)

    const res = await placeOrder(params)
    setLoading(false)

    if (res.error) {
      setError(res.error)
    } else {
      setQuantity("")
      setPrice("")
      setStopPrice("")
      onOrderPlaced?.()
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">{t("trading.symbol")}</Label>
          <Input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="BTC/USDT"
            className="h-9"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">{t("trading.type")}</Label>
          <Select
            className="h-9"
            value={orderType}
            onChange={(e) => setOrderType(e.target.value as typeof orderType)}
            options={[
              { value: "market", label: t("trading.market") },
              { value: "limit", label: t("trading.limit") },
              { value: "stop_market", label: t("trading.stopMarket") },
              { value: "stop_limit", label: t("trading.stopLimit") },
            ]}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">{t("trading.quantity")}</Label>
        <Input
          type="number"
          step="any"
          min="0"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          placeholder="0.001"
          className="h-9"
          required
        />
      </div>

      {showPrice && (
        <div className="space-y-1.5">
          <Label className="text-xs">{t("trading.price")}</Label>
          <Input
            type="number"
            step="any"
            min="0"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="60000"
            className="h-9"
          />
        </div>
      )}

      {showStopPrice && (
        <div className="space-y-1.5">
          <Label className="text-xs">{t("trading.stopPrice")}</Label>
          <Input
            type="number"
            step="any"
            min="0"
            value={stopPrice}
            onChange={(e) => setStopPrice(e.target.value)}
            placeholder="59000"
            className="h-9"
          />
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <Button
          type="submit"
          onClick={() => setSide("buy")}
          disabled={loading || !quantity}
          className={cn(
            "h-10 font-semibold",
            side === "buy" ? "bg-green-600 hover:bg-green-700" : ""
          )}
          variant={side === "buy" ? "default" : "outline"}
        >
          {t("trading.buy")}
        </Button>
        <Button
          type="submit"
          onClick={() => setSide("sell")}
          disabled={loading || !quantity}
          className={cn(
            "h-10 font-semibold",
            side === "sell" ? "bg-red-600 hover:bg-red-700" : ""
          )}
          variant={side === "sell" ? "default" : "outline"}
        >
          {t("trading.sell")}
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}
    </form>
  )
}
