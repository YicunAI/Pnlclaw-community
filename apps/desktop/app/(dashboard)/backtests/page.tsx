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
import { Plus, TrendingUp, TrendingDown, BarChart3, Target, Activity, ArrowDownUp } from "lucide-react"
import {
  getBacktests,
  getStrategies,
  runBacktest,
  type BacktestData,
  type StrategyData,
} from "@/lib/api-client"

function EquityCurve({ curve }: { curve: number[] }) {
  if (curve.length < 2) return null

  const w = 600
  const h = 200
  const padX = 40
  const padY = 20
  const min = Math.min(...curve)
  const max = Math.max(...curve)
  const range = max - min || 1

  const path = curve
    .map((v, i) => {
      const x = padX + (i / (curve.length - 1)) * (w - padX * 2)
      const y = padY + (1 - (v - min) / range) * (h - padY * 2)
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(" ")

  const areaPath = `${path} L ${(w - padX).toFixed(1)} ${(h - padY).toFixed(1)} L ${padX.toFixed(1)} ${(h - padY).toFixed(1)} Z`
  const isProfit = curve[curve.length - 1] >= curve[0]

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full">
      {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
        const y = padY + pct * (h - padY * 2)
        const val = max - pct * range
        return (
          <g key={pct}>
            <line x1={padX} y1={y} x2={w - padX} y2={y} stroke="rgba(255,255,255,0.05)" />
            <text x={padX - 4} y={y + 4} textAnchor="end" fontSize={9} className="fill-muted-foreground">
              {val.toFixed(0)}
            </text>
          </g>
        )
      })}
      <defs>
        <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={isProfit ? "#10b981" : "#ef4444"} stopOpacity={0.3} />
          <stop offset="100%" stopColor={isProfit ? "#10b981" : "#ef4444"} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#eqGrad)" />
      <path d={path} fill="none" stroke={isProfit ? "#10b981" : "#ef4444"} strokeWidth={1.5} />
    </svg>
  )
}

function MetricCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string
  value: string
  icon: React.ComponentType<{ className?: string }>
  color?: string
}) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
      <Icon className={`h-4 w-4 ${color || "text-primary"}`} />
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className={`text-sm font-medium font-mono ${color || ""}`}>{value}</p>
      </div>
    </div>
  )
}

