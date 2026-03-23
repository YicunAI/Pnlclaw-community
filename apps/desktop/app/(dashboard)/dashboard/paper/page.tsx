"use client"

import React, { useEffect, useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogDescription,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Plus, TrendingUp, TrendingDown, Wallet } from "lucide-react"
import {
  getPaperAccounts,
  getPaperPositions,
  getPaperOrders,
  getPaperPnl,
  createPaperAccount,
  submitPaperOrder,
  type PaperAccountData,
  type PaperPositionData,
  type PaperOrderData,
} from "@/lib/api-client"

const ORDER_STATUS_COLORS: Record<string, "success" | "secondary" | "destructive" | "warning" | "default"> = {
  filled: "success",
  created: "secondary",
  accepted: "default",
  cancelled: "destructive",
}

export default function PaperPage() {
  const [accounts, setAccounts] = useState<PaperAccountData[]>([])
  const [selectedAccount, setSelectedAccount] = useState<string>("")
  const [positions, setPositions] = useState<PaperPositionData[]>([])
  const [orders, setOrders] = useState<PaperOrderData[]>([])
  const [pnl, setPnl] = useState<{ realized: number; unrealized: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [newAccount, setNewAccount] = useState({ name: "", balance: "10000" })

  const [orderForm, setOrderForm] = useState({
    symbol: "BTC/USDT",
    side: "buy",
    order_type: "market",
    quantity: "",
    price: "",
  })

  const fetchAccounts = useCallback(async () => {
    const res = await getPaperAccounts()
    if (res.data) {
      const list = Array.isArray(res.data) ? res.data : []
      setAccounts(list)
      if (list.length > 0 && !selectedAccount) {
        setSelectedAccount(list[0].id)
      }
    }
    if (res.error) setError("API not reachable")
    setLoading(false)
  }, [selectedAccount])

  const fetchAccountData = useCallback(async () => {
    if (!selectedAccount) return
    const [pos, ord, pnlRes] = await Promise.all([
      getPaperPositions(selectedAccount),
      getPaperOrders(selectedAccount),
      getPaperPnl(selectedAccount),
    ])
    if (pos.data) setPositions(Array.isArray(pos.data) ? pos.data : [])
    if (ord.data) setOrders(Array.isArray(ord.data) ? ord.data : [])
    if (pnlRes.data) setPnl(pnlRes.data)
  }, [selectedAccount])

  useEffect(() => {
    fetchAccounts()
  }, [fetchAccounts])

  useEffect(() => {
    fetchAccountData()
  }, [fetchAccountData])

  const handleCreateAccount = async () => {
    await createPaperAccount({
      name: newAccount.name || "Paper Account",
      balance: parseFloat(newAccount.balance) || 10000,
    })
    setCreateDialogOpen(false)
    setNewAccount({ name: "", balance: "10000" })
    fetchAccounts()
  }

  const handleSubmitOrder = async () => {
    if (!selectedAccount || !orderForm.quantity) return
    await submitPaperOrder({
      account_id: selectedAccount,
      symbol: orderForm.symbol,
      side: orderForm.side,
      order_type: orderForm.order_type,
      quantity: parseFloat(orderForm.quantity),
      price: orderForm.price ? parseFloat(orderForm.price) : undefined,
    })
    setOrderForm({ ...orderForm, quantity: "", price: "" })
    fetchAccountData()
  }

  const currentAccount = accounts.find((a) => a.id === selectedAccount)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Paper Trading</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Simulated trading environment
          </p>
        </div>
        <div className="flex gap-2 items-center">
          {accounts.length > 0 && (
            <select
              value={selectedAccount}
              onChange={(e) => setSelectedAccount(e.target.value)}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          )}
          <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
            <DialogTrigger asChild>
              <Button variant="outline">
                <Plus className="h-4 w-4 mr-2" /> New Account
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create Paper Account</DialogTitle>
                <DialogDescription>Set up a new simulated trading account</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Account Name
                  </label>
                  <Input
                    placeholder="My Paper Account"
                    value={newAccount.name}
                    onChange={(e) =>
                      setNewAccount({ ...newAccount, name: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Initial Balance (USDT)
                  </label>
                  <Input
                    type="number"
                    value={newAccount.balance}
                    onChange={(e) =>
                      setNewAccount({ ...newAccount, balance: e.target.value })
                    }
                  />
                </div>
                <Button onClick={handleCreateAccount} className="w-full">
                  Create Account
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {error ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <p>{error}</p>
          </CardContent>
        </Card>
      ) : loading ? (
        <div className="space-y-4">
          <Skeleton className="h-32" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-4">
            <Card>
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">Balance</p>
                <p className="text-lg font-bold font-mono mt-1">
                  ${currentAccount?.balance?.toLocaleString() ?? "0"}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground">Equity</p>
                <p className="text-lg font-bold font-mono mt-1">
                  ${currentAccount?.equity?.toLocaleString() ?? "0"}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">Realized PnL</p>
                  <p
                    className={`text-lg font-bold font-mono mt-1 ${
                      (pnl?.realized ?? 0) >= 0
                        ? "text-emerald-400"
                        : "text-red-400"
                    }`}
                  >
                    {(pnl?.realized ?? 0) >= 0 ? "+" : ""}$
                    {(pnl?.realized ?? 0).toFixed(2)}
                  </p>
                </div>
                {(pnl?.realized ?? 0) >= 0 ? (
                  <TrendingUp className="h-5 w-5 text-emerald-400" />
                ) : (
                  <TrendingDown className="h-5 w-5 text-red-400" />
                )}
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">Unrealized PnL</p>
                  <p
                    className={`text-lg font-bold font-mono mt-1 ${
                      (pnl?.unrealized ?? 0) >= 0
                        ? "text-emerald-400"
                        : "text-red-400"
                    }`}
                  >
                    {(pnl?.unrealized ?? 0) >= 0 ? "+" : ""}$
                    {(pnl?.unrealized ?? 0).toFixed(2)}
                  </p>
                </div>
                <Wallet className="h-5 w-5 text-primary" />
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-2 gap-6">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Positions</CardTitle>
              </CardHeader>
              <CardContent>
                {positions.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-4 text-center">
                    No open positions
                  </p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Symbol</TableHead>
                        <TableHead>Side</TableHead>
                        <TableHead>Qty</TableHead>
                        <TableHead>Entry</TableHead>
                        <TableHead>Current</TableHead>
                        <TableHead>PnL</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {positions.map((pos, i) => (
                        <TableRow key={i}>
                          <TableCell className="font-medium text-xs">
                            {pos.symbol}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={
                                pos.side === "long" ? "success" : "destructive"
                              }
                            >
                              {pos.side}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs font-mono">
                            {pos.quantity}
                          </TableCell>
                          <TableCell className="text-xs font-mono">
                            ${pos.entry_price?.toFixed(2)}
                          </TableCell>
                          <TableCell className="text-xs font-mono">
                            ${pos.current_price?.toFixed(2)}
                          </TableCell>
                          <TableCell
                            className={`text-xs font-mono ${
                              (pos.unrealized_pnl ?? 0) >= 0
                                ? "text-emerald-400"
                                : "text-red-400"
                            }`}
                          >
                            {(pos.unrealized_pnl ?? 0) >= 0 ? "+" : ""}$
                            {(pos.unrealized_pnl ?? 0).toFixed(2)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Orders</CardTitle>
              </CardHeader>
              <CardContent>
                {orders.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-4 text-center">
                    No orders yet
                  </p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Symbol</TableHead>
                        <TableHead>Side</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Qty</TableHead>
                        <TableHead>Price</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {orders.map((ord) => (
                        <TableRow key={ord.id}>
                          <TableCell className="font-medium text-xs">
                            {ord.symbol}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={
                                ord.side === "buy" ? "success" : "destructive"
                              }
                            >
                              {ord.side}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs">{ord.type}</TableCell>
                          <TableCell className="text-xs font-mono">
                            {ord.quantity}
                          </TableCell>
                          <TableCell className="text-xs font-mono">
                            {ord.price ? `$${ord.price.toFixed(2)}` : "-"}
                          </TableCell>
                          <TableCell>
                            <Badge variant={ORDER_STATUS_COLORS[ord.status] ?? "secondary"}>
                              {ord.status}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Quick Order</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-3 items-end">
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Symbol
                  </label>
                  <select
                    value={orderForm.symbol}
                    onChange={(e) =>
                      setOrderForm({ ...orderForm, symbol: e.target.value })
                    }
                    className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                  >
                    <option value="BTC/USDT">BTC/USDT</option>
                    <option value="ETH/USDT">ETH/USDT</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Side
                  </label>
                  <select
                    value={orderForm.side}
                    onChange={(e) =>
                      setOrderForm({ ...orderForm, side: e.target.value })
                    }
                    className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                  >
                    <option value="buy">Buy</option>
                    <option value="sell">Sell</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Type
                  </label>
                  <select
                    value={orderForm.order_type}
                    onChange={(e) =>
                      setOrderForm({
                        ...orderForm,
                        order_type: e.target.value,
                      })
                    }
                    className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                  >
                    <option value="market">Market</option>
                    <option value="limit">Limit</option>
                  </select>
                </div>
                <div className="flex-1">
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Quantity
                  </label>
                  <Input
                    type="number"
                    step="0.001"
                    placeholder="0.001"
                    value={orderForm.quantity}
                    onChange={(e) =>
                      setOrderForm({ ...orderForm, quantity: e.target.value })
                    }
                  />
                </div>
                {orderForm.order_type === "limit" && (
                  <div className="flex-1">
                    <label className="text-xs text-muted-foreground mb-1 block">
                      Price
                    </label>
                    <Input
                      type="number"
                      step="0.01"
                      placeholder="40000"
                      value={orderForm.price}
                      onChange={(e) =>
                        setOrderForm({ ...orderForm, price: e.target.value })
                      }
                    />
                  </div>
                )}
                <Button
                  onClick={handleSubmitOrder}
                  className={
                    orderForm.side === "buy"
                      ? "bg-emerald-600 hover:bg-emerald-700"
                      : "bg-red-600 hover:bg-red-700"
                  }
                >
                  {orderForm.side === "buy" ? "Buy" : "Sell"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
