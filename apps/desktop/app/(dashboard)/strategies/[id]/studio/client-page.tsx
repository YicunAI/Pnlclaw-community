"use client"

import { StudioToolbar } from "@/components/strategy/studio-toolbar"
import { BacktestResultPanel } from "@/components/strategy/backtest-result-panel"
import { RunnerMonitorPanel } from "@/components/strategy/runner-monitor"
import { AiSidebar } from "@/components/strategy/ai-sidebar"
import { VersionTimeline } from "@/components/strategy/version-timeline"
import { useI18n } from "@/components/i18n/use-i18n"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  deployStrategyToPaper,
  stopStrategyDeployment,
  getBacktest,
  getBacktests,
  getStrategy,
  getRunnerStatus,
  runBacktest,
  updateStrategy,
  validateStrategy,
  type BacktestData,
  type StrategyData,
} from "@/lib/api-client"
import {
  Activity,
  ArrowLeft,
  PanelLeftOpen,
  Terminal,
} from "lucide-react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react"

type BottomTab = "logs" | "monitor"

const AI_SIDEBAR_MIN_WIDTH = 240
const AI_SIDEBAR_MAX_WIDTH = 480
const AI_SIDEBAR_DEFAULT_WIDTH = 360

function getStudioBacktestStorageKey(strategyId: string): string {
  return `pnlclaw:strategy-studio-backtest:${strategyId}`
}

function strategyToValidateConfig(s: StrategyData): Record<string, unknown> {
  return {
    name: s.name,
    symbols: s.symbols,
    symbol: s.symbol,
    type: s.type,
    interval: s.interval,
    description: s.description,
    parameters: s.parameters,
    entry_rules: s.entry_rules,
    exit_rules: s.exit_rules,
    risk_params: s.risk_params,
    tags: s.tags,
    source: s.source,
    direction: s.direction,
  }
}

