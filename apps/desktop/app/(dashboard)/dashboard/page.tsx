"use client"

import React, { useEffect, useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Activity,
  Wifi,
  WifiOff,
  Send,
  TrendingUp,
  TrendingDown,
  FlaskConical,
  Wallet,
} from "lucide-react"
import {
  checkHealth,
  getBacktests,
  getPaperAccounts,
  sendAgentChat,
  type BacktestData,
  type PaperAccountData,
} from "@/lib/api-client"

function StatusCard({
  label,
  value,
  ok,
}: {
  label: string
  value: string
  ok: boolean | null
}) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between p-4">
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-sm font-medium mt-1">{value}</p>
        </div>
        {ok === null ? (
          <Skeleton className="h-8 w-8 rounded-full" />
        ) : ok ? (
          <Wifi className="h-5 w-5 text-emerald-400" />
        ) : (
          <WifiOff className="h-5 w-5 text-red-400" />
        )}
      </CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const [apiOk, setApiOk] = useState<boolean | null>(null)
  const [backtests, setBacktests] = useState<BacktestData[]>([])
  const [accounts, setAccounts] = useState<PaperAccountData[]>([])
  const [loading, setLoading] = useState(true)

  const [chatInput, setChatInput] = useState("")
  const [chatMessages, setChatMessages] = useState<
    { role: "user" | "assistant"; content: string }[]
  >([])
  const [chatLoading, setChatLoading] = useState(false)

  useEffect(() => {
    async function load() {
      const health = await checkHealth()
      setApiOk(health.data?.status === "ok" || health.error === null)

      const bt = await getBacktests()
      if (bt.data) setBacktests(Array.isArray(bt.data) ? bt.data.slice(0, 5) : [])

      const acc = await getPaperAccounts()
      if (acc.data) setAccounts(Array.isArray(acc.data) ? acc.data : [])

      setLoading(false)
    }
    load()
  }, [])

  const handleChat = useCallback(async () => {
    if (!chatInput.trim() || chatLoading) return
    const msg = chatInput.trim()
    setChatInput("")
    setChatMessages((prev) => [...prev, { role: "user", content: msg }])
    setChatLoading(true)

    let response = ""
    await sendAgentChat(msg, (event) => {
      if (event.type === "text" || event.type === "content") {
        response += event.data
        setChatMessages((prev) => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last?.role === "assistant") {
            updated[updated.length - 1] = { ...last, content: response }
          } else {
            updated.push({ role: "assistant", content: response })
          }
          return updated
        })
      }
    })

    if (!response) {
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: "API not reachable. Start the local API server to use the AI assistant." },
      ])
    }
    setChatLoading(false)
  }, [chatInput, chatLoading])

  const totalPnl = accounts.reduce(
    (sum, a) => sum + (a.realized_pnl ?? 0) + (a.unrealized_pnl ?? 0),
    0
  )
  const totalBalance = accounts.reduce((sum, a) => sum + (a.balance ?? 0), 0)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-1">
          System overview and quick actions
        </p>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <StatusCard
          label="API Server"
          value={apiOk === null ? "Checking..." : apiOk ? "Connected" : "Offline"}
          ok={apiOk}
        />
        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="text-xs text-muted-foreground">Backtests</p>
              <p className="text-sm font-medium mt-1">
                {loading ? "..." : backtests.length}
              </p>
            </div>
            <FlaskConical className="h-5 w-5 text-primary" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="text-xs text-muted-foreground">Paper Balance</p>
              <p className="text-sm font-medium mt-1">
                {loading ? "..." : `$${totalBalance.toLocaleString()}`}
              </p>
            </div>
            <Wallet className="h-5 w-5 text-primary" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="text-xs text-muted-foreground">Total PnL</p>
              <p
                className={`text-sm font-medium mt-1 ${
                  totalPnl >= 0 ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {loading
                  ? "..."
                  : `${totalPnl >= 0 ? "+" : ""}$${totalPnl.toFixed(2)}`}
              </p>
            </div>
            {totalPnl >= 0 ? (
              <TrendingUp className="h-5 w-5 text-emerald-400" />
            ) : (
              <TrendingDown className="h-5 w-5 text-red-400" />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Recent Backtests</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : backtests.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                No backtests yet. Run your first one!
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Strategy</TableHead>
                    <TableHead>Return</TableHead>
                    <TableHead>Sharpe</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {backtests.map((bt) => (
                    <TableRow key={bt.id}>
                      <TableCell className="font-medium text-xs">
                        {bt.strategy_name}
                      </TableCell>
                      <TableCell
                        className={`text-xs ${
                          bt.total_return >= 0
                            ? "text-emerald-400"
                            : "text-red-400"
                        }`}
                      >
                        {(bt.total_return * 100).toFixed(1)}%
                      </TableCell>
                      <TableCell className="text-xs">
                        {bt.sharpe_ratio?.toFixed(2) ?? "-"}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            bt.status === "completed" ? "success" : "secondary"
                          }
                        >
                          {bt.status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Paper Accounts</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                {[1, 2].map((i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : accounts.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                No paper accounts. Create one to start!
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Balance</TableHead>
                    <TableHead>PnL</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {accounts.map((acc) => {
                    const pnl =
                      (acc.realized_pnl ?? 0) + (acc.unrealized_pnl ?? 0)
                    return (
                      <TableRow key={acc.id}>
                        <TableCell className="font-medium text-xs">
                          {acc.name}
                        </TableCell>
                        <TableCell className="text-xs">
                          ${acc.balance?.toLocaleString()}
                        </TableCell>
                        <TableCell
                          className={`text-xs ${
                            pnl >= 0 ? "text-emerald-400" : "text-red-400"
                          }`}
                        >
                          {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Activity className="h-4 w-4" />
            AI Assistant
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3 max-h-60 overflow-y-auto mb-3">
            {chatMessages.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-4">
                Ask about strategies, markets, or backtests...
              </p>
            )}
            {chatMessages.map((msg, i) => (
              <div
                key={i}
                className={`text-sm px-3 py-2 rounded-lg ${
                  msg.role === "user"
                    ? "bg-primary/10 text-primary ml-12"
                    : "bg-muted mr-12"
                }`}
              >
                {msg.content}
              </div>
            ))}
            {chatLoading && (
              <div className="flex gap-1 px-3 py-2">
                <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce" />
                <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce [animation-delay:150ms]" />
                <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce [animation-delay:300ms]" />
              </div>
            )}
          </div>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              handleChat()
            }}
          >
            <Input
              placeholder="Ask something..."
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              disabled={chatLoading}
              className="flex-1"
            />
            <Button type="submit" size="icon" disabled={chatLoading}>
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
