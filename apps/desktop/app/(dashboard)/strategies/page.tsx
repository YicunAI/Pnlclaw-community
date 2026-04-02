"use client"

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { RequireAuth } from "@/components/auth/require-auth"
import { useRouter, useSearchParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Input } from "@/components/ui/input"
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
  FlaskConical,
  Search,
  LayoutGrid,
  List,
  ArrowRight,
  Loader2,
  Rocket,
  History,
  Brain,
  BarChart3,
  AlertCircle,
  Trash2,
} from "lucide-react"
import {
  getStrategies,
  getBacktests,
  createStrategy,
  deleteStrategy,
  deleteBacktest,
  getStrategyDeployments,
  stopStrategyDeployment,
  getPaperEquityHistory,
  getPaperPnl,
  getPaperAccount,
  abortAllPendingGets,
  sendAgentChat,
  type StrategyData,
  type BacktestData,
  type StrategyDeploymentData,
  type PaperEquityPoint,
  type PaperAccountData,
} from "@/lib/api-client"
import { BacktestResultPanel } from "@/components/strategy/backtest-result-panel"
import { useI18n } from "@/components/i18n/use-i18n"
import { StrategyCard } from "@/components/strategy/strategy-card"
import { cn } from "@/lib/utils"
import { parseRichMarkdownToReact } from "@/lib/markdown-rich"

type TabId = "my" | "center" | "deployments" | "templates" | "backtests"

function directionKey(direction: StrategyData["direction"]): string {
  if (direction === "short_only") return "strategies.card.dirShort"
  if (direction === "neutral") return "strategies.card.dirNeutral"
  return "strategies.card.dirLong"
}

function tableMetrics(bt: BacktestData | null | undefined) {
  if (!bt) return { sharpe: "—", ret: "—", dd: "—", retClass: "" }
  const m = bt.result?.metrics
  const sharpe = m?.sharpe_ratio ?? bt.sharpe_ratio ?? 0
  const ret = m?.total_return ?? bt.total_return ?? 0
  const dd = m?.max_drawdown ?? bt.max_drawdown ?? 0
  return {
    sharpe: sharpe.toFixed(2),
    ret: `${(ret * 100).toFixed(1)}%`,
    dd: `${(dd * 100).toFixed(1)}%`,
    retClass: ret >= 0 ? "text-emerald-400" : "text-red-400",
  }
}

