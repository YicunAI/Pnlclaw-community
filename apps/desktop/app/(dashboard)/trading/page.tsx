"use client"

import { ModeToggle } from "@/components/trading/mode-toggle"
import { OrderForm } from "@/components/trading/order-form"
import { OrderTable } from "@/components/trading/order-table"
import { PositionPanel } from "@/components/trading/position-panel"
import { BalanceCard } from "@/components/trading/balance-card"
import { TradeHistory } from "@/components/trading/trade-history"
import { useTradingWS } from "@/lib/use-trading-ws"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Wifi, WifiOff } from "lucide-react"

export default function TradingPage() {
  const { connected, orders, positions, balances, fills } = useTradingWS()

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Trading</h1>
          <p className="text-sm text-muted-foreground">
            Place orders, track positions, and manage your portfolio
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-xs">
            {connected ? (
              <>
                <Wifi className="h-3 w-3 text-green-500" />
                <span className="text-green-500">Connected</span>
              </>
            ) : (
              <>
                <WifiOff className="h-3 w-3 text-muted-foreground" />
                <span className="text-muted-foreground">Disconnected</span>
              </>
            )}
          </div>
          <ModeToggle />
        </div>
      </div>

      <Separator />

      {/* Main grid */}
      <div className="grid grid-cols-12 gap-6">
        {/* Left column — Order Form + Balance + Positions */}
        <div className="col-span-4 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Place Order</CardTitle>
            </CardHeader>
            <CardContent>
              <OrderForm />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Balance</CardTitle>
            </CardHeader>
            <CardContent>
              <BalanceCard wsBalances={balances} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Positions</CardTitle>
            </CardHeader>
            <CardContent>
              <PositionPanel wsPositions={positions} />
            </CardContent>
          </Card>
        </div>

        {/* Right column — Orders + History */}
        <div className="col-span-8 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Orders</CardTitle>
            </CardHeader>
            <CardContent>
              <OrderTable wsOrders={orders} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Trade History</CardTitle>
            </CardHeader>
            <CardContent>
              <TradeHistory wsFills={fills} />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