export default function StrategyStudioPage() {
  const { t } = useI18n()
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const paramId = typeof params.id === "string" ? params.id : params.id?.[0]
  const id = searchParams.get("id") || (paramId !== "placeholder" ? paramId : undefined)

  const [strategy, setStrategy] = useState<StrategyData | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [backtestResult, setBacktestResult] = useState<BacktestData | null>(null)
  const [backtestRunning, setBacktestRunning] = useState(false)
  const [leftPanelOpen, setLeftPanelOpen] = useState(true)
  const [leftPanelWidth, setLeftPanelWidth] = useState(AI_SIDEBAR_DEFAULT_WIDTH)
  const [bottomPanelOpen, setBottomPanelOpen] = useState(false)
  const [bottomTab, setBottomTab] = useState<BottomTab>("logs")
  const [logs, setLogs] = useState<string[]>([])
  const [versionRefreshKey, setVersionRefreshKey] = useState(0)
  const [runnerAccountId, setRunnerAccountId] = useState<string | null>(null)
  const [runnerDeploymentId, setRunnerDeploymentId] = useState<string | null>(null)
  const [validationResult, setValidationResult] = useState<{
    valid: boolean
    errors: string[]
  } | null>(null)
  const [deploying, setDeploying] = useState(false)
  const backtestStorageKey = id ? getStudioBacktestStorageKey(id) : null

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const dragStateRef = useRef<{ startX: number; startWidth: number } | null>(null)

  useEffect(() => {
    if (!leftPanelOpen) return

    const handlePointerMove = (event: PointerEvent) => {
      const dragState = dragStateRef.current
      if (!dragState) return
      const nextWidth = dragState.startWidth + (event.clientX - dragState.startX)
      setLeftPanelWidth(Math.min(AI_SIDEBAR_MAX_WIDTH, Math.max(AI_SIDEBAR_MIN_WIDTH, nextWidth)))
    }

    const handlePointerUp = () => {
      dragStateRef.current = null
    }

    window.addEventListener("pointermove", handlePointerMove)
    window.addEventListener("pointerup", handlePointerUp)
    return () => {
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
    }
  }, [leftPanelOpen])

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (!id) return
    let cancelled = false
    const check = async () => {
      const res = await getRunnerStatus()
      if (cancelled || !res.data) return
      const slot = res.data.deployments.find((d) => d.strategy_id === id)
      if (slot) {
        setRunnerAccountId(slot.account_id)
        setRunnerDeploymentId(slot.deployment_id)
        setBottomPanelOpen(true)
        setBottomTab("monitor")
      }
    }
    check()
    const iv = setInterval(check, 30_000)
    return () => { cancelled = true; clearInterval(iv) }
  }, [id])

  useEffect(() => {
    if (!id) {
      setLoading(false)
      setLoadError(t("strategies.studio.missingId"))
      setStrategy(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setLoadError(null)
    getStrategy(id).then((res) => {
      if (cancelled) return
      setLoading(false)
      if (res.error || !res.data) {
        setStrategy(null)
        setLoadError(res.error ?? t("strategies.studio.notFound"))
      } else {
        setStrategy(res.data)
        setLoadError(null)
      }
    })
    return () => {
      cancelled = true
    }
  }, [id])

  useEffect(() => {
    if (!id) return
    let cancelled = false

    // Show cached result instantly while API loads
    if (backtestStorageKey) {
      try {
        const raw = window.localStorage.getItem(backtestStorageKey)
        if (raw) {
          const cached = JSON.parse(raw) as BacktestData
          if (cached && (cached.strategy_id === id || cached.result || cached.trades)) {
            setBacktestResult(cached)
          }
        }
      } catch { /* ignore */ }
    }

    // Always fetch latest from API and override cache
    getBacktests(id).then((res) => {
      if (cancelled) return
      const list = Array.isArray(res.data) ? res.data : []
      const latest = list.find((b) => b.status === "completed" || b.result) ?? list[0]
      if (latest) {
        setBacktestResult(latest)
      }
    }).catch(() => { /* keep cached result if API fails */ })

    return () => { cancelled = true }
  }, [id, backtestStorageKey])

  useEffect(() => {
    if (!backtestStorageKey || !backtestResult) return
    try {
      window.localStorage.setItem(backtestStorageKey, JSON.stringify(backtestResult))
    } catch {
      // ignore storage failures
    }
  }, [backtestResult, backtestStorageKey])

  const handleSave = useCallback(async () => {
    if (!strategy || !id) return
    console.log("[Strategy Studio] save", id, strategy)
    const res = await updateStrategy(id, strategy)
    if (res.error) {
      setLogs((prev) => [...prev, `${t("strategies.studio.saveFailed")}: ${res.error}`])
      return
    }
    if (res.data) setStrategy(res.data)
    setLogs((prev) => [...prev, t("strategies.studio.saved")])
    setVersionRefreshKey((k) => k + 1)
  }, [id, strategy, t])

  const handleValidate = useCallback(async () => {
    if (!strategy) return
    const res = await validateStrategy(strategyToValidateConfig(strategy))
    if (res.error) {
      setValidationResult({ valid: false, errors: [res.error] })
      setLogs((prev) => [...prev, `${t("strategies.studio.validateFail")}: ${res.error}`])
      return
    }
    if (res.data) {
      setValidationResult(res.data)
      setLogs((prev) => [
        ...prev,
        res.data!.valid ? t("strategies.studio.validatePass") : `${t("strategies.studio.validateFail")}: ${res.data!.errors.join("; ")}`,
      ])
    }
  }, [strategy, t])

  const handleRunBacktest = useCallback(async () => {
    if (!id || backtestRunning) return
    setBacktestRunning(true)
    setLogs((prev) => [...prev, `${t("strategies.studio.backtestStarting")} (${id})`])

    const runRes = await runBacktest({
      strategy_id: id,
      initial_capital: 10000,
      commission_rate: 0.001,
    })

    if (runRes.error || !runRes.data?.task_id) {
      setBacktestRunning(false)
      setLogs((prev) => [...prev, `${t("strategies.studio.backtestFailed")}: ${runRes.error ?? "no task_id"}`])
      return
    }

    const taskId = runRes.data.task_id
    setLogs((prev) => [...prev, `${t("strategies.studio.polling")} (${taskId})`])

    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }

    const tick = async () => {
      const res = await getBacktest(taskId)
      if (res.error) {
        if (pollRef.current) {
          clearInterval(pollRef.current)
          pollRef.current = null
        }
        setBacktestRunning(false)
        setLogs((prev) => [...prev, `${t("strategies.studio.pollError")}: ${res.error}`])
        return
      }
      const data = res.data
      if (!data) return
      const st = (data.status || "").toLowerCase()
      if (st === "completed" || st === "failed") {
        if (pollRef.current) {
          clearInterval(pollRef.current)
          pollRef.current = null
        }
        setBacktestRunning(false)
        setBacktestResult(data)
        setLogs((prev) => [
          ...prev,
          st === "completed"
            ? t("strategies.studio.backtestDone")
            : `${t("strategies.studio.backtestFailed")}: ${data.error ?? "unknown error"}`,
        ])
      }
    }

    await tick()
    pollRef.current = setInterval(() => {
      void tick()
    }, 1000)
  }, [id, backtestRunning, t])

  const handleDeploy = useCallback(async () => {
    if (!id || deploying) return
    setDeploying(true)
    setBottomPanelOpen(true)
    setLogs((prev) => [...prev, `${t("strategies.studio.deploy")}...`])
    try {
      const res = await deployStrategyToPaper(id)
      if (res.error) {
        setLogs((prev) => [...prev, `${t("strategies.studio.deployFailed")}: ${res.error}`])
        return
      }
      const data = res.data as Record<string, unknown> | undefined
      const dep = data?.deployment as Record<string, unknown> | undefined
      if (dep?.account_id) setRunnerAccountId(dep.account_id as string)
      if (dep?.id) setRunnerDeploymentId(dep.id as string)

      if (data?.already_deployed) {
        setLogs((prev) => [...prev, `${t("strategies.studio.deployDone")} — already running`])
        setBottomTab("monitor")
        return
      }
      const createdAcct = data?.created_account as Record<string, unknown> | undefined
      if (createdAcct?.name) {
        setLogs((prev) => [
          ...prev,
          `📋 ${t("strategies.studio.accountCreated")}: ${createdAcct.name} (${createdAcct.id})`,
        ])
      }

      const runnerStatus = data?.runner_status
      if (runnerStatus === "running") {
        setLogs((prev) => [
          ...prev,
          `${t("strategies.studio.deployDone")} — Strategy Runner active`,
        ])
        setBottomTab("monitor")
      } else {
        const runnerError = (data?.runner_error as string) || ""
        setLogs((prev) => [
          ...prev,
          `${t("strategies.studio.deployDone")} (runner: ${runnerError || "inactive"})`,
        ])
      }
    } catch {
      setLogs((prev) => [...prev, `${t("strategies.studio.deployFailed")}: network error`])
    } finally {
      setDeploying(false)
    }
  }, [id, deploying, t])

  const handleStopDeployment = useCallback(async () => {
    if (!id) return
    setLogs((prev) => [...prev, t("strategies.studio.stoppingDeployment")])
    try {
      const res = await stopStrategyDeployment(id)
      if (res.error) {
        setLogs((prev) => [...prev, `${t("strategies.studio.stopFailed")}: ${res.error}`])
      } else {
        const stopped = res.data?.stopped_deployments ?? []
        setLogs((prev) => [...prev, `${t("strategies.studio.stopDone")} (${stopped.length})`])
        setRunnerDeploymentId(null)
        setRunnerAccountId(null)
      }
    } catch {
      setLogs((prev) => [...prev, `${t("strategies.studio.stopFailed")}: network error`])
    }
  }, [id, t])

  const handleExport = useCallback(() => {
    if (!strategy) return
    const blob = new Blob([JSON.stringify(strategy, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${strategy.name?.replace(/\s+/g, "-") || strategy.id}-strategy.json`
    a.click()
    URL.revokeObjectURL(url)
    setLogs((prev) => [...prev, t("strategies.studio.exportDone")])
  }, [strategy, t])

  const handleStrategyChange = useCallback((updated: Partial<StrategyData>) => {
    setStrategy((prev) => (prev ? { ...prev, ...updated } : prev))
  }, [])

  const handleApplyYaml = useCallback((yamlContent: string) => {
    try {
      const yaml = require("js-yaml")
      const parsed = yaml.load(yamlContent) as Record<string, unknown>
      if (parsed && typeof parsed === "object") {
        const MAPPED: Record<string, string> = {
          parsed_entry_rules: "entry_rules",
          parsed_exit_rules: "exit_rules",
          parsed_risk_params: "risk_params",
        }
        for (const [from, to] of Object.entries(MAPPED)) {
          if (from in parsed && !(to in parsed)) {
            parsed[to] = parsed[from]
          }
          delete parsed[from]
        }

        handleStrategyChange(parsed as Partial<StrategyData>)
        setLogs((prev) => [...prev, t("strategies.studio.yamlApplied")])

        if (id) {
          updateStrategy(id, parsed as Partial<StrategyData>).then((res) => {
            const d = res.data
            if (d) {
              setStrategy((prev) => prev ? { ...prev, ...d, version: d.version } : prev)
              const ver = d.version ?? "?"
              setLogs((prev) => [...prev, `Auto-saved as version ${ver}`])
              setVersionRefreshKey((k) => k + 1)
            }
          }).catch(() => {
            setLogs((prev) => [...prev, "Auto-save failed (API unreachable)"])
          })
        }
      }
    } catch {
      setLogs((prev) => [...prev, t("strategies.studio.yamlApplyFailed")])
    }
  }, [handleStrategyChange, t, id])

  const handleLeftPanelResizeStart = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      dragStateRef.current = {
        startX: event.clientX,
        startWidth: leftPanelWidth,
      }
      event.currentTarget.setPointerCapture(event.pointerId)
      event.preventDefault()
    },
    [leftPanelWidth]
  )

  if (loading) {
    return (
      <div className="flex flex-col h-[calc(100vh-3.5rem)] overflow-hidden p-4">
        <Card className="border-border bg-card">
          <CardHeader className="py-3">
            <CardTitle className="text-sm">{t("strategies.studio.title")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Skeleton className="h-8 w-full max-w-md" />
            <Skeleton className="h-32 w-full" />
          </CardContent>
        </Card>
      </div>
    )
  }

  if (!strategy && loadError) {
    return (
      <div className="flex flex-col h-[calc(100vh-3.5rem)] overflow-hidden items-center justify-center p-4">
        <Card className="border-border bg-card max-w-md w-full">
          <CardHeader>
            <CardTitle className="text-sm text-destructive">{t("strategies.studio.notFound")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">{loadError}</p>
            <Button variant="outline" size="sm" onClick={() => router.push("/strategies")}>
              <ArrowLeft className="h-4 w-4 mr-1" /> {t("strategies.studio.backToHub")}
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col overflow-hidden bg-background">
      <div className="shrink-0 bg-card/95 backdrop-blur-sm">
        <div className="flex items-center gap-2 border-b border-border/70 px-3 py-2">
          <Button variant="ghost" size="sm" onClick={() => router.push("/strategies")}>
            <ArrowLeft className="mr-1 h-4 w-4" /> {t("strategies.studio.backToHub")}
          </Button>
          <div className="flex min-w-0 items-center gap-2">
            <h1 className="truncate text-sm font-semibold">{strategy?.name}</h1>
            <Badge variant="outline" className="border-border/70 bg-background/40 text-[10px]">
              v{strategy?.version ?? 1}
            </Badge>
            <Badge variant="outline" className="border-border/70 bg-background/40 text-[10px]">
              {strategy?.lifecycle_state ?? "draft"}
            </Badge>
          </div>
          <div className="ml-auto">
            <StudioToolbar
              onSave={handleSave}
              onValidate={handleValidate}
              onRunBacktest={handleRunBacktest}
              onDeploy={handleDeploy}
              onStopDeployment={handleStopDeployment}
              onExport={handleExport}
              backtestRunning={backtestRunning}
              deploying={deploying}
              isDeployed={!!runnerDeploymentId}
              validationResult={validationResult}
            />
          </div>
        </div>
        <VersionTimeline
          strategyId={id || ""}
          currentVersion={strategy?.version ?? 1}
          refreshKey={versionRefreshKey}
          onRevert={(config, ver) => {
            handleStrategyChange(config as Partial<StrategyData>)
            setLogs((prev) => [...prev, `Loaded version ${ver} config (click Save to apply)`])
          }}
        />
      </div>

      <div className="flex flex-1 overflow-hidden bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.05),transparent_28%),radial-gradient(circle_at_top_right,rgba(34,211,238,0.035),transparent_24%)] p-2">
        <div className="flex min-h-0 flex-1 overflow-hidden rounded-[20px] border border-border/70 bg-card/40 shadow-[0_18px_48px_rgba(0,0,0,0.32)]">
          {leftPanelOpen && (
            <>
              <div
                className="shrink-0 overflow-hidden border-r border-border/70 bg-card/90"
                style={{ width: `${leftPanelWidth}px` }}
              >
                <AiSidebar
                  onCollapse={() => setLeftPanelOpen(false)}
                  strategyId={id || ""}
                  strategyName={strategy?.name || ""}
                  strategy={strategy}
                  symbol={strategy?.symbols?.[0]}
                  timeframe={strategy?.interval}
                  onStrategyChange={handleStrategyChange}
                  onApplyYaml={handleApplyYaml}
                  onBacktestResult={setBacktestResult}
                  onStrategyRefresh={() => {
                    if (!id) return
                    getStrategy(id).then((res) => {
                      if (res.data) {
                        setStrategy(res.data)
                        setVersionRefreshKey((k) => k + 1)
                      }
                    })
                  }}
                />
              </div>
              <div
                role="separator"
                aria-orientation="vertical"
                aria-label={t("strategies.studio.aiHelper")}
                onPointerDown={handleLeftPanelResizeStart}
                className="w-1.5 shrink-0 cursor-col-resize bg-transparent transition-colors hover:bg-primary/20 active:bg-primary/30"
              />
            </>
          )}

          {!leftPanelOpen && (
            <button
              type="button"
              onClick={() => setLeftPanelOpen(true)}
              className="shrink-0 border-r border-border/70 bg-card/70 px-1.5 transition-colors hover:bg-muted"
              aria-label={t("strategies.studio.aiHelper")}
            >
              <PanelLeftOpen className="h-4 w-4 text-muted-foreground" />
            </button>
          )}

          <div className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden bg-background/30">
            <div className="min-h-full p-3">
              <div className="min-h-full overflow-hidden rounded-[20px] border border-border/60 bg-card/85 p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
                <BacktestResultPanel
                  result={backtestResult}
                  strategy={strategy}
                  loading={backtestRunning}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {bottomPanelOpen && (
        <div className="h-48 shrink-0 border-t border-border bg-card flex flex-col overflow-hidden">
          <div className="flex shrink-0 items-center gap-0 border-b border-border/50 bg-muted/30 px-2">
            <button
              type="button"
              onClick={() => setBottomTab("logs")}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-[11px] transition-colors border-b-2 ${
                bottomTab === "logs"
                  ? "border-primary text-foreground font-medium"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <Terminal className="h-3 w-3" />
              {t("strategies.studio.logs")}
            </button>
            {(strategy?.lifecycle_state === "running" || runnerAccountId) && (
              <button
                type="button"
                onClick={() => setBottomTab("monitor")}
                className={`flex items-center gap-1 px-2.5 py-1.5 text-[11px] transition-colors border-b-2 ${
                  bottomTab === "monitor"
                    ? "border-primary text-foreground font-medium"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                <Activity className="h-3 w-3" />
                {t("runner.monitor")}
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-3">
            {bottomTab === "logs" && (
              <div className="text-xs font-mono text-muted-foreground space-y-0.5">
                {logs.length === 0
                  ? <p>{t("strategies.studio.noLogs")}</p>
                  : logs.map((log, i) => <p key={i}>{log}</p>)}
              </div>
            )}
            {bottomTab === "monitor" && id && (
              <RunnerMonitorPanel
                strategyId={id}
                accountId={runnerAccountId}
                deploymentId={runnerDeploymentId}
              />
            )}
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => setBottomPanelOpen(!bottomPanelOpen)}
        className="h-6 shrink-0 border-t border-border flex items-center justify-center hover:bg-muted transition-colors"
      >
        <Terminal className="h-3 w-3 text-muted-foreground mr-1" />
        <span className="text-[10px] text-muted-foreground">{t("strategies.studio.logs")}</span>
      </button>
    </div>
  )
}
