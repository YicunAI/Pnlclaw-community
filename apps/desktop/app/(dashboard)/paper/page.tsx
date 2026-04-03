"use client"

import Link from "next/link"
import React, { useEffect, useState, useCallback, useMemo, useRef } from "react"
import { RequireAuth } from "@/components/auth/require-auth"
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
import {
  Plus,
  TrendingUp,
  TrendingDown,
  Wallet,
  X,
  Bot,
  Loader2,
  ChevronDown,
  ChevronUp,
  Shield,
  Trash2,
  RotateCcw,
  Minus,
  Maximize2,
  Rocket,
  Activity,
} from "lucide-react"
import {
  getPaperAccounts,
  getPaperPositions,
  getPaperOrders,
  getPaperPnl,
  getPaperFills,
  getPaperSettings,
  updatePaperSettings,
  getStrategyDeployments,
  getStrategies,
  createPaperAccount,
  deletePaperAccount,
  abortAllPendingGets,
  resetPaperAccount,
  submitPaperOrder,
  closePaperPosition,
  cancelPaperOrder,
  getTicker,
  sendAgentChat,
  type PaperAccountData,
  type KlineData,
  type PaperPositionData,
  type PaperOrderData,
  type PaperFillData,
  type PaperSettings,
  type StrategyDeploymentData,
  type StrategyData,
  type MarginMode,
  type PositionSideType,
} from "@/lib/api-client"
import { useI18n } from "@/components/i18n/use-i18n"
import { useKlineHistory } from "@/lib/hooks/use-klines"
import { parseMarkdownToReact } from "@/components/agent-chat"
import CandlestickChart from "@/components/trading/candlestick-chart"
import type { TradeMarker } from "@/components/trading/candlestick-chart"
import { useMarketWS } from "@/lib/use-market-ws"
import { OrderTable } from "@/components/trading/order-table"
import { TradeHistory } from "@/components/trading/trade-history"
import { useDashboardRealtime } from "@/components/providers/dashboard-realtime-provider"
import { TickerPanel } from "@/components/trading/ticker-panel"
import { OrderbookPanel } from "@/components/trading/orderbook-panel"
import { PNLCurvePanel } from "@/components/trading/pnl-curve-panel"
import { usePaperWS, type StrategySignal } from "@/lib/use-paper-ws"

const LEVERAGE_OPTIONS = [1, 2, 3, 5, 10, 20, 50, 75, 100, 125]

const SYMBOLS = [
  { label: "BTC-USDT-SWAP", value: "BTC-USDT-SWAP", base: "BTC" },
  { label: "ETH-USDT-SWAP", value: "ETH-USDT-SWAP", base: "ETH" },
  { label: "SOL-USDT-SWAP", value: "SOL-USDT-SWAP", base: "SOL" },
]

const CHART_INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

type BottomTab = "positions" | "pending" | "filled" | "history" | "liveOrders" | "liveHistory"

