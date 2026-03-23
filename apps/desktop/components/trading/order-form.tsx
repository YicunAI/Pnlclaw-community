"use client"

import { useState } from "react"
import { placeOrder } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"

export function OrderForm({ onOrderPlaced }: { onOrderPlaced?: () => void }) {
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
          <Label className="text-xs">Symbol</Label>
          <Input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="BTC/USDT"
            className="h-9"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">Type</Label>
          <Select value={orderType} onValueChange={(v) => setOrderType(v as typeof orderType)}>
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="market">Market</SelectItem>
              <SelectItem value="limit">Limit</SelectItem>
              <SelectItem value="stop_market">Stop Market</SelectItem>
              <SelectItem value="stop_limit">Stop Limit</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Quantity</Label>
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
          <Label className="text-xs">Price</Label>
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
          <Label className="text-xs">Stop Price</Label>
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
          Buy
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
          Sell
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}
    </form>
  )
}