export default function StrategiesHubPage() {
  const { t } = useI18n()
  const router = useRouter()
  const searchParams = useSearchParams()

  const initialTab = (searchParams.get("tab") as TabId) || "my"
  const [strategies, setStrategies] = useState<StrategyData[]>([])
  const [backtests, setBacktests] = useState<BacktestData[]>([])
  const [deployments, setDeployments] = useState<StrategyDeploymentData[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<TabId>(
    ["my", "center", "deployments", "templates", "backtests"].includes(initialTab) ? initialTab : "my"
  )
  const [viewMode, setViewMode] = useState<"grid" | "table">("grid")
  const [searchQuery, setSearchQuery] = useState("")
  const [filterState, setFilterState] = useState("all")
  const [filterDirection, setFilterDirection] = useState("all")
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [newStrategyName, setNewStrategyName] = useState("")
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [selectedBacktest, setSelectedBacktest] = useState<BacktestData | null>(null)
  const [explanation, setExplanation] = useState("")
  const [explaining, setExplaining] = useState(false)
  const [liveEquityMap, setLiveEquityMap] = useState<Record<string, PaperEquityPoint[]>>({})
  const [livePnlMap, setLivePnlMap] = useState<Record<string, { realized: number; unrealized: number }>>({})
  const [liveAccountMap, setLiveAccountMap] = useState<Record<string, PaperAccountData>>({})


  const explainBacktest = useCallback(async () => {
    if (!selectedBacktest) return
    setExplaining(true)
    setExplanation("")
    const m = selectedBacktest.result?.metrics
    await sendAgentChat(
      "Please explain this backtest in plain language.",
      (event) => {
        if (event.type === "text_delta") {
          const text = typeof event.data === "object" && event.data !== null && "text" in event.data
            ? String((event.data as { text?: unknown }).text ?? "")
            : typeof event.data === "string" ? event.data : ""
          setExplanation((prev) => prev + text)
        }
        if (event.type === "done" || event.type === "error") setExplaining(false)
      },
      {
        intent: "backtest_explain",
        backtest_id: selectedBacktest.id,
        strategy_id: selectedBacktest.strategy_id,
        strategy_name: selectedBacktest.strategy_name,
        metrics: {
          total_return: m?.total_return ?? selectedBacktest.total_return ?? 0,
          annual_return: m?.annual_return ?? selectedBacktest.annual_return ?? 0,
          sharpe_ratio: m?.sharpe_ratio ?? selectedBacktest.sharpe_ratio ?? 0,
          max_drawdown: m?.max_drawdown ?? selectedBacktest.max_drawdown ?? 0,
          win_rate: m?.win_rate ?? selectedBacktest.win_rate ?? 0,
          profit_factor: m?.profit_factor ?? selectedBacktest.profit_factor ?? 0,
          total_trades: m?.total_trades ?? selectedBacktest.total_trades ?? 0,
          calmar_ratio: m?.calmar_ratio ?? selectedBacktest.calmar_ratio ?? 0,
          sortino_ratio: m?.sortino_ratio ?? selectedBacktest.sortino_ratio ?? 0,
          expectancy: m?.expectancy ?? selectedBacktest.expectancy ?? 0,
          recovery_factor: m?.recovery_factor ?? 0,
        },
      }
    )
  }, [selectedBacktest])

  const getLatestBacktest = useCallback(
    (strategyId: string): BacktestData | null => {
      const list = backtests.filter((b) => b.strategy_id === strategyId)
      if (!list.length) return null
      return [...list].sort(
        (a, b) => Number(b.created_at) - Number(a.created_at)
      )[0]
    },
    [backtests]
  )

  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      abortAllPendingGets()
    }
  }, [])

  const fetchAll = useCallback(async (showLoader = true) => {
    if (showLoader) setLoading(true)
    const [sr, br, dr] = await Promise.all([
      getStrategies(),
      getBacktests(),
      getStrategyDeployments().catch(() => ({ data: [] })),
    ])
    if (!mountedRef.current) return
    setStrategies(Array.isArray(sr.data) ? sr.data : [])
    setBacktests(Array.isArray(br.data) ? br.data : [])
    setDeployments(Array.isArray(dr.data) ? dr.data : [])
    setLoading(false)
  }, [])

  const fetchLiveData = useCallback(async (deps: StrategyDeploymentData[]) => {
    const running = deps.filter((d) => d.status === "running" && d.account_id)
    if (!running.length) return
    const [eqResults, pnlResults, acctResults] = await Promise.all([
      Promise.all(running.map((d) => getPaperEquityHistory(d.account_id, 200).catch(() => ({ data: null })))),
      Promise.all(running.map((d) => getPaperPnl(d.account_id).catch(() => ({ data: null })))),
      Promise.all(running.map((d) => getPaperAccount(d.account_id).catch(() => ({ data: null })))),
    ])
    if (!mountedRef.current) return
    const eqMap: Record<string, PaperEquityPoint[]> = {}
    const pMap: Record<string, { realized: number; unrealized: number }> = {}
    const aMap: Record<string, PaperAccountData> = {}
    running.forEach((d, i) => {
      if (Array.isArray(eqResults[i].data)) eqMap[d.strategy_id] = eqResults[i].data!
      if (pnlResults[i].data) pMap[d.strategy_id] = pnlResults[i].data!
      if (acctResults[i].data) aMap[d.strategy_id] = acctResults[i].data!
    })
    setLiveEquityMap(eqMap)
    setLivePnlMap(pMap)
    setLiveAccountMap(aMap)
  }, [])

  useEffect(() => {
    fetchAll()
    const onFocus = () => fetchAll(false)
    window.addEventListener("focus", onFocus)
    return () => {
      window.removeEventListener("focus", onFocus)
    }
  }, [fetchAll])

  useEffect(() => {
    if (deployments.length === 0) return
    void fetchLiveData(deployments)
    const hasRunning = deployments.some((d) => d.status === "running")
    if (!hasRunning) return
    const id = setInterval(() => {
      if (mountedRef.current) void fetchLiveData(deployments)
    }, 30_000)
    return () => clearInterval(id)
  }, [deployments, fetchLiveData])

  const handleStopStrategy = useCallback(async (strategyId: string) => {
    await stopStrategyDeployment(strategyId)
    await fetchAll(false)
  }, [fetchAll])

  const deployedStrategyIds = useMemo(
    () => new Set(deployments.filter((d) => d.status === "running").map((d) => d.strategy_id)),
    [deployments],
  )

  const deploymentByStrategyId = useMemo(() => {
    const map: Record<string, StrategyDeploymentData> = {}
    for (const d of deployments) {
      if (!map[d.strategy_id] || d.status === "running") {
        map[d.strategy_id] = d
      }
    }
    return map
  }, [deployments])

  const strategyNameMap = useMemo(
    () => Object.fromEntries(strategies.map((s) => [s.id, s.name])),
    [strategies],
  )

  const strategyMap = useMemo(
    () => Object.fromEntries(strategies.map((s) => [s.id, s])),
    [strategies],
  )

  const filteredStrategies = useMemo(() => {
    let list = strategies
    if (activeTab === "templates") {
      list = list.filter((s) => s.source === "template")
    } else if (activeTab === "center") {
      list = list.filter(
        (s) =>
          s.lifecycle_state === "running" || deployedStrategyIds.has(s.id),
      )
    } else if (activeTab === "my") {
      list = list.filter((s) => s.source !== "template")
    }
    const q = searchQuery.trim().toLowerCase()
    if (q) {
      list = list.filter((s) => s.name.toLowerCase().includes(q))
    }
    if (filterState !== "all") {
      list = list.filter(
        (s) => (s.lifecycle_state ?? "draft") === filterState
      )
    }
    if (filterDirection !== "all") {
      list = list.filter((s) => s.direction === filterDirection)
    }
    return [...list].sort((a, b) => {
      const aRunning = deployedStrategyIds.has(a.id) ? 1 : 0
      const bRunning = deployedStrategyIds.has(b.id) ? 1 : 0
      if (aRunning !== bRunning) return bRunning - aRunning
      return Number(b.created_at ?? 0) - Number(a.created_at ?? 0)
    })
  }, [
    strategies,
    activeTab,
    searchQuery,
    filterState,
    filterDirection,
    deployedStrategyIds,
  ])

  const handleCreateStrategy = async () => {
    setCreateError(null)
    const name = newStrategyName.trim()
    if (!name) {
      setCreateError(t("strategies.hub.errNameRequired"))
      return
    }
    setCreating(true)
    try {
      const res = await createStrategy({
        name,
        type: "custom",
        symbols: ["BTC/USDT"],
        interval: "1h",
        description: "",
        parameters: {},
        entry_rules: {},
        exit_rules: {},
        risk_params: {},
        tags: [],
        source: "user",
      })
      if (res.error || !res.data?.id) {
        setCreateError(res.error ?? "Failed")
        return
      }
      setCreateDialogOpen(false)
      setNewStrategyName("")
      router.push(`/strategies/${res.data.id}/studio`)
    } finally {
      setCreating(false)
    }
  }

  const handleDeleteStrategy = async (id: string) => {
    await deleteStrategy(id)
    setStrategies((prev) => prev.filter((s) => s.id !== id))
  }

  const handleDeleteBacktest = async (id: string) => {
    await deleteBacktest(id)
    setBacktests((prev) => prev.filter((b) => b.id !== id))
    if (selectedBacktest?.id === id) setSelectedBacktest(null)
  }

  const tabClass = (tab: TabId) =>
    cn(
      "pb-2 text-sm font-medium border-b-2 -mb-px transition-colors",
      activeTab === tab
        ? "border-primary text-foreground"
        : "border-transparent text-muted-foreground hover:text-foreground"
    )

  return (
    <RequireAuth>
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{t("strategies.hub.title")}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {t("strategies.hub.subtitle")}
          </p>
        </div>
        <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button type="button" className="gap-1.5 shrink-0">
              <Plus className="h-4 w-4" />
              {t("strategies.hub.newStrategy")}
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-card border-border sm:max-w-[400px]">
            <DialogHeader>
              <DialogTitle>{t("strategies.hub.newStrategy")}</DialogTitle>
              <DialogDescription className="text-muted-foreground">
                {t("strategies.hub.createHint")}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-muted-foreground block mb-1">
                  {t("strategies.hub.strategyName")}
                </label>
                <Input
                  value={newStrategyName}
                  onChange={(e) => setNewStrategyName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") void handleCreateStrategy() }}
                  placeholder={t("strategies.hub.namePlaceholder")}
                  autoFocus
                />
              </div>
              {createError && (
                <p className="text-xs text-red-400">{createError}</p>
              )}
              <Button
                type="button"
                className="w-full"
                disabled={creating || !newStrategyName.trim()}
                onClick={handleCreateStrategy}
              >
                {creating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  t("strategies.hub.createAndEnter")
                )}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <div className="flex items-center gap-4 border-b border-border">
        <button
          type="button"
          className={tabClass("my")}
          onClick={() => setActiveTab("my")}
        >
          {t("strategies.hub.myResearch")}
        </button>
        <button
          type="button"
          className={tabClass("center")}
          onClick={() => setActiveTab("center")}
        >
          <span className="inline-flex items-center gap-1.5">
            <Rocket className="h-3.5 w-3.5" />
            {t("strategies.hub.strategyCenter")}
            {deployedStrategyIds.size > 0 && (
              <Badge variant="default" className="text-[10px] px-1.5 py-0 ml-1">
                {deployedStrategyIds.size}
              </Badge>
            )}
          </span>
        </button>
        <button
          type="button"
          className={tabClass("deployments")}
          onClick={() => setActiveTab("deployments")}
        >
          <span className="inline-flex items-center gap-1.5">
            {t("strategies.hub.deployments")}
            {deployments.length > 0 && (
              <Badge variant="outline" className="text-[10px] px-1.5 py-0 ml-0.5">
                {deployments.length}
              </Badge>
            )}
          </span>
        </button>
        <button
          type="button"
          className={tabClass("templates")}
          onClick={() => setActiveTab("templates")}
        >
          <span className="inline-flex items-center gap-1.5">
            <FlaskConical className="h-3.5 w-3.5" />
            {t("strategies.hub.templates")}
          </span>
        </button>
        <button
          type="button"
          className={tabClass("backtests")}
          onClick={() => setActiveTab("backtests")}
        >
          <span className="inline-flex items-center gap-1.5">
            <History className="h-3.5 w-3.5" />
            {t("nav.backtests")}
            {backtests.length > 0 && (
              <Badge variant="outline" className="text-[10px] px-1.5 py-0 ml-0.5">
                {backtests.length}
              </Badge>
            )}
          </span>
        </button>
      </div>

      {activeTab === "deployments" ? (
        <div className="space-y-4">
          {deployments.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border bg-card/50 py-16 text-center text-sm text-muted-foreground">
              {t("strategies.hub.noDeployments")}
            </div>
          ) : (
            <div className="rounded-lg border border-border bg-card overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="border-border hover:bg-transparent">
                    <TableHead className="text-xs">{t("paper.deployStrategy")}</TableHead>
                    <TableHead className="text-xs">{t("paper.deployVersion")}</TableHead>
                    <TableHead className="text-xs">{t("paper.deployStatus")}</TableHead>
                    <TableHead className="text-xs">{t("paper.deployMode")}</TableHead>
                    <TableHead className="text-xs">{t("paper.deployCreated")}</TableHead>
                    <TableHead className="text-xs" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {deployments.map((dep) => (
                    <TableRow key={dep.id} className="border-border">
                      <TableCell>
                        <div className="text-sm font-medium">{strategyNameMap[dep.strategy_id] ?? dep.strategy_id}</div>
                        <div className="font-mono text-[10px] text-muted-foreground">{dep.strategy_id}</div>
                      </TableCell>
                      <TableCell className="text-xs font-mono">v{dep.strategy_version}</TableCell>
                      <TableCell>
                        <Badge variant={dep.status === "running" ? "default" : "secondary"} className="text-[10px]">
                          {dep.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">{dep.mode}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {new Date(dep.created_at).toLocaleString()}
                      </TableCell>
                      <TableCell>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs"
                          onClick={() => router.push(`/strategies/${dep.strategy_id}/studio`)}
                        >
                          {t("strategies.hub.openStudio")}
                          <ArrowRight className="h-3 w-3 ml-1" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      ) : activeTab === "backtests" ? (
        <div className="grid grid-cols-[320px_1fr] gap-6 items-start">
          {/* Backtest list */}
          <Card className="h-fit">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <History className="h-4 w-4" />
                {t("backtests.history")}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {loading ? (
                <div className="space-y-2 p-3">
                  {[1,2,3].map((i) => <div key={i} className="h-14 rounded-lg bg-muted animate-pulse" />)}
                </div>
              ) : backtests.length === 0 ? (
                <p className="text-sm text-muted-foreground py-8 text-center">{t("backtests.none")}</p>
              ) : (
                <div className="space-y-1 p-2 max-h-[calc(100vh-280px)] overflow-y-auto">
                  {backtests.map((bt) => {
                    const isRunning = bt.status === "pending" || bt.status === "running"
                    const isFailed = bt.status === "failed"
                    const totalReturn = bt.result?.metrics?.total_return ?? bt.total_return ?? 0
                    return (
                      <div
                        key={bt.id}
                        role="button"
                        tabIndex={0}
                        onClick={() => { setSelectedBacktest(bt); setExplanation("") }}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedBacktest(bt); setExplanation("") } }}
                        className={`w-full text-left p-3 rounded-lg transition-colors cursor-pointer ${
                          selectedBacktest?.id === bt.id
                            ? "bg-primary/10 border border-primary/20"
                            : "hover:bg-muted"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium truncate">{bt.strategy_name}</span>
                          <div className="flex items-center gap-1 shrink-0">
                            {isRunning ? (
                              <Badge variant="secondary" className="gap-1">
                                <Loader2 className="h-3 w-3 animate-spin" />{bt.status}
                              </Badge>
                            ) : isFailed ? (
                              <Badge variant="destructive" className="gap-1">
                                <AlertCircle className="h-3 w-3" />{t("backtests.failed")}
                              </Badge>
                            ) : (
                              <Badge variant={totalReturn >= 0 ? "default" : "destructive"} className={totalReturn >= 0 ? "bg-emerald-600" : ""}>
                                {totalReturn >= 0 ? "+" : ""}{(totalReturn * 100).toFixed(1)}%
                              </Badge>
                            )}
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                              onClick={(e) => {
                                e.stopPropagation()
                                if (confirm(t("backtests.deleteConfirm"))) {
                                  void handleDeleteBacktest(bt.id)
                                }
                              }}
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">
                          {bt.result?.metrics?.total_trades ?? bt.total_trades ?? 0} {t("backtests.trades")} &middot; {new Date(bt.created_at).toLocaleDateString()}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Backtest detail */}
          {selectedBacktest ? (
            <div className="space-y-4">
              <BacktestResultPanel
                result={selectedBacktest}
                strategy={selectedBacktest ? strategyMap[selectedBacktest.strategy_id] ?? null : null}
                symbolOverride={selectedBacktest.symbol || strategyMap[selectedBacktest.strategy_id]?.symbols?.[0] || strategyMap[selectedBacktest.strategy_id]?.symbol}
                intervalOverride={selectedBacktest.interval || strategyMap[selectedBacktest.strategy_id]?.interval}
                loading={false}
              />
              {/* AI explanation */}
              <Card>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Brain className="h-4 w-4" />
                      {t("backtests.explainBacktest")}
                    </CardTitle>
                    <Button size="sm" variant="outline" onClick={explainBacktest} disabled={explaining}>
                      {explaining ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Brain className="h-4 w-4 mr-1" />}
                      {t("backtests.explain")}
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {explanation ? (
                    <div className="strategy-ai-richtext text-sm leading-relaxed [&_strong]:font-semibold [&_em]:italic">
                      {parseRichMarkdownToReact(explanation, explaining)}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">{t("backtests.explainHint")}</p>
                  )}
                </CardContent>
              </Card>
            </div>
          ) : (
            <Card>
              <CardContent className="py-16 text-center text-muted-foreground">
                <BarChart3 className="h-10 w-10 mx-auto mb-3 opacity-30" />
                <p className="font-medium">{t("backtests.selectPrompt")}</p>
                <p className="text-xs mt-2">{t("backtests.selectHint")}</p>
              </CardContent>
            </Card>
          )}
        </div>
      ) : (
        <>
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9 bg-card"
            placeholder={t("strategies.hub.search")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <select
          className="h-9 rounded-md border border-border bg-card px-2 text-sm text-foreground"
          value={filterState}
          onChange={(e) => setFilterState(e.target.value)}
        >
          <option value="all">{t("strategies.hub.filterAll")}</option>
          <option value="draft">draft</option>
          <option value="validated">validated</option>
          <option value="confirmed">confirmed</option>
          <option value="running">running</option>
        </select>
        <select
          className="h-9 rounded-md border border-border bg-card px-2 text-sm text-foreground"
          value={filterDirection}
          onChange={(e) => setFilterDirection(e.target.value)}
        >
          <option value="all">{t("strategies.hub.filterAll")}</option>
          <option value="long_only">long_only</option>
          <option value="short_only">short_only</option>
          <option value="neutral">neutral</option>
        </select>
        <div className="flex rounded-md border border-border overflow-hidden">
          <Button
            type="button"
            size="sm"
            variant={viewMode === "grid" ? "secondary" : "ghost"}
            className="rounded-none h-9 px-2"
            onClick={() => setViewMode("grid")}
            title={t("strategies.hub.viewCards")}
          >
            <LayoutGrid className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            size="sm"
            variant={viewMode === "table" ? "secondary" : "ghost"}
            className="rounded-none h-9 px-2 border-l border-border"
            onClick={() => setViewMode("table")}
            title={t("strategies.hub.viewTable")}
          >
            <List className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-48 w-full rounded-lg" />
          ))}
        </div>
      ) : filteredStrategies.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-card/50 py-16 text-center text-sm text-muted-foreground">
          {t("strategies.hub.noStrategies")}
        </div>
      ) : viewMode === "grid" ? (
        (() => {
          const running = filteredStrategies.filter((s) => deployedStrategyIds.has(s.id))
          const idle = filteredStrategies.filter((s) => !deployedStrategyIds.has(s.id))
          return (
            <div className="space-y-6">
              {running.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-sm font-medium text-emerald-400 flex items-center gap-1.5">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                    </span>
                    {t("strategies.hub.runningSection")}
                    <Badge variant="default" className="text-[10px] px-1.5 py-0 ml-1 bg-emerald-600">
                      {running.length}
                    </Badge>
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {running.map((s) => (
                      <StrategyCard
                        key={s.id}
                        strategy={s}
                        latestBacktest={getLatestBacktest(s.id)}
                        deployment={deploymentByStrategyId[s.id]}
                        liveEquity={liveEquityMap[s.id]}
                        livePnl={livePnlMap[s.id]}
                        liveAccount={liveAccountMap[s.id]}
                        onDelete={handleDeleteStrategy}
                        onStop={handleStopStrategy}
                      />
                    ))}
                  </div>
                </div>
              )}
              {idle.length > 0 && (
                <div className="space-y-3">
                  {running.length > 0 && (
                    <h3 className="text-sm font-medium text-muted-foreground">
                      {t("strategies.hub.idleSection")}
                    </h3>
                  )}
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {idle.map((s) => (
                      <StrategyCard
                        key={s.id}
                        strategy={s}
                        latestBacktest={getLatestBacktest(s.id)}
                        deployment={deploymentByStrategyId[s.id]}
                        onDelete={handleDeleteStrategy}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )
        })()
      ) : (
        <div className="rounded-lg border border-border bg-card overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-xs">{t("strategies.hub.strategyName")}</TableHead>
                <TableHead className="text-xs">{t("strategies.table.type")}</TableHead>
                <TableHead className="text-xs">{t("strategies.table.interval")}</TableHead>
                <TableHead className="text-xs">{t("strategies.table.direction")}</TableHead>
                <TableHead className="text-xs">{t("strategies.table.state")}</TableHead>
                <TableHead className="text-xs text-right">{t("strategies.table.sharpe")}</TableHead>
                <TableHead className="text-xs text-right">{t("strategies.table.return")}</TableHead>
                <TableHead className="text-xs text-right">{t("strategies.table.maxDD")}</TableHead>
                <TableHead className="text-xs w-[100px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredStrategies.map((s) => {
                const bt = getLatestBacktest(s.id)
                const tm = tableMetrics(bt)
                const isLive = deployedStrategyIds.has(s.id)
                return (
                  <TableRow
                    key={s.id}
                    className={cn(
                      "border-border cursor-pointer",
                      isLive && "bg-emerald-500/[0.03]",
                    )}
                    onClick={() => router.push(`/strategies/${s.id}/studio`)}
                  >
                    <TableCell className="text-sm font-medium">
                      <span className="flex items-center gap-1.5">
                        {isLive && (
                          <span className="relative flex h-2 w-2 shrink-0">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                          </span>
                        )}
                        {s.name}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs">{s.type}</TableCell>
                    <TableCell className="text-xs">{s.interval}</TableCell>
                    <TableCell className="text-xs">
                      {t(directionKey(s.direction) as Parameters<typeof t>[0])}
                    </TableCell>
                    <TableCell className="text-xs">
                      {isLive ? (
                        <Badge className="text-[10px] bg-emerald-600 hover:bg-emerald-600">
                          {t("strategies.card.running")}
                        </Badge>
                      ) : (
                        <Badge
                          variant={
                            s.lifecycle_state === "confirmed"
                              ? "default"
                              : "outline"
                          }
                          className="text-[10px]"
                        >
                          {s.lifecycle_state ?? "draft"}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-xs font-mono text-right">
                      {tm.sharpe}
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-xs font-mono text-right",
                        tm.retClass
                      )}
                    >
                      {tm.ret}
                    </TableCell>
                    <TableCell className="text-xs font-mono text-right text-red-400">
                      {tm.dd}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs"
                          onClick={(e) => {
                            e.stopPropagation()
                            router.push(`/strategies/${s.id}/studio`)
                          }}
                        >
                          {t("strategies.hub.openStudio")}
                          <ArrowRight className="h-3 w-3 ml-1" />
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                          onClick={(e) => {
                            e.stopPropagation()
                            if (confirm(t("strategies.hub.deleteStrategyConfirm"))) {
                              void handleDeleteStrategy(s.id)
                            }
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
      </>
      )}
    </div>
    </RequireAuth>
  )
}