export default function PaperPage() {
  const { t } = useI18n()
  const { trading: liveTrading } = useDashboardRealtime()

  const [accounts, setAccounts] = useState<PaperAccountData[]>([])
  const [selectedAccount, setSelectedAccount] = useState("")
  const selectedAccountRef = useRef("")
  const [positions, setPositions] = useState<PaperPositionData[]>([])
  const [orders, setOrders] = useState<PaperOrderData[]>([])
  const [fills, setFills] = useState<PaperFillData[]>([])
  const [deployments, setDeployments] = useState<StrategyDeploymentData[]>([])
  const [strategies, setStrategies] = useState<StrategyData[]>([])
  const [pnl, setPnl] = useState<{ realized: number; unrealized: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [newAccount, setNewAccount] = useState({ name: "", balance: "100000", type: "manual" as "strategy" | "agent" | "manual", strategy_id: "" })

  // Order form state
  const [symbol, setSymbol] = useState("BTC-USDT-SWAP")
  const [orderType, setOrderType] = useState<"market" | "limit">("limit")
  const [leverage, setLeverage] = useState(10)
  const [leverageInput, setLeverageInput] = useState("10")
  const [showLeveragePicker, setShowLeveragePicker] = useState(false)
  const [marginMode, setMarginMode] = useState<MarginMode>("cross")
  const [quantity, setQuantity] = useState("")
  const [price, setPrice] = useState("")
  const [markPrice, setMarkPrice] = useState<number | null>(null)
  const [orderError, setOrderError] = useState<string | null>(null)
  const [placing, setPlacing] = useState(false)

  // TP/SL
  const [showTpSl, setShowTpSl] = useState(false)
  const [tpPrice, setTpPrice] = useState("")
  const [slPrice, setSlPrice] = useState("")

  // Bottom tabs
  const [bottomTab, setBottomTab] = useState<BottomTab>("positions")

  // Fee settings dialog
  const [feeDialogOpen, setFeeDialogOpen] = useState(false)
  const [feeSettings, setFeeSettings] = useState<PaperSettings | null>(null)
  const [feeForm, setFeeForm] = useState({ maker: "0.02", taker: "0.05" })
  const [feeSaving, setFeeSaving] = useState(false)

  // AI panel — persisted per-symbol in localStorage
  const [showAiPanel, setShowAiPanel] = useState(false)
  const [aiPanelCollapsed, setAiPanelCollapsed] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiResult, setAiResult] = useState("")
  const [aiSavedAt, setAiSavedAt] = useState<number | null>(null)

  const [chartInterval, setChartInterval] = useState("1h")
  const [signalFeedOpen, setSignalFeedOpen] = useState(true)

  const currentSymbolInfo = useMemo(() => SYMBOLS.find(s => s.value === symbol), [symbol])
  const tickerSymbol = useMemo(() => symbol.replace("-SWAP", "").replace("-", "/"), [symbol])

  const {
    klines: klineHistory,
    isLoading: klineLoading,
    isLoadingMore,
    loadMore: handleLoadMoreKlines,
  } = useKlineHistory(tickerSymbol, chartInterval, "okx", "futures")

  const marketWS = useMarketWS({ symbol: tickerSymbol, exchange: "okx", marketType: "futures" })

  const paperWS = usePaperWS(selectedAccount || null)

  const hasRunningDeployment = useMemo(() => {
    return deployments.some(
      (d) => d.account_id === selectedAccount && d.status === "running",
    )
  }, [deployments, selectedAccount])

  const recentSignals = useMemo(
    () => paperWS.signals.slice(0, 10),
    [paperWS.signals],
  )

  const runnerSlot = paperWS.slotStatus

  // Initial mark price (one-shot REST), then WS takes over
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const res = await getTicker(tickerSymbol, { exchange: "okx", market_type: "futures" })
      if (!cancelled && res.data) {
        setMarkPrice(res.data.last_price)
        if (orderType === "limit" && !price) {
          setPrice(res.data.last_price.toString())
        }
      }
    })()
    return () => { cancelled = true }
  }, [tickerSymbol]) // eslint-disable-line react-hooks/exhaustive-deps

  // Real-time mark price from WS ticker
  useEffect(() => {
    if (marketWS.ticker?.last_price) {
      setMarkPrice(marketWS.ticker.last_price)
    }
  }, [marketWS.ticker?.last_price])

  const estimatedMargin = useMemo(() => {
    const qty = parseFloat(quantity)
    if (!qty || qty <= 0) return null
    return qty / leverage
  }, [quantity, leverage])

  const estimatedBaseQty = useMemo(() => {
    const qty = parseFloat(quantity)
    const px = orderType === "market" ? markPrice : parseFloat(price)
    if (!qty || !px || px <= 0) return null
    return qty / px
  }, [quantity, price, orderType, markPrice])

  const handleAccountSwitch = useCallback((accountId: string) => {
    if (accountId === selectedAccountRef.current) return
    selectedAccountRef.current = accountId
    setSelectedAccount(accountId)
    setPositions([])
    setOrders([])
    setFills([])
    setDeployments([])
    setPnl(null)
  }, [])

  // Data fetching
  const initialSelectDone = useRef(false)

  const fetchAccounts = useCallback(async () => {
    const [acctRes, allDepsRes] = await Promise.all([
      getPaperAccounts(),
      getStrategyDeployments(),
    ])
    if (acctRes.data) {
      const list = Array.isArray(acctRes.data) ? acctRes.data : []
      setAccounts(list)

      if (list.length > 0 && !initialSelectDone.current) {
        initialSelectDone.current = true
        const allDeps = Array.isArray(allDepsRes.data) ? allDepsRes.data : []
        const runningDep = allDeps.find((d: StrategyDeploymentData) => d.status === "running")
        if (runningDep?.account_id && list.some((a: PaperAccountData) => a.id === runningDep.account_id)) {
          handleAccountSwitch(runningDep.account_id)
        } else {
          const strategyAcct = list.find(
            (a: PaperAccountData) => a.account_type === "strategy"
          )
          handleAccountSwitch(strategyAcct?.id || list[0].id)
        }
      }
    }
    if (acctRes.error) setError(t("paper.apiUnreachable"))
    setLoading(false)
  }, [t, handleAccountSwitch])

  const fetchAccountData = useCallback(async () => {
    if (!selectedAccount) return
    const requestedAccount = selectedAccount
    const [pos, ord, pnlRes, fillsRes, deploymentRes] = await Promise.all([
      getPaperPositions(selectedAccount),
      getPaperOrders(selectedAccount),
      getPaperPnl(selectedAccount),
      getPaperFills(selectedAccount),
      getStrategyDeployments(selectedAccount),
    ])
    if (selectedAccountRef.current !== requestedAccount) return
    setPositions(Array.isArray(pos.data) ? pos.data : [])
    setOrders(Array.isArray(ord.data) ? ord.data : [])
    setFills(Array.isArray(fillsRes.data) ? fillsRes.data : [])
    setDeployments(Array.isArray(deploymentRes.data) ? deploymentRes.data : [])
    if (pnlRes.data) {
      const records = Array.isArray(pnlRes.data) ? pnlRes.data : []
      const aggregated = records.reduce(
        (acc: { realized: number; unrealized: number }, r: Record<string, number>) => ({
          realized: acc.realized + (r.realized_pnl ?? 0),
          unrealized: acc.unrealized + (r.unrealized_pnl ?? 0),
        }),
        { realized: 0, unrealized: 0 },
      )
      setPnl(aggregated)
    } else {
      setPnl(null)
    }
  }, [selectedAccount])

  useEffect(() => { fetchAccounts() }, [fetchAccounts])
  useEffect(() => { fetchAccountData() }, [fetchAccountData])
  useEffect(() => {
    getStrategies().then((res) => {
      if (res.data) setStrategies(Array.isArray(res.data) ? res.data : [])
    })
    return () => { abortAllPendingGets() }
  }, [])

  // WS-driven incremental state updates: merge into local state on every WS version bump
  useEffect(() => {
    if (paperWS.version === 0) return

    if (paperWS.account) {
      setAccounts((prev) => {
        const idx = prev.findIndex((a) => a.id === paperWS.account!.id)
        if (idx < 0) return prev
        const next = [...prev]
        next[idx] = { ...next[idx], ...paperWS.account }
        return next
      })
    }

    if (paperWS.fills.length > 0) {
      setFills((prev) => {
        const ids = new Set(prev.map((f) => f.id))
        const newFills = paperWS.fills.filter((f) => !ids.has(f.id))
        return newFills.length > 0 ? [...newFills, ...prev] : prev
      })
    }

    if (paperWS.orders.length > 0) {
      setOrders((prev) => {
        const next = [...prev]
        for (const wo of paperWS.orders) {
          const idx = next.findIndex((o) => o.id === wo.id)
          if (idx >= 0) next[idx] = wo
          else next.unshift(wo)
        }
        return next
      })
    }

    if (paperWS.positions.length > 0) {
      setPositions((prev) => {
        const next = [...prev]
        for (const wp of paperWS.positions) {
          const idx = next.findIndex(
            (p) => p.symbol === wp.symbol && (p.pos_side ?? p.side) === (wp.pos_side ?? wp.side),
          )
          if (idx >= 0) next[idx] = wp
          else next.push(wp)
        }
        return next
      })
    }
  }, [paperWS.version]) // eslint-disable-line react-hooks/exhaustive-deps

  // Re-fetch full state after manual actions (place order, close position, etc.)
  const refreshAfterAction = useCallback(async () => {
    await Promise.all([fetchAccountData(), fetchAccounts()])
  }, [fetchAccountData, fetchAccounts])

  // Merge REST history with WS live klines
  const chartData = useMemo(() => {
    const history = [...klineHistory]
    for (const wk of marketWS.klines) {
      const wsIvl = (wk as any).wsInterval
      if (wsIvl && wsIvl !== chartInterval) continue
      const existIdx = history.findIndex((h) => h.timestamp === wk.timestamp)
      if (existIdx >= 0) {
        history[existIdx] = wk
      } else if (history.length === 0 || wk.timestamp > history[history.length - 1].timestamp) {
        history.push(wk)
      }
    }
    return history
  }, [klineHistory, marketWS.klines, chartInterval])

  // Convert paper fills to chart markers (entry/exit signals)
  const chartMarkers: TradeMarker[] = useMemo(() => {
    return fills
      .filter((f) => f.symbol === symbol && f.timestamp)
      .map((f) => {
        const isEntry = !f.reduce_only
        const isLong = f.side === "buy"
        if (isEntry) {
          return {
            time: Math.floor(f.timestamp / 1000),
            position: isLong ? ("belowBar" as const) : ("aboveBar" as const),
            color: isLong ? "#10b981" : "#ef4444",
            shape: isLong ? ("arrowUp" as const) : ("arrowDown" as const),
            text: isLong ? t("paper.openLongBadge") : t("paper.openShortBadge"),
          }
        }
        const closingLong = f.pos_side === "long" || (f.side === "sell" && !f.pos_side)
        return {
          time: Math.floor(f.timestamp / 1000),
          position: closingLong ? ("aboveBar" as const) : ("belowBar" as const),
          color: closingLong ? "#f59e0b" : "#3b82f6",
          shape: "square" as const,
          text: closingLong ? t("paper.closeLongBadge") : t("paper.closeShortBadge"),
        }
      })
  }, [fills, symbol])

  const handleCreateAccount = async () => {
    const res = await createPaperAccount({
      name: newAccount.name || t("paper.title"),
      initial_balance: parseFloat(newAccount.balance) || 100000,
      account_type: newAccount.type,
      strategy_id: newAccount.type === "strategy" ? newAccount.strategy_id || undefined : undefined,
    })
    if (res.error) { setError(res.error); return }
    setCreateDialogOpen(false)
    setNewAccount({ name: "", balance: "100000", type: "manual", strategy_id: "" })
    fetchAccounts()
  }

  const handleDeleteAccount = async () => {
    if (!selectedAccount) return
    if (selectedAccount === "paper-default") {
      alert(t("paper.cannotDeleteDefault"))
      return
    }

    const accountName = accounts.find(a => a.id === selectedAccount)?.name || selectedAccount
    if (!confirm(t("paper.confirmDelete", { name: accountName }))) {
      return
    }

    try {
      abortAllPendingGets()
      const res = await deletePaperAccount(selectedAccount)
      if (res.error) {
        alert(`${t("paper.deleteFailed")}: ${res.error}`)
        return
      }
      alert(t("paper.deleteSuccess"))

      const otherAccounts = accounts.filter(a => a.id !== selectedAccount)
      setAccounts(otherAccounts)
      const nextAccount = otherAccounts.find(a => a.id === "paper-default") || otherAccounts[0]
      if (nextAccount) {
        handleAccountSwitch(nextAccount.id)
      } else {
        handleAccountSwitch("")
      }
    } catch (err) {
      alert(t("paper.networkError"))
    }
  }

  const [resetCounter, setResetCounter] = useState(0)

  const handleResetAccount = async () => {
    if (!selectedAccount) return
    const accountName = accounts.find(a => a.id === selectedAccount)?.name || selectedAccount
    
    if (!confirm(t("paper.confirmReset", { name: accountName }))) {
      return
    }

    try {
      abortAllPendingGets()
      const res = await resetPaperAccount(selectedAccount)
      if (res.error) {
        alert(`${t("paper.resetFailed")}: ${res.error}`)
        return
      }

      setPositions([])
      setOrders([])
      setFills([])
      setPnl(null)
      paperWS.clearSignals()
      paperWS.setEquityHistory([])
      setResetCounter(c => c + 1)

      alert(t("paper.resetSuccess"))
      refreshAfterAction()
    } catch (err) {
      alert(t("paper.networkError"))
    }
  }

  const handlePlaceOrder = async (posSide: PositionSideType) => {
    if (!selectedAccount || !quantity) return
    setOrderError(null)
    setPlacing(true)

    const side = posSide === "long" ? "buy" : "sell"
    const px = orderType === "limit" ? parseFloat(price) : undefined

    if (orderType === "limit" && (!px || px <= 0)) {
      setOrderError(t("paper.enterValidPrice"))
      setPlacing(false)
      return
    }

    const res = await submitPaperOrder({
      account_id: selectedAccount,
      symbol,
      side,
      order_type: orderType,
      quantity: parseFloat(quantity),
      price: px,
      leverage,
      margin_mode: marginMode,
      pos_side: posSide,
      mark_price: markPrice ?? undefined,
      tp_price: tpPrice ? parseFloat(tpPrice) : undefined,
      sl_price: slPrice ? parseFloat(slPrice) : undefined,
    })

    setPlacing(false)

    if (res.error) {
      setOrderError(res.error)
      return
    }
    setQuantity("")
    setTpPrice("")
    setSlPrice("")
    refreshAfterAction()
  }

  const handleClosePosition = async (pos: PaperPositionData) => {
    if (!selectedAccount) return
    const res = await closePaperPosition({
      account_id: selectedAccount,
      symbol: pos.symbol,
      pos_side: pos.pos_side ?? "long",
      mark_price: markPrice ?? undefined,
    })
    if (res.error) {
      setOrderError(res.error)
      return
    }
    refreshAfterAction()
  }

  const handleCancelOrder = async (orderId: string) => {
    try {
      const res = await cancelPaperOrder(orderId)
      if (res.error) {
        setError(`${t("paper.cancelFailed")}: ${res.error}`)
        return
      }
      refreshAfterAction()
    } catch (err: any) {
      setError(`${t("paper.cancelFailed")}: ${err.message}`)
    }
  }

  const fetchFeeSettings = useCallback(async () => {
    if (!selectedAccount) return
    const res = await getPaperSettings(selectedAccount)
    if (res.data) {
      setFeeSettings(res.data)
      setFeeForm({
        maker: ((res.data.maker_fee_rate ?? 0.0002) * 100).toFixed(3),
        taker: ((res.data.taker_fee_rate ?? 0.0005) * 100).toFixed(3),
      })
    }
  }, [selectedAccount])

  useEffect(() => { fetchFeeSettings() }, [fetchFeeSettings])

  const aiStorageKey = `pnlclaw_ai_analysis_${symbol}`

  useEffect(() => {
    try {
      const raw = localStorage.getItem(aiStorageKey)
      if (raw) {
        const data = JSON.parse(raw) as { result: string; timestamp: number }
        if (data.result) {
          setAiResult(data.result)
          setAiSavedAt(data.timestamp)
          setShowAiPanel(true)
        }
      } else {
        setAiResult("")
        setAiSavedAt(null)
        setShowAiPanel(false)
      }
    } catch { /* ignore corrupted data */ }
  }, [aiStorageKey])

  const prevAiLoading = useRef(true)
  useEffect(() => {
    if (prevAiLoading.current && !aiLoading && aiResult) {
      const now = Date.now()
      setAiSavedAt(now)
      try {
        localStorage.setItem(aiStorageKey, JSON.stringify({ result: aiResult, timestamp: now }))
      } catch { /* quota exceeded — non-critical */ }
    }
    prevAiLoading.current = aiLoading
  }, [aiLoading, aiResult, aiStorageKey])

  const handleClearAiAnalysis = useCallback(() => {
    setAiResult("")
    setAiSavedAt(null)
    setShowAiPanel(false)
    try { localStorage.removeItem(aiStorageKey) } catch {}
  }, [aiStorageKey])

  const handleSaveFees = async () => {
    setFeeSaving(true)
    const makerRate = parseFloat(feeForm.maker) / 100
    const takerRate = parseFloat(feeForm.taker) / 100
    await updatePaperSettings({
      account_id: selectedAccount,
      maker_fee_rate: makerRate,
      taker_fee_rate: takerRate,
    })
    await fetchFeeSettings()
    setFeeSaving(false)
    setFeeDialogOpen(false)
  }

  const handleAiAnalysis = async (customTimeframe?: string) => {
    setAiLoading(true)
    if (!customTimeframe) {
      setAiResult("")
    } else {
      setAiResult(prev => prev + `\n\n---\n> **系统提示：** \n> 您选择了 **${customTimeframe}** 级别。\n\n`)
    }
    setShowAiPanel(true)

    const activePositions = positions.filter(p => p.symbol === symbol && (p.quantity ?? 0) > 0)
    const positionPayload = activePositions.map(p => ({
      symbol: p.symbol,
      pos_side: p.pos_side ?? p.side,
      side: p.side,
      leverage: p.leverage,
      margin: p.margin,
      quantity_base: p.quantity_base,
      avg_entry_price: p.avg_entry_price ?? p.entry_price,
      unrealized_pnl: p.unrealized_pnl,
      quantity: p.quantity,
    }))

    let intent: string
    let label: string
    if (customTimeframe === "平仓") {
      intent = "close_evaluation"
      label = `评估 ${symbol} 平仓`
    } else if (customTimeframe) {
      intent = "timeframe_trade"
      label = `分析 ${symbol} ${customTimeframe} 级别`
    } else {
      intent = "multi_timeframe_analysis"
      label = `分析 ${symbol} 多周期行情`
    }

    let text = aiResult + (customTimeframe ? `\n\n---\n> **系统提示：** \n> 您选择了 **${customTimeframe}** 级别。\n\n` : "")
    if (!customTimeframe) text = ""

    try {
      await sendAgentChat(label, (event) => {
        if (event.type === "text_delta") {
          const chunk = typeof event.data === "object" && event.data !== null && "text" in event.data 
            ? (event.data as any).text 
            : typeof event.data === "string" ? event.data : ""
          text += chunk
          setAiResult(text)
        } else if (event.type === "thinking") {
          const chunk = typeof event.data === "object" && event.data !== null && "content" in event.data
            ? (event.data as any).content
            : typeof event.data === "string" ? event.data : ""
          if (chunk) {
            text += chunk
            setAiResult(text)
          }
        } else if (event.type === "error") {
          text += `\n**[Error]**: ${event.data}`
          setAiResult(text)
        }
      }, {
        intent,
        symbol: tickerSymbol,
        exchange: "okx",
        market_type: "futures",
        contract_symbol: symbol,
        timeframe: customTimeframe === "平仓" ? "15m" : (customTimeframe || "1h"),
        mark_price: markPrice ?? undefined,
        positions: positionPayload,
      })
    } catch {
      setAiResult(t("paper.aiUnavailable"))
    }
    setAiLoading(false)
  }

  const currentAccount = accounts.find((a) => a.id === selectedAccount)
  const latestDeployment = useMemo(
    () => deployments.find((deployment) => deployment.account_id === selectedAccount) ?? null,
    [deployments, selectedAccount]
  )
  const strategyNameById = useMemo(
    () => Object.fromEntries(strategies.map((strategy) => [strategy.id, strategy.name])),
    [strategies]
  )
  const availableBalance = currentAccount?.current_balance ?? currentAccount?.balance ?? 0
  const walletBalance = (currentAccount?.initial_balance ?? 0) + (currentAccount?.total_realized_pnl ?? 0) - (currentAccount?.total_fee ?? 0)
  const maxQuantity = availableBalance * leverage
  const netRealizedPnl = (currentAccount?.total_realized_pnl ?? 0) - (currentAccount?.total_fee ?? 0)
  const initBal = currentAccount?.initial_balance ?? 0

  const openPositions = useMemo(() => positions.filter(p => p.quantity > 0), [positions])
  const pendingOrders = useMemo(() => orders.filter(o => o.status === "accepted" || o.status === "created" || o.status === "partial"), [orders])
  const filledOrders = useMemo(() => orders.filter(o => o.status === "filled"), [orders])

  // Real-time unrealized PnL: current symbol uses WS markPrice, others use REST current_price
  const liveUnrealizedPnl = useMemo(() => {
    let total = 0
    for (const pos of openPositions) {
      const isCurrentSymbol = pos.symbol === symbol
      const price = isCurrentSymbol && markPrice ? markPrice : (pos.current_price ?? 0)
      if (price <= 0 || pos.avg_entry_price <= 0) {
        total += pos.unrealized_pnl ?? 0
        continue
      }
      const entryPrice = pos.avg_entry_price ?? pos.entry_price ?? 0
      const baseQty = pos.quantity_base ?? (entryPrice > 0 ? pos.quantity / entryPrice : 0)
      if (baseQty <= 0) {
        total += pos.unrealized_pnl ?? 0
        continue
      }
      const dir = pos.pos_side === "net" || !pos.pos_side ? pos.side : pos.pos_side
      const isLong = dir === "long" || dir === "buy"
      total += isLong
        ? (price - entryPrice) * baseQty
        : (entryPrice - price) * baseQty
    }
    return total
  }, [openPositions, symbol, markPrice])

  const totalEquity = walletBalance + liveUnrealizedPnl
  const totalReturnPct = initBal > 0 ? ((totalEquity - initBal) / initBal) * 100 : 0
  const realizedReturnPct = initBal > 0 ? (netRealizedPnl / initBal) * 100 : 0
  const unrealizedReturnPct = initBal > 0 ? (liveUnrealizedPnl / initBal) * 100 : 0

  const tabCounts: Record<BottomTab, number> = {
    positions: openPositions.length,
    pending: pendingOrders.length,
    filled: filledOrders.length,
    history: fills.length,
    liveOrders: liveTrading.orders.length,
    liveHistory: liveTrading.fills.length,
  }

  return (
    <RequireAuth>
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("paper.title")}</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {t("paper.descSwap")}
          </p>
        </div>
        <div className="flex gap-2 items-center">
          {accounts.length > 0 && (
            <select
              value={selectedAccount}
              onChange={(e) => handleAccountSwitch(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              {accounts.map((a) => {
                const typeTag = a.account_type === "strategy" ? "⚙️ " : a.account_type === "agent" ? "🤖 " : ""
                return <option key={a.id} value={a.id}>{typeTag}{a.name}</option>
              })}
            </select>
          )}
          {selectedAccount && (
            <div className="flex gap-1 items-center">
              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 p-0 text-muted-foreground hover:text-primary transition-colors"
                onClick={handleResetAccount}
                title={t("paper.resetAccount")}
              >
                <RotateCcw className="h-4 w-4" />
              </Button>
              {selectedAccount !== "paper-default" && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-9 w-9 p-0 text-muted-foreground hover:text-destructive transition-colors"
                  onClick={handleDeleteAccount}
                  title={t("paper.deleteAccount")}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </div>
          )}
          <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm">
                <Plus className="h-4 w-4 mr-1" /> {t("paper.newAccount")}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{t("paper.createAccount")}</DialogTitle>
                <DialogDescription>{t("paper.createAccountDesc")}</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">{t("paper.accountType") || "Account Type"}</label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {([
                      { key: "manual" as const, label: t("paper.typeManual") || "Manual", icon: "🎮" },
                      { key: "strategy" as const, label: t("paper.typeStrategy") || "Strategy", icon: "⚙️" },
                      { key: "agent" as const, label: t("paper.typeAgent") || "Agent (Soon)", icon: "🤖", disabled: true },
                    ]).map((opt) => (
                      <button
                        key={opt.key}
                        type="button"
                        disabled={opt.disabled}
                        onClick={() => setNewAccount({ ...newAccount, type: opt.key })}
                        className={`flex flex-col items-center gap-1 rounded-lg border p-2 text-xs transition-colors ${
                          newAccount.type === opt.key
                            ? "border-primary bg-primary/10 text-foreground"
                            : "border-border text-muted-foreground hover:border-primary/40"
                        } ${opt.disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}
                      >
                        <span className="text-lg">{opt.icon}</span>
                        <span className="font-medium">{opt.label}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {newAccount.type === "strategy" && strategies.length > 0 && (
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">{t("paper.linkedStrategy") || "Linked Strategy"}</label>
                    <select
                      value={newAccount.strategy_id}
                      onChange={(e) => setNewAccount({ ...newAccount, strategy_id: e.target.value })}
                      className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                    >
                      <option value="">{t("paper.selectStrategy") || "Select a strategy..."}</option>
                      {strategies.map((s) => (
                        <option key={s.id} value={s.id}>{s.name} (v{s.version})</option>
                      ))}
                    </select>
                  </div>
                )}

                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">{t("paper.accountName")}</label>
                  <Input
                    placeholder={t("paper.accountPlaceholder")}
                    value={newAccount.name}
                    onChange={(e) => setNewAccount({ ...newAccount, name: e.target.value })}
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">{t("paper.initialBalance")}</label>
                  <Input
                    type="number"
                    value={newAccount.balance}
                    onChange={(e) => setNewAccount({ ...newAccount, balance: e.target.value })}
                  />
                </div>
                <Button onClick={handleCreateAccount} className="w-full">{t("paper.create")}</Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {latestDeployment && (
        <div className="rounded-xl border border-border/60 bg-card/80 overflow-hidden">
          {/* Strategy header row */}
          <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border/30">
            <div className="flex items-center gap-2">
              {latestDeployment.status === "running" ? (
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-green-500" />
                </span>
              ) : (
                <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/40" />
              )}
              <Rocket className="h-4 w-4 text-primary" />
            </div>
            <div className="flex items-center gap-2 min-w-0 flex-1 flex-wrap">
              <span className="text-sm font-semibold truncate">
                {strategyNameById[latestDeployment.strategy_id] ?? latestDeployment.strategy_id}
              </span>
              <Badge variant="outline" className="text-[10px]">v{latestDeployment.strategy_version}</Badge>
              <Badge variant={latestDeployment.status === "running" ? "default" : "secondary"} className="text-[10px]">
                {latestDeployment.status === "running" ? t("runner.running") : latestDeployment.status}
              </Badge>
              {paperWS.connected && (
                <Badge variant="outline" className="text-[9px] gap-1 border-green-500/30">
                  <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                  WS
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <Button asChild size="sm" variant="ghost" className="h-7 text-xs">
                <Link href={`/strategies/${latestDeployment.strategy_id}/studio`}>
                  {t("runner.viewInStudio")}
                </Link>
              </Button>
              <Button asChild size="sm" variant="ghost" className="h-7 text-xs">
                <Link href="/strategies?tab=deployments">
                  {t("paper.deployHistory")}
                </Link>
              </Button>
            </div>
          </div>

          {/* Live metrics row - 3Commas style */}
          {latestDeployment.status === "running" && (
            <div className="grid grid-cols-5 gap-0 divide-x divide-border/30">
              <div className="px-3 py-2 text-center">
                <div className="text-[10px] text-muted-foreground">{t("runner.barCount")}</div>
                <div className="text-sm font-mono font-semibold">{runnerSlot?.bar_count ?? "—"}</div>
              </div>
              <div className="px-3 py-2 text-center">
                <div className="text-[10px] text-muted-foreground">{t("runner.signalCount")}</div>
                <div className="text-sm font-mono font-semibold">{runnerSlot?.signals_emitted ?? "—"}</div>
              </div>
              <div className="px-3 py-2 text-center">
                <div className="text-[10px] text-muted-foreground">{t("runner.orderCount")}</div>
                <div className="text-sm font-mono font-semibold">{runnerSlot?.orders_placed ?? "—"}</div>
              </div>
              <div className="px-3 py-2 text-center">
                <div className="text-[10px] text-muted-foreground">{t("runner.position")}</div>
                <div className={`text-sm font-mono font-semibold ${
                  runnerSlot?.position === "long" ? "text-green-400" :
                  runnerSlot?.position === "short" ? "text-red-400" : ""
                }`}>
                  {runnerSlot?.position ?? "—"}
                </div>
              </div>
              <div className="px-3 py-2 text-center">
                <div className="text-[10px] text-muted-foreground">{t("runner.errors")}</div>
                <div className={`text-sm font-mono font-semibold ${(runnerSlot?.errors ?? 0) > 0 ? "text-red-400" : ""}`}>
                  {runnerSlot?.errors ?? "0"}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {latestDeployment && latestDeployment.status === "running" && (
        <div className="rounded-lg border border-border/50 bg-card/50 overflow-hidden">
          <button
            type="button"
            onClick={() => setSignalFeedOpen(!signalFeedOpen)}
            className="flex w-full items-center gap-2 px-3 py-2 text-xs hover:bg-muted/30 transition-colors"
          >
            <Activity className="h-3.5 w-3.5 text-primary" />
            <span className="font-medium">{t("runner.signalFeed")}</span>
            {paperWS.connected && (
              <span className="ml-1 h-1.5 w-1.5 rounded-full bg-green-500" />
            )}
            <span className="ml-auto text-muted-foreground">
              {recentSignals.length > 0
                ? `${recentSignals.length} ${t("runner.signals")}`
                : t("runner.noSignals")}
            </span>
            {signalFeedOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>
          {signalFeedOpen && (
            <div className="border-t border-border/30 px-3 py-2">
              {recentSignals.length === 0 ? (
                <p className="py-3 text-center text-[11px] text-muted-foreground">{t("runner.waitingForSignals")}</p>
              ) : (
                <div className="max-h-40 overflow-y-auto space-y-1">
                  {recentSignals.map((sig, i) => {
                    const s = typeof sig.signal === "object" ? sig.signal : { side: "", reason: String(sig.signal) }
                    const isBuy = s.side?.toLowerCase().includes("buy")
                    return (
                      <div key={`${sig.ts}-${i}`} className="flex items-center gap-2 text-[11px]">
                        <span className="text-muted-foreground w-16 shrink-0">
                          {new Date(sig.ts).toLocaleTimeString()}
                        </span>
                        <Badge variant={isBuy ? "default" : "destructive"} className="text-[9px] px-1.5 py-0">
                          {isBuy ? "BUY" : "SELL"}
                        </Badge>
                        <span className="truncate text-muted-foreground">{s.reason || "-"}</span>
                      </div>
                    )
                  })}
                </div>
              )}
              <div className="mt-2 text-right">
                <Button
                  asChild
                  size="sm"
                  variant="ghost"
                  className="h-6 text-[10px] px-2"
                >
                  <Link href={`/strategies/${latestDeployment.strategy_id}/studio`}>
                    {t("runner.viewInStudio")}
                  </Link>
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {error ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <p>{error}</p>
          </CardContent>
        </Card>
      ) : loading ? (
        <div className="space-y-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <>
          {/* Account Stats Row */}
          <div className="grid grid-cols-5 gap-3">
            <Card className="border-border/50">
              <CardContent className="p-3">
                <p className="text-xs text-muted-foreground">{t("paper.availableBalance")}</p>
                <p className="text-lg font-bold font-mono mt-0.5">
                  {availableBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} <span className="text-xs text-muted-foreground">USDT</span>
                </p>
              </CardContent>
            </Card>
            <Card className="border-border/50">
              <CardContent className="p-3">
                <p className="text-xs text-muted-foreground">{t("paper.accountEquity")}</p>
                <p className="text-lg font-bold font-mono mt-0.5">
                  {totalEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} <span className="text-xs text-muted-foreground">USDT</span>
                </p>
                {initBal > 0 && (
                  <p className={`text-xs font-mono mt-0.5 ${totalReturnPct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {totalReturnPct >= 0 ? "+" : ""}{totalReturnPct.toFixed(2)}%
                  </p>
                )}
              </CardContent>
            </Card>
            <Card className="border-border/50">
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">{t("paper.netRealizedPnl")}</p>
                  <p className={`text-lg font-bold font-mono mt-0.5 ${netRealizedPnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {netRealizedPnl >= 0 ? "+" : ""}{netRealizedPnl.toFixed(2)} <span className="text-xs">USDT</span>
                  </p>
                  {initBal > 0 && (
                    <p className={`text-xs font-mono mt-0.5 ${realizedReturnPct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {realizedReturnPct >= 0 ? "+" : ""}{realizedReturnPct.toFixed(2)}%
                    </p>
                  )}
                </div>
                {netRealizedPnl >= 0
                  ? <TrendingUp className="h-4 w-4 text-emerald-400" />
                  : <TrendingDown className="h-4 w-4 text-red-400" />}
              </CardContent>
            </Card>
            <Card className="border-border/50">
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">{t("paper.unrealizedPnl")}</p>
                  <p className={`text-lg font-bold font-mono mt-0.5 ${liveUnrealizedPnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {liveUnrealizedPnl >= 0 ? "+" : ""}{liveUnrealizedPnl.toFixed(2)} <span className="text-xs">USDT</span>
                  </p>
                  {initBal > 0 && (
                    <p className={`text-xs font-mono mt-0.5 ${unrealizedReturnPct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {unrealizedReturnPct >= 0 ? "+" : ""}{unrealizedReturnPct.toFixed(2)}%
                    </p>
                  )}
                </div>
                {liveUnrealizedPnl >= 0
                  ? <TrendingUp className="h-4 w-4 text-emerald-400" />
                  : <TrendingDown className="h-4 w-4 text-red-400" />}
              </CardContent>
            </Card>
            <Card className="border-border/50">
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">{t("paper.totalFees")}</p>
                  <p className="text-lg font-bold font-mono mt-0.5 text-amber-400">
                    {(currentAccount?.total_fee ?? 0).toFixed(2)} <span className="text-xs">USDT</span>
                  </p>
                </div>
                <Dialog open={feeDialogOpen} onOpenChange={setFeeDialogOpen}>
                  <DialogTrigger asChild>
                    <button className="text-xs text-primary hover:text-primary/80 cursor-pointer">
                      {t("paper.feeBtn")}
                    </button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>{t("paper.feeSettingsTitle")}</DialogTitle>
                      <DialogDescription>{t("paper.feeSettingsDesc")}</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                      <div>
                        <label className="text-xs text-muted-foreground mb-1 block">{t("paper.makerFee")}</label>
                        <Input
                          type="number"
                          step="0.001"
                          value={feeForm.maker}
                          onChange={(e) => setFeeForm({ ...feeForm, maker: e.target.value })}
                        />
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground mb-1 block">{t("paper.takerFee")}</label>
                        <Input
                          type="number"
                          step="0.001"
                          value={feeForm.taker}
                          onChange={(e) => setFeeForm({ ...feeForm, taker: e.target.value })}
                        />
                      </div>
                      <Button onClick={handleSaveFees} className="w-full" disabled={feeSaving}>
                        {feeSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : t("paper.save")}
                      </Button>
                    </div>
                  </DialogContent>
                </Dialog>
              </CardContent>
            </Card>
          </div>

          {/* Main Trading Panel */}
          <div className="grid grid-cols-12 gap-3 items-stretch">
            {/* Left: Order Form */}
            <div className="col-span-3">
              <Card className="border-border/50 h-full">
                <CardContent className="p-4 space-y-3">
                  {/* Equity Curve above order form */}
                  {selectedAccount && (
                    <div className="pb-2 border-b border-border/50 -mt-1">
                      <PNLCurvePanel
                        accountId={selectedAccount}
                        noWrapper
                        compact
                        wsEquityPoints={paperWS.equityPoints}
                        onHistoryLoaded={paperWS.setEquityHistory}
                        liveEquity={walletBalance + liveUnrealizedPnl}
                        initialBalance={currentAccount?.initial_balance}
                        refreshTrigger={resetCounter}
                      />
                    </div>
                  )}

                  {/* Symbol */}
                  <select
                    value={symbol}
                    onChange={(e) => { setSymbol(e.target.value); setPrice("") }}
                    className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm font-medium"
                  >
                    {SYMBOLS.map((s) => (
                      <option key={s.value} value={s.value}>{s.label}</option>
                    ))}
                  </select>

                  {/* Mark Price */}
                  {markPrice && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">{t("paper.markPrice")}</span>
                      <span className="font-mono font-medium text-primary">
                        {markPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })} USDT
                      </span>
                    </div>
                  )}

                  {/* Margin Mode */}
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => setMarginMode("cross")}
                      className={`flex-1 h-7 rounded text-xs font-medium transition-colors ${
                        marginMode === "cross"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground hover:bg-muted/80"
                      }`}
                    >
                      {t("paper.crossMargin")}
                    </button>
                    <button
                      onClick={() => setMarginMode("isolated")}
                      className={`flex-1 h-7 rounded text-xs font-medium transition-colors ${
                        marginMode === "isolated"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground hover:bg-muted/80"
                      }`}
                    >
                      {t("paper.isolatedMargin")}
                    </button>
                  </div>

                  {/* Leverage */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-muted-foreground">{t("paper.leverage")}</span>
                      <button
                        onClick={() => setShowLeveragePicker(!showLeveragePicker)}
                        className="text-xs font-mono font-bold text-primary hover:text-primary/80 cursor-pointer"
                      >
                        {leverage}x
                      </button>
                    </div>
                    {showLeveragePicker && (
                      <div className="space-y-2 mb-2">
                        <div className="flex flex-wrap gap-1">
                          {LEVERAGE_OPTIONS.map((lv) => (
                            <button
                              key={lv}
                              onClick={() => { setLeverage(lv); setLeverageInput(String(lv)); setShowLeveragePicker(false) }}
                              className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                                leverage === lv
                                  ? "bg-primary text-primary-foreground"
                                  : "bg-muted text-muted-foreground hover:bg-muted/80"
                              }`}
                            >
                              {lv}x
                            </button>
                          ))}
                        </div>
                        <div className="flex gap-1">
                          <Input
                            type="number"
                            min={1}
                            max={125}
                            value={leverageInput}
                            onChange={(e) => setLeverageInput(e.target.value)}
                            className="h-7 text-xs font-mono"
                            placeholder={t("paper.customPlaceholder")}
                          />
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 text-xs px-2"
                            onClick={() => {
                              const v = Math.min(125, Math.max(1, parseInt(leverageInput) || 1))
                              setLeverage(v)
                              setLeverageInput(String(v))
                              setShowLeveragePicker(false)
                            }}
                          >
                            {t("paper.confirm")}
                          </Button>
                        </div>
                      </div>
                    )}
                    {!showLeveragePicker && (
                      <input
                        type="range"
                        min={1}
                        max={125}
                        value={leverage}
                        onChange={(e) => { setLeverage(Number(e.target.value)); setLeverageInput(e.target.value) }}
                        className="w-full h-1 accent-primary cursor-pointer"
                      />
                    )}
                  </div>

                  {/* Order Type */}
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => setOrderType("limit")}
                      className={`flex-1 h-7 rounded text-xs font-medium transition-colors ${
                        orderType === "limit"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground hover:bg-muted/80"
                      }`}
                    >
                      {t("paper.limit")}
                    </button>
                    <button
                      onClick={() => setOrderType("market")}
                      className={`flex-1 h-7 rounded text-xs font-medium transition-colors ${
                        orderType === "market"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground hover:bg-muted/80"
                      }`}
                    >
                      {t("paper.market")}
                    </button>
                  </div>

                  {/* Price */}
                  {orderType === "limit" ? (
                    <div>
                      <label className="text-xs text-muted-foreground mb-1 block">{t("paper.priceLabel")}</label>
                      <Input
                        type="number"
                        step="0.01"
                        placeholder={markPrice ? markPrice.toString() : t("paper.enterPrice")}
                        value={price}
                        onChange={(e) => setPrice(e.target.value)}
                        className="font-mono h-9"
                      />
                    </div>
                  ) : (
                    <div className="h-9 flex items-center justify-center rounded-md border border-input bg-muted/50 text-xs text-muted-foreground">
                      {t("paper.marketFill")}
                    </div>
                  )}

                  {/* Quantity */}
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">{t("paper.qtyLabel")}</label>
                    <Input
                      type="number"
                      step="1"
                      min={1}
                      placeholder={t("paper.enterQty")}
                      value={quantity}
                      onChange={(e) => setQuantity(e.target.value)}
                      className="font-mono h-9"
                    />
                    <div className="flex gap-1.5 mt-1">
                      {[10, 25, 50, 100].map((pct) => (
                        <button
                          key={pct}
                          onClick={() => setQuantity(Math.floor(maxQuantity * pct / 100).toString())}
                          className="flex-1 h-5 rounded text-[10px] bg-muted text-muted-foreground hover:bg-muted/80 transition-colors"
                        >
                          {pct}%
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* TP/SL Toggle */}
                  <div>
                    <button
                      onClick={() => setShowTpSl(!showTpSl)}
                      className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <Shield className="h-3 w-3" />
                      {t("paper.tpsl")}
                      <ChevronDown className={`h-3 w-3 transition-transform ${showTpSl ? "rotate-180" : ""}`} />
                    </button>
                    {showTpSl && (
                      <div className="mt-1.5 space-y-1.5">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-emerald-400 w-6 shrink-0">TP</span>
                          <Input
                            type="number"
                            step="0.01"
                            placeholder={t("paper.tpPrice")}
                            value={tpPrice}
                            onChange={(e) => setTpPrice(e.target.value)}
                            className="h-7 text-xs font-mono"
                          />
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-red-400 w-6 shrink-0">SL</span>
                          <Input
                            type="number"
                            step="0.01"
                            placeholder={t("paper.slPrice")}
                            value={slPrice}
                            onChange={(e) => setSlPrice(e.target.value)}
                            className="h-7 text-xs font-mono"
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Order Info */}
                  <div className="space-y-0.5 text-xs">
                    {estimatedBaseQty && (
                      <div className="flex justify-between text-muted-foreground">
                        <span>{t("paper.baseQty", { base: currentSymbolInfo?.base ?? "" })}</span>
                        <span className="font-mono">{estimatedBaseQty.toFixed(6)}</span>
                      </div>
                    )}
                    {estimatedMargin !== null && (
                      <div className="flex justify-between text-muted-foreground">
                        <span>{t("paper.requiredMargin")}</span>
                        <span className="font-mono">{estimatedMargin.toFixed(2)} USDT</span>
                      </div>
                    )}
                    <div className="flex justify-between text-muted-foreground">
                      <span>{t("paper.maxOpen")}</span>
                      <span className="font-mono">{maxQuantity.toLocaleString(undefined, { maximumFractionDigits: 0 })} USDT</span>
                    </div>
                  </div>

                  {/* Buy/Sell */}
                  <div className="grid grid-cols-2 gap-2">
                    <Button
                      onClick={() => handlePlaceOrder("long")}
                      disabled={!quantity || parseFloat(quantity) <= 0 || placing}
                      className="bg-emerald-600 hover:bg-emerald-700 text-white font-medium h-10"
                    >
                      {placing ? <Loader2 className="h-4 w-4 animate-spin" /> : <><TrendingUp className="h-4 w-4 mr-1" />{t("paper.openLong")}</>}
                    </Button>
                    <Button
                      onClick={() => handlePlaceOrder("short")}
                      disabled={!quantity || parseFloat(quantity) <= 0 || placing}
                      className="bg-red-600 hover:bg-red-700 text-white font-medium h-10"
                    >
                      {placing ? <Loader2 className="h-4 w-4 animate-spin" /> : <><TrendingDown className="h-4 w-4 mr-1" />{t("paper.openShort")}</>}
                    </Button>
                  </div>

                  {orderError && (
                    <p className="text-xs text-destructive">{orderError}</p>
                  )}

                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full text-xs"
                    onClick={() => handleAiAnalysis()}
                    disabled={aiLoading}
                  >
                    {aiLoading ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Bot className="h-3 w-3 mr-1" />}
                    {t("paper.aiAnalysis")}
                  </Button>
                </CardContent>
              </Card>
            </div>

              {/* Right: Chart + AI + Tabs */}
            <div className="col-span-9 space-y-3">
              {/* Chart + Ticker/Orderbook row */}
              <div className="grid grid-cols-[1fr_280px] gap-3 items-stretch">
                {/* Candlestick Chart */}
                <Card className="border-border/50 flex flex-col">
                  <div className="flex items-center justify-between px-4 py-2 border-b border-border/50">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-medium text-muted-foreground mr-1">{t("paper.kline")}</span>
                      {CHART_INTERVALS.map((ivl) => (
                        <button
                          key={ivl}
                          onClick={() => setChartInterval(ivl)}
                          className={`px-2 py-0.5 rounded text-[11px] font-mono transition-colors ${
                            chartInterval === ivl
                              ? "bg-primary text-primary-foreground font-bold"
                              : "text-muted-foreground hover:text-foreground hover:bg-muted/80"
                          }`}
                        >
                          {ivl}
                        </button>
                      ))}
                    </div>
                    <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                      {marketWS.connected ? (
                        <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />{t("paper.wsLive")}</span>
                      ) : (
                        <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-amber-400" />{t("paper.wsConnecting")}</span>
                      )}
                    </div>
                  </div>
                  <CardContent className="p-0 flex-1">
                    <div className="h-full min-h-[420px] relative">
                      <CandlestickChart
                        data={chartData}
                        interval={chartInterval}
                        markers={chartMarkers}
                        onLoadMore={handleLoadMoreKlines}
                        isLoadingMore={isLoadingMore}
                      />
                      {klineLoading && klineHistory.length === 0 && (
                        <div className="absolute inset-0 z-20 flex items-center justify-center bg-background/80">
                          <Skeleton className="h-full w-full" />
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>

                {/* Ticker + Orderbook Sidebar */}
                <div className="flex flex-col gap-3">
                  <Card className="border-border/50 shrink-0">
                    <CardContent className="p-4">
                      <TickerPanel ticker={marketWS.ticker} />
                    </CardContent>
                  </Card>
                  <Card className="border-border/50 flex-1 flex flex-col overflow-hidden">
                    <CardContent className="p-4 flex-1 overflow-y-auto">
                      <OrderbookPanel data={marketWS.orderbook} maxRows={25} baseCurrency={currentSymbolInfo?.base} />
                    </CardContent>
                  </Card>
                </div>
              </div>

              {/* AI Panel (expandable) */}
              {showAiPanel && (
                <Card className="border-border/50 border-primary/30 flex flex-col shadow-lg overflow-hidden">
                  <CardHeader className="pb-2 pt-3 px-4 flex flex-row items-center justify-between border-b border-border/50">
                    <div className="flex items-center gap-2">
                      <Bot className="h-4 w-4 text-primary" />
                      <CardTitle className="text-sm font-bold bg-gradient-to-r from-primary to-blue-400 bg-clip-text text-transparent">
                        {t("paper.aiTitle")} ({symbol})
                      </CardTitle>
                      {aiLoading && <Loader2 className="h-3 w-3 animate-spin text-primary ml-1" />}
                      {!aiLoading && aiSavedAt && (
                        <span className="text-[10px] text-muted-foreground ml-1">
                          {new Date(aiSavedAt).toLocaleString()}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={handleClearAiAnalysis}
                        className="text-muted-foreground hover:text-destructive hover:bg-destructive/10 p-1 rounded-md transition-colors"
                        title={t("paper.clearAnalysis")}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                      <button 
                        onClick={() => setAiPanelCollapsed(!aiPanelCollapsed)} 
                        className="text-muted-foreground hover:bg-muted p-1 rounded-md transition-colors"
                        title={aiPanelCollapsed ? "Expand" : "Collapse"}
                      >
                        {aiPanelCollapsed ? <Maximize2 className="h-4 w-4" /> : <Minus className="h-4 w-4" />}
                      </button>
                      <button onClick={() => setShowAiPanel(false)} className="text-muted-foreground hover:bg-muted p-1 rounded-md transition-colors">
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  </CardHeader>
                  
                  {!aiPanelCollapsed && (
                    <CardContent className="px-4 py-4 flex-1 flex flex-col">
                      <div className="flex-1 bg-muted/20 rounded-lg p-3 max-h-[400px] overflow-y-auto hover-scrollbar">
                        {aiResult ? (
                          <div className="text-sm space-y-2 text-foreground/90">
                            {parseMarkdownToReact(aiResult, aiLoading)}
                          </div>
                        ) : (
                          <div className="flex flex-col items-center justify-center h-24 text-muted-foreground space-y-3">
                            <Loader2 className="h-6 w-6 animate-spin text-primary/50" />
                            <p className="text-xs">{t("paper.aiLoadingDesc")}</p>
                          </div>
                        )}
                      </div>
                      
                      {/* Quick Reply / Interactive Buttons */}
                      <div className="mt-3 pt-3 border-t border-border/50">
                        <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1.5"><Bot className="h-3 w-3" /> {t("paper.aiContinue")}</p>
                        <div className="flex flex-wrap gap-2">
                          {["15m", "1h", "4h"].map(tf => (
                            <Button 
                              key={tf} 
                              onClick={() => handleAiAnalysis(tf)} 
                              disabled={aiLoading}
                              variant="secondary" 
                              size="sm" 
                              className="h-7 text-xs"
                            >
                              Analyze {tf}
                            </Button>
                          ))}
                          <Button 
                            onClick={() => handleAiAnalysis("平仓")} 
                            disabled={aiLoading}
                            variant="secondary" 
                            size="sm" 
                            className="h-7 text-xs bg-red-500/10 hover:bg-red-500/20 text-red-500 border-red-500/20 border"
                          >
                            {t("paper.evalClose")}
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  )}
                </Card>
              )}

              {/* Tab Header */}
              <Card className="border-border/50">
                <div className="border-b border-border/50">
                  <div className="flex px-4">
                    {([
                      { key: "positions" as BottomTab, label: t("paper.tabPositions") },
                      { key: "pending" as BottomTab, label: t("paper.tabPending") },
                      { key: "filled" as BottomTab, label: t("paper.tabFilled") },
                      { key: "history" as BottomTab, label: t("paper.tabHistory") },
                      { key: "liveOrders" as BottomTab, label: t("paper.tabLiveOrders") },
                      { key: "liveHistory" as BottomTab, label: t("paper.tabLiveHistory") },
                    ]).map((tab) => (
                      <button
                        key={tab.key}
                        onClick={() => setBottomTab(tab.key)}
                        className={`px-4 py-2.5 text-xs font-medium border-b-2 transition-colors ${
                          bottomTab === tab.key
                            ? "border-primary text-foreground"
                            : "border-transparent text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        {tab.label}
                        {tabCounts[tab.key] > 0 && (
                          <span className={`ml-1 px-1 py-0.5 rounded text-[10px] ${
                            bottomTab === tab.key ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"
                          }`}>
                            {tabCounts[tab.key]}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>

                <CardContent className="px-4 py-3">
                  {/* Positions Tab */}
                  {bottomTab === "positions" && (
                    openPositions.length === 0 ? (
                      <div className="py-8 text-center space-y-2">
                        <p className="text-sm text-muted-foreground">{t("paper.noPositions")}</p>
                        {hasRunningDeployment && (
                          <p className="text-xs text-muted-foreground/60">{t("paper.strategyRunningNoTrade")}</p>
                        )}
                      </div>
                    ) : (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">{t("paper.contract")}</TableHead>
                            <TableHead className="text-xs">{t("paper.direction")}</TableHead>
                            <TableHead className="text-xs">{t("paper.mode")}</TableHead>
                            <TableHead className="text-xs">{t("paper.leverage")}</TableHead>
                            <TableHead className="text-xs">{t("paper.qtyUsdt")}</TableHead>
                            <TableHead className="text-xs">{t("paper.qtyBase", { base: currentSymbolInfo?.base ?? "" })}</TableHead>
                            <TableHead className="text-xs">{t("paper.avgEntry")}</TableHead>
                            <TableHead className="text-xs">{t("paper.markPrice")}</TableHead>
                            <TableHead className="text-xs">{t("paper.margin")}</TableHead>
                            <TableHead className="text-xs">{t("paper.liqPrice")}</TableHead>
                            <TableHead className="text-xs">{t("paper.unrealizedPnl")}</TableHead>
                            <TableHead className="text-xs">{t("paper.returnPct")}</TableHead>
                            <TableHead className="text-xs">{t("paper.action")}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {openPositions.map((pos, i) => {
                            const posDir = (pos.pos_side ?? pos.side) === "long" || pos.side === "buy" ? "long" : "short"
                            return (
                              <TableRow key={i}>
                                <TableCell className="font-medium text-xs">{pos.symbol}</TableCell>
                                <TableCell>
                                  <Badge variant={posDir === "long" ? "success" : "destructive"} className="text-[10px]">
                                    {posDir === "long" ? t("paper.longBadge") : t("paper.shortBadge")}
                                  </Badge>
                                </TableCell>
                                <TableCell>
                                  <Badge variant={pos.margin_mode === "isolated" ? "secondary" : "warning"} className="text-[10px]">
                                    {pos.margin_mode === "isolated" ? t("paper.isolatedMargin") : t("paper.crossMargin")}
                                  </Badge>
                                </TableCell>
                                <TableCell className="text-xs font-mono">{pos.leverage ?? 1}x</TableCell>
                                <TableCell className="text-xs font-mono">{pos.quantity?.toFixed(2)}</TableCell>
                                <TableCell className="text-xs font-mono">{(pos.quantity_base ?? 0).toFixed(6)}</TableCell>
                                <TableCell className="text-xs font-mono">{(pos.avg_entry_price ?? pos.entry_price)?.toFixed(2)}</TableCell>
                                <TableCell className="text-xs font-mono">{pos.current_price?.toFixed(2) ?? "-"}</TableCell>
                                <TableCell className="text-xs font-mono">{pos.margin?.toFixed(2) ?? "-"}</TableCell>
                                <TableCell className="text-xs font-mono">{pos.liquidation_price?.toFixed(2) ?? "-"}</TableCell>
                                <TableCell className={`text-xs font-mono ${(pos.unrealized_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                                  {(pos.unrealized_pnl ?? 0) >= 0 ? "+" : ""}{(pos.unrealized_pnl ?? 0).toFixed(2)}
                                </TableCell>
                                <TableCell className={`text-xs font-mono ${(pos.unrealized_pnl_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                                  {(pos.unrealized_pnl_pct ?? 0) >= 0 ? "+" : ""}{(pos.unrealized_pnl_pct ?? 0).toFixed(2)}%
                                </TableCell>
                                <TableCell>
                                  <Button
                                    variant="destructive"
                                    size="sm"
                                    className="h-6 px-2 text-[10px]"
                                    onClick={() => handleClosePosition(pos)}
                                  >
                                    {t("paper.closeBtn")}
                                  </Button>
                                </TableCell>
                              </TableRow>
                            )
                          })}
                        </TableBody>
                      </Table>
                    )
                  )}

                  {/* Pending Orders Tab */}
                  {bottomTab === "pending" && (
                    pendingOrders.length === 0 ? (
                      <p className="text-sm text-muted-foreground py-8 text-center">{t("paper.noPending")}</p>
                    ) : (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">{t("paper.contract")}</TableHead>
                            <TableHead className="text-xs">{t("paper.direction")}</TableHead>
                            <TableHead className="text-xs">{t("paper.type")}</TableHead>
                            <TableHead className="text-xs">{t("paper.leverage")}</TableHead>
                            <TableHead className="text-xs">{t("paper.qtyUsdt")}</TableHead>
                            <TableHead className="text-xs">{t("paper.orderPrice")}</TableHead>
                            <TableHead className="text-xs">{t("paper.status")}</TableHead>
                            <TableHead className="text-xs">{t("paper.action")}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {pendingOrders.map((ord) => (
                            <TableRow key={ord.id}>
                              <TableCell className="font-medium text-xs">{ord.symbol}</TableCell>
                              <TableCell>
                                <Badge variant={(ord.pos_side ?? ord.side) === "long" || ord.side === "buy" ? "success" : "destructive"} className="text-[10px]">
                                  {(ord.pos_side ?? ord.side) === "long" || ord.side === "buy" ? t("paper.openLongBadge") : t("paper.openShortBadge")}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-xs">{ord.type === "market" ? t("paper.market") : t("paper.limit")}</TableCell>
                              <TableCell className="text-xs font-mono">{ord.leverage ?? 1}x</TableCell>
                              <TableCell className="text-xs font-mono">{ord.quantity?.toFixed(2)}</TableCell>
                              <TableCell className="text-xs font-mono">
                                {ord.price ? `${ord.price.toFixed(2)}` : t("paper.market")}
                              </TableCell>
                              <TableCell>
                                <Badge variant="warning" className="text-[10px]">
                                  {ord.status === "partial" ? t("paper.partialFill") : t("paper.pendingFill")}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <Button
                                  variant="destructive"
                                  size="sm"
                                  className="h-6 px-2 text-[10px]"
                                  onClick={() => handleCancelOrder(ord.id)}
                                >
                                  {t("paper.cancelBtn")}
                                </Button>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )
                  )}

                  {/* Filled Orders Tab */}
                  {bottomTab === "filled" && (
                    filledOrders.length === 0 ? (
                      <p className="text-sm text-muted-foreground py-8 text-center">{t("paper.noFilled")}</p>
                    ) : (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">{t("paper.contract")}</TableHead>
                            <TableHead className="text-xs">{t("paper.direction")}</TableHead>
                            <TableHead className="text-xs">{t("paper.type")}</TableHead>
                            <TableHead className="text-xs">{t("paper.leverage")}</TableHead>
                            <TableHead className="text-xs">{t("paper.qtyUsdt")}</TableHead>
                            <TableHead className="text-xs">{t("paper.avgFillPrice")}</TableHead>
                            <TableHead className="text-xs">{t("paper.status")}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filledOrders.map((ord) => (
                            <TableRow key={ord.id}>
                              <TableCell className="font-medium text-xs">{ord.symbol}</TableCell>
                              <TableCell>
                                <Badge variant={(ord.pos_side ?? ord.side) === "long" || ord.side === "buy" ? "success" : "destructive"} className="text-[10px]">
                                  {ord.reduce_only
                                    ? ((ord.pos_side ?? ord.side) === "long" || ord.side === "buy" ? t("paper.closeLongBadge") : t("paper.closeShortBadge"))
                                    : ((ord.pos_side ?? ord.side) === "long" || ord.side === "buy" ? t("paper.openLongBadge") : t("paper.openShortBadge"))}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-xs">{ord.type === "market" ? t("paper.market") : t("paper.limit")}</TableCell>
                              <TableCell className="text-xs font-mono">{ord.leverage ?? 1}x</TableCell>
                              <TableCell className="text-xs font-mono">{ord.quantity?.toFixed(2)}</TableCell>
                              <TableCell className="text-xs font-mono">
                                {(ord.avg_fill_price ?? ord.price) ? `${(ord.avg_fill_price ?? ord.price)?.toFixed(2)}` : "-"}
                              </TableCell>
                              <TableCell>
                                <Badge variant="success" className="text-[10px]">{t("paper.filledBadge")}</Badge>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )
                  )}

                  {/* Trade History Tab — enriched fill records */}
                  {bottomTab === "history" && (
                    fills.length === 0 ? (
                      <div className="py-8 text-center space-y-2">
                        <p className="text-sm text-muted-foreground">{t("paper.noFills")}</p>
                        {hasRunningDeployment && (
                          <p className="text-xs text-muted-foreground/60">{t("paper.strategyRunningNoTrade")}</p>
                        )}
                      </div>
                    ) : (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">{t("paper.contract")}</TableHead>
                            <TableHead className="text-xs">{t("paper.direction")}</TableHead>
                            <TableHead className="text-xs">{t("paper.openClose")}</TableHead>
                            <TableHead className="text-xs">{t("paper.leverage")}</TableHead>
                            <TableHead className="text-xs">{t("paper.qtyUsdt")}</TableHead>
                            <TableHead className="text-xs">{t("paper.fillPrice")}</TableHead>
                            <TableHead className="text-xs">{t("paper.fee")}</TableHead>
                            <TableHead className="text-xs">{t("paper.pnl")}</TableHead>
                            <TableHead className="text-xs">{t("paper.makerTaker")}</TableHead>
                            <TableHead className="text-xs">{t("paper.time")}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {[...fills].sort((a, b) => (b.timestamp ?? 0) - (a.timestamp ?? 0)).map((f) => (
                            <TableRow key={f.id}>
                              <TableCell className="font-medium text-xs">{f.symbol}</TableCell>
                              <TableCell>
                                <Badge variant={f.side === "buy" ? "success" : "destructive"} className="text-[10px]">
                                  {f.side === "buy" ? t("paper.buyBadge") : t("paper.sellBadge")}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-xs">
                                {f.reduce_only ? (
                                  <Badge variant="secondary" className="text-[10px]">{t("paper.closePosition")}</Badge>
                                ) : (
                                  <span className="text-muted-foreground">{t("paper.openPosition")}</span>
                                )}
                              </TableCell>
                              <TableCell className="text-xs font-mono">{f.leverage ?? 1}x</TableCell>
                              <TableCell className="text-xs font-mono">{f.quantity?.toFixed(2)}</TableCell>
                              <TableCell className="text-xs font-mono">
                                {f.price ? f.price.toFixed(2) : "-"}
                              </TableCell>
                              <TableCell className="text-xs font-mono text-amber-400">
                                {(f.fee ?? 0).toFixed(4)}
                              </TableCell>
                              <TableCell className={`text-xs font-mono ${(f.realized_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                                {(f.realized_pnl ?? 0) === 0 ? "-" : `${(f.realized_pnl ?? 0) > 0 ? "+" : ""}${(f.realized_pnl ?? 0).toFixed(2)}`}
                              </TableCell>
                              <TableCell className="text-xs">
                                <Badge variant="outline" className="text-[9px]">
                                  {f.exec_type === "maker" ? "M" : "T"}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-xs font-mono text-muted-foreground">
                                {f.timestamp ? new Date(f.timestamp).toLocaleTimeString() : "-"}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )
                  )}

                  {/* Live Orders Tab (from Trading module) */}
                  {bottomTab === "liveOrders" && (
                    <OrderTable wsOrders={liveTrading.orders} />
                  )}

                  {/* Live Trade History Tab (from Trading module) */}
                  {bottomTab === "liveHistory" && (
                    <TradeHistory wsFills={liveTrading.fills} />
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
    </RequireAuth>
  )
}