export default function BacktestsPage() {
  const [backtests, setBacktests] = useState<BacktestData[]>([])
  const [strategies, setStrategies] = useState<StrategyData[]>([])
  const [selected, setSelected] = useState<BacktestData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)

  const [newBt, setNewBt] = useState({
    strategy_id: "",
    data_path: "",
    initial_capital: "10000",
    commission_rate: "0.001",
  })

  const fetchData = useCallback(async () => {
    setLoading(true)
    const [bt, st] = await Promise.all([getBacktests(), getStrategies()])
    if (bt.data) setBacktests(Array.isArray(bt.data) ? bt.data : [])
    if (st.data) setStrategies(Array.isArray(st.data) ? st.data : [])
    if (bt.error && st.error) setError("API not reachable")
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleSubmit = async () => {
    const res = await runBacktest({
      strategy_id: newBt.strategy_id,
      data_path: newBt.data_path || undefined,
      initial_capital: parseFloat(newBt.initial_capital) || 10000,
      commission_rate: parseFloat(newBt.commission_rate) || 0.001,
    })
    if (!res.error) {
      setDialogOpen(false)
      fetchData()
    }
  }

  const mockEquityCurve = selected
    ? Array.from({ length: 100 }, (_, i) => {
        const base = 10000
        const ret = selected.total_return || 0
        const progress = i / 99
        const noise = Math.sin(i * 0.3) * base * 0.02
        return base + base * ret * progress + noise
      })
    : []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Backtests</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Run and analyze strategy backtests
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" /> New Backtest
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Run New Backtest</DialogTitle>
              <DialogDescription>Configure and run a backtest on a strategy</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">
                  Strategy
                </label>
                <select
                  value={newBt.strategy_id}
                  onChange={(e) =>
                    setNewBt({ ...newBt, strategy_id: e.target.value })
                  }
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="">Select strategy...</option>
                  {strategies.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">
                  Data File Path (optional)
                </label>
                <Input
                  placeholder="demo/data/btc_usdt_1h_90d.parquet"
                  value={newBt.data_path}
                  onChange={(e) =>
                    setNewBt({ ...newBt, data_path: e.target.value })
                  }
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Initial Capital
                  </label>
                  <Input
                    type="number"
                    value={newBt.initial_capital}
                    onChange={(e) =>
                      setNewBt({ ...newBt, initial_capital: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Commission Rate
                  </label>
                  <Input
                    type="number"
                    step="0.0001"
                    value={newBt.commission_rate}
                    onChange={(e) =>
                      setNewBt({ ...newBt, commission_rate: e.target.value })
                    }
                  />
                </div>
              </div>
              <Button onClick={handleSubmit} className="w-full">
                Run Backtest
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {error ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <p>{error}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-[350px_1fr] gap-6">
          <Card className="h-fit">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Backtest History</CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-14 w-full" />
                  ))}
                </div>
              ) : backtests.length === 0 ? (
                <p className="text-sm text-muted-foreground py-6 text-center">
                  No backtests yet
                </p>
              ) : (
                <div className="space-y-1">
                  {backtests.map((bt) => (
                    <button
                      key={bt.id}
                      onClick={() => setSelected(bt)}
                      className={`w-full text-left p-3 rounded-lg transition-colors ${
                        selected?.id === bt.id
                          ? "bg-primary/10 border border-primary/20"
                          : "hover:bg-muted"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">
                          {bt.strategy_name}
                        </span>
                        <Badge
                          variant={
                            bt.total_return >= 0 ? "success" : "destructive"
                          }
                        >
                          {(bt.total_return * 100).toFixed(1)}%
                        </Badge>
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {bt.total_trades} trades &middot;{" "}
                        {new Date(bt.created_at).toLocaleDateString()}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="space-y-4">
            {selected ? (
              <>
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      Equity Curve &mdash; {selected.strategy_name}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <EquityCurve curve={mockEquityCurve} />
                  </CardContent>
                </Card>

                <div className="grid grid-cols-3 gap-3">
                  <MetricCard
                    label="Total Return"
                    value={`${(selected.total_return * 100).toFixed(2)}%`}
                    icon={selected.total_return >= 0 ? TrendingUp : TrendingDown}
                    color={
                      selected.total_return >= 0
                        ? "text-emerald-400"
                        : "text-red-400"
                    }
                  />
                  <MetricCard
                    label="Sharpe Ratio"
                    value={selected.sharpe_ratio?.toFixed(2) ?? "-"}
                    icon={BarChart3}
                  />
                  <MetricCard
                    label="Max Drawdown"
                    value={`${((selected.max_drawdown ?? 0) * 100).toFixed(2)}%`}
                    icon={TrendingDown}
                    color="text-red-400"
                  />
                  <MetricCard
                    label="Win Rate"
                    value={`${((selected.win_rate ?? 0) * 100).toFixed(1)}%`}
                    icon={Target}
                  />
                  <MetricCard
                    label="Profit Factor"
                    value={selected.profit_factor?.toFixed(2) ?? "-"}
                    icon={Activity}
                  />
                  <MetricCard
                    label="Total Trades"
                    value={String(selected.total_trades ?? 0)}
                    icon={ArrowDownUp}
                  />
                </div>
              </>
            ) : (
              <Card>
                <CardContent className="py-16 text-center text-muted-foreground">
                  <BarChart3 className="h-10 w-10 mx-auto mb-3 opacity-30" />
                  <p>Select a backtest to view results</p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
