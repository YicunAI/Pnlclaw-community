const API_BASE = process.env.NEXT_PUBLIC_API_URL || ""

interface ApiResponse<T> {
  data: T | null
  error: string | null
}

// ---------------------------------------------------------------------------
// In-flight GET deduplication: if the exact same GET is already in-flight,
// reuse its promise instead of sending a duplicate network request.
// ---------------------------------------------------------------------------
const _inflight = new Map<string, Promise<ApiResponse<unknown>>>()

// Tracked AbortControllers so mutation calls (DELETE/POST/PUT) can cancel
// all pending GETs to free up browser connections immediately.
const _controllers = new Set<AbortController>()

export function abortAllPendingGets(): void {
  for (const c of _controllers) {
    try { c.abort() } catch { /* ignore */ }
  }
  _controllers.clear()
  _inflight.clear()
}

async function request<T>(path: string, init?: RequestInit): Promise<ApiResponse<T>> {
  const method = (init?.method ?? "GET").toUpperCase()

  if (method === "GET") {
    const key = path
    const existing = _inflight.get(key)
    if (existing) return existing as Promise<ApiResponse<T>>

    const controller = new AbortController()
    _controllers.add(controller)

    const promise = _doRequest<T>(path, { ...init, signal: controller.signal })
      .finally(() => {
        _inflight.delete(key)
        _controllers.delete(controller)
      })
    _inflight.set(key, promise as Promise<ApiResponse<unknown>>)
    return promise
  }

  return _doRequest<T>(path, init)
}

async function _doRequest<T>(path: string, init?: RequestInit): Promise<ApiResponse<T>> {
  try {
    const method = (init?.method ?? "GET").toUpperCase()
    const headers: Record<string, string> = { ...init?.headers as Record<string, string> }
    if (method !== "GET" && method !== "HEAD") {
      headers["Content-Type"] ??= "application/json"
    }
    const res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store" as RequestCache,
      ...init,
      headers,
    })
    if (!res.ok) {
      const body = await res.text()
      return { data: null, error: `HTTP ${res.status}: ${body}` }
    }
    const json = await res.json()
    return { data: (json.data ?? json) as T, error: null }
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      return { data: null, error: null }
    }
    return { data: null, error: e instanceof Error ? e.message : "Unknown error" }
  }
}

export interface TickerData {
  symbol: string
  last_price: number
  change_24h_pct: number
  volume_24h: number
  quote_volume_24h?: number
  high_24h?: number
  low_24h?: number
  bid?: number
  ask?: number
}

export interface KlineData {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface OrderbookData {
  bids: { price: number; quantity: number }[]
  asks: { price: number; quantity: number }[]
}

export interface StrategyData {
  id: string
  name: string
  symbols: string[]
  symbol?: string
  type: string
  interval: string
  description?: string
  parameters?: Record<string, unknown>
  entry_rules?: Record<string, unknown>
  exit_rules?: Record<string, unknown>
  risk_params?: Record<string, unknown>
  tags?: string[]
  source?: string
  direction?: "long_only" | "short_only" | "neutral"
  version?: number
  lifecycle_state?: string
  created_at?: string | number
}

export interface StrategyVersionSnapshotData {
  id: string
  strategy_id: string
  version: number
  config_snapshot: Record<string, unknown>
  note?: string
  created_at: string | number
}

export interface StrategyDeploymentData {
  id: string
  strategy_id: string
  strategy_version: number
  account_id: string
  mode: string
  status: string
  created_at: string | number
}

export interface BacktestMetricsData {
  total_return: number
  annual_return: number
  sharpe_ratio: number
  max_drawdown: number
  win_rate: number
  profit_factor: number
  total_trades: number
  calmar_ratio?: number
  sortino_ratio?: number
  expectancy?: number
  recovery_factor?: number
}

export interface BacktestTradeData {
  pnl?: number
  side?: string
  symbol?: string
  price?: number
  quantity?: number
  timestamp?: number
  [key: string]: unknown
}

export interface BacktestResultData {
  id: string
  strategy_id: string
  strategy_version?: number
  start_date?: string
  end_date?: string
  metrics: BacktestMetricsData
  equity_curve?: number[]
  drawdown_curve?: number[]
  buy_hold_curve?: number[]
  trades?: BacktestTradeData[]
  trades_count: number
  created_at: string | number
}

export interface BacktestData {
  id: string
  task_id: string
  strategy_id: string
  strategy_version?: number
  strategy_name: string
  symbol?: string
  interval?: string
  status: string
  total_return: number
  annual_return?: number
  sharpe_ratio: number
  max_drawdown: number
  win_rate: number
  profit_factor: number
  total_trades: number
  calmar_ratio?: number
  sortino_ratio?: number
  expectancy?: number
  recovery_factor?: number
  equity_curve?: number[]
  drawdown_curve?: number[]
  buy_hold_curve?: number[]
  trades?: BacktestTradeData[]
  result?: BacktestResultData
  error?: string | null
  created_at: string | number
}

export interface PaperAccountData {
  id: string
  name: string
  initial_balance: number
  current_balance: number
  balance?: number
  equity: number
  unrealized_pnl?: number
  realized_pnl?: number
  total_realized_pnl: number
  total_fee: number
  maker_fee_rate: number
  taker_fee_rate: number
  status?: string
  account_type?: "strategy" | "agent" | "manual"
  strategy_id?: string
  deployment_id?: string
  created_at: string | number
}

export type MarginMode = "cross" | "isolated" | "cash"
export type PositionSideType = "long" | "short" | "net"

export interface PaperPositionData {
  symbol: string
  side: string
  pos_side: PositionSideType
  quantity: number
  quantity_base: number
  avg_entry_price: number
  entry_price?: number
  current_price: number | null
  leverage: number
  margin_mode: MarginMode
  margin: number
  liquidation_price: number | null
  unrealized_pnl: number
  unrealized_pnl_pct: number
  realized_pnl: number
}

export interface PaperOrderData {
  id: string
  symbol: string
  side: string
  type: string
  quantity: number
  price: number | null
  avg_fill_price: number | null
  status: string
  leverage: number
  margin_mode: MarginMode
  pos_side: PositionSideType
  reduce_only: boolean
  created_at: string | number
}

export async function checkHealth(): Promise<ApiResponse<{ status: string }>> {
  return request("/api/v1/health")
}

export async function getMarkets(): Promise<ApiResponse<string[]>> {
  return request("/api/v1/markets")
}

function marketPathSymbol(symbol: string): string {
  return symbol.trim().toUpperCase().replace(/[\s/_]+/g, "-")
}

export type ExchangeProvider = "binance" | "okx"
export type MarketType = "spot" | "futures"

interface MarketSourceOptions {
  exchange?: ExchangeProvider
  market_type?: MarketType
}

function toMarketSourceQuery(options?: MarketSourceOptions): string {
  const qs = new URLSearchParams()
  if (options?.exchange) qs.set("exchange", options.exchange)
  if (options?.market_type) qs.set("market_type", options.market_type)
  const query = qs.toString()
  return query ? `&${query}` : ""
}

export async function getTicker(
  symbol: string,
  options?: MarketSourceOptions
): Promise<ApiResponse<TickerData>> {
  return request(`/api/v1/markets/${marketPathSymbol(symbol)}/ticker${toMarketSourceQuery(options).replace(/^&/, "?")}`)
}

export async function getKlines(
  symbol: string,
  interval = "1h",
  limit = 500,
  options?: MarketSourceOptions,
  endTime?: number
): Promise<ApiResponse<KlineData[]>> {
  let url = `/api/v1/markets/${marketPathSymbol(symbol)}/kline?interval=${interval}&limit=${limit}${toMarketSourceQuery(options)}`
  if (endTime != null) url += `&end_time=${endTime}`
  return request(url)
}

export async function getOrderbook(
  symbol: string,
  depth = 10,
  options?: MarketSourceOptions
): Promise<ApiResponse<OrderbookData>> {
  return request(`/api/v1/markets/${marketPathSymbol(symbol)}/orderbook?depth=${depth}${toMarketSourceQuery(options)}`)
}

export async function getStrategies(tags?: string): Promise<ApiResponse<StrategyData[]>> {
  const qs = tags ? `?tags=${encodeURIComponent(tags)}` : ""
  return request(`/api/v1/strategies${qs}`)
}

export async function getStrategy(id: string): Promise<ApiResponse<StrategyData>> {
  return request(`/api/v1/strategies/${encodeURIComponent(id)}`)
}

export async function updateStrategy(id: string, data: Partial<StrategyData>, versionNote?: string): Promise<ApiResponse<StrategyData>> {
  const payload: Record<string, unknown> = { ...data }
  if (versionNote) payload.version_note = versionNote
  return request(`/api/v1/strategies/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export async function deleteStrategy(id: string): Promise<ApiResponse<{ deleted: string }>> {
  return request(`/api/v1/strategies/${encodeURIComponent(id)}`, {
    method: "DELETE",
  })
}

export async function deleteBacktest(id: string): Promise<ApiResponse<{ deleted: string }>> {
  return request(`/api/v1/backtests/${encodeURIComponent(id)}`, {
    method: "DELETE",
  })
}

export async function createStrategy(config: Record<string, unknown>): Promise<ApiResponse<StrategyData>> {
  return request("/api/v1/strategies", {
    method: "POST",
    body: JSON.stringify(config),
  })
}

export async function validateStrategy(config: Record<string, unknown>): Promise<ApiResponse<{ valid: boolean; errors: string[] }>> {
  return request("/api/v1/strategies/validate", {
    method: "POST",
    body: JSON.stringify(config),
  })
}

export async function getStrategyVersions(strategyId: string): Promise<ApiResponse<StrategyVersionSnapshotData[]>> {
  return request(`/api/v1/strategies/${encodeURIComponent(strategyId)}/versions`)
}

export async function confirmStrategy(strategyId: string): Promise<ApiResponse<StrategyData>> {
  return request(`/api/v1/strategies/${encodeURIComponent(strategyId)}/confirm`, {
    method: "POST",
  })
}

export async function stopStrategyDeployment(
  strategyId: string
): Promise<ApiResponse<{ stopped_deployments: string[] }>> {
  return request(`/api/v1/strategies/${encodeURIComponent(strategyId)}/stop-deployment`, {
    method: "POST",
  })
}

export async function deployStrategyToPaper(
  strategyId: string,
  accountId: string = "paper-default"
): Promise<ApiResponse<{ deployment: StrategyDeploymentData; strategy: StrategyData }>> {
  return request(`/api/v1/strategies/${encodeURIComponent(strategyId)}/deploy-paper`, {
    method: "POST",
    body: JSON.stringify({ account_id: accountId }),
  })
}

export async function getStrategyDeployments(accountId?: string): Promise<ApiResponse<StrategyDeploymentData[]>> {
  const qs = accountId ? `?account_id=${encodeURIComponent(accountId)}` : ""
  return request(`/api/v1/strategies/deployments/list${qs}`)
}

export async function getBacktests(strategyId?: string, limit = 50): Promise<ApiResponse<BacktestData[]>> {
  const qs = strategyId ? `?strategy_id=${encodeURIComponent(strategyId)}&limit=${limit}` : ""
  return request(`/api/v1/backtests${qs}`)
}

export async function getBacktest(id: string): Promise<ApiResponse<BacktestData>> {
  return request(`/api/v1/backtests/${id}`)
}

export async function runBacktest(params: {
  strategy_id: string
  data_path?: string
  initial_capital?: number
  initial_cash?: number
  commission_rate?: number
  start_date?: string
  end_date?: string
}): Promise<ApiResponse<{ task_id: string; status: string }>> {
  return request("/api/v1/backtests", {
    method: "POST",
    body: JSON.stringify({
      strategy_id: params.strategy_id,
      data_path: params.data_path,
      initial_capital: params.initial_capital ?? params.initial_cash ?? 10000,
      commission_rate: params.commission_rate ?? 0.001,
      start_date: params.start_date,
      end_date: params.end_date,
    }),
  })
}

export async function getPaperAccounts(): Promise<ApiResponse<PaperAccountData[]>> {
  return request("/api/v1/paper/accounts")
}

export async function getPaperAccount(accountId: string): Promise<ApiResponse<PaperAccountData>> {
  return request(`/api/v1/paper/accounts/${encodeURIComponent(accountId)}`)
}

export async function createPaperAccount(params: {
  name: string
  balance?: number
  initial_balance?: number
  account_type?: "strategy" | "agent" | "manual"
  strategy_id?: string
}): Promise<ApiResponse<PaperAccountData>> {
  const payload: Record<string, unknown> = {
    name: params.name,
    initial_balance: params.initial_balance ?? params.balance ?? 10000,
  }
  if (params.account_type) payload.account_type = params.account_type
  if (params.strategy_id) payload.strategy_id = params.strategy_id
  return request("/api/v1/paper/accounts", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function deletePaperAccount(accountId: string): Promise<ApiResponse<{ success: boolean; id: string }>> {
  return request(`/api/v1/paper/accounts/${accountId}`, {
    method: "DELETE",
  })
}

// Reset account history and balance
export async function resetPaperAccount(accountId: string): Promise<ApiResponse<{ success: boolean; id: string }>> {
  return request(`/api/v1/paper/accounts/${accountId}/reset`, {
    method: "POST",
  })
}

export async function getPaperPositions(accountId: string): Promise<ApiResponse<PaperPositionData[]>> {
  return request(`/api/v1/paper/positions?account_id=${accountId}`)
}

export async function getPaperOrders(accountId: string): Promise<ApiResponse<PaperOrderData[]>> {
  return request(`/api/v1/paper/orders?account_id=${accountId}`)
}

export async function getPaperPnl(accountId: string): Promise<ApiResponse<{ realized: number; unrealized: number }>> {
  return request(`/api/v1/paper/pnl?account_id=${accountId}`)
}

export async function submitPaperOrder(params: {
  account_id: string
  symbol: string
  side: string
  order_type: string
  quantity: number
  price?: number
  leverage?: number
  margin_mode?: MarginMode
  pos_side?: PositionSideType
  reduce_only?: boolean
  mark_price?: number
  tp_price?: number
  sl_price?: number
}): Promise<ApiResponse<PaperOrderData>> {
  return request("/api/v1/paper/orders", {
    method: "POST",
    body: JSON.stringify(params),
  })
}

export async function closePaperPosition(params: {
  account_id: string
  symbol: string
  pos_side: PositionSideType
  quantity?: number
  mark_price?: number
}): Promise<ApiResponse<PaperOrderData>> {
  return request("/api/v1/paper/close-position", {
    method: "POST",
    body: JSON.stringify(params),
  })
}

export async function cancelPaperOrder(orderId: string): Promise<ApiResponse<PaperOrderData>> {
  return request(`/api/v1/paper/orders/${encodeURIComponent(orderId)}`, {
    method: "DELETE",
  })
}

export interface PaperEquityPoint {
  timestamp: string
  equity: number
}

export async function getPaperEquityHistory(
  accountId: string,
  limit: number = 100
): Promise<ApiResponse<PaperEquityPoint[]>> {
  return request(`/api/v1/paper/accounts/${encodeURIComponent(accountId)}/equity-history?limit=${limit}`)
}

export interface PaperFillData {
  id: string
  order_id: string
  symbol: string
  side: string
  pos_side: string
  price: number
  quantity: number
  fee: number
  fee_rate: number
  realized_pnl: number
  exec_type: string
  leverage: number
  reduce_only: boolean
  timestamp: number
}

export async function getPaperFills(accountId: string): Promise<ApiResponse<PaperFillData[]>> {
  return request(`/api/v1/paper/fills?account_id=${accountId}`)
}

export interface PaperSettings {
  account_id: string
  maker_fee_rate: number
  taker_fee_rate: number
}

export async function getPaperSettings(accountId: string = "paper-default"): Promise<ApiResponse<PaperSettings>> {
  return request(`/api/v1/paper/settings?account_id=${accountId}`)
}

export async function updatePaperSettings(params: {
  account_id?: string
  maker_fee_rate: number
  taker_fee_rate: number
}): Promise<ApiResponse<PaperSettings>> {
  const accountId = params.account_id || "paper-default"
  return request(`/api/v1/paper/settings?account_id=${accountId}`, {
    method: "POST",
    body: JSON.stringify({ maker_fee_rate: params.maker_fee_rate, taker_fee_rate: params.taker_fee_rate }),
  })
}

// ---------------------------------------------------------------------------
// Trading API (unified — works for both paper and live modes)
// ---------------------------------------------------------------------------

export interface TradingOrder {
  id: string
  account_id: string
  symbol: string
  side: "buy" | "sell"
  type: "market" | "limit" | "stop_market" | "stop_limit"
  status: string
  quantity: number
  price: number | null
  stop_price: number | null
  filled_quantity: number
  avg_fill_price: number | null
  created_at: number
  updated_at: number
}

export interface TradingPosition {
  account_id: string
  symbol: string
  side: "buy" | "sell"
  quantity: number
  avg_entry_price: number
  unrealized_pnl: number
  realized_pnl: number
  opened_at: number
  updated_at: number
}

export interface TradingBalance {
  account_id: string
  exchange: string
  asset: string
  free: number
  locked: number
  timestamp: number
}

export interface TradingFill {
  id: string
  account_id: string
  order_id: string
  price: number
  quantity: number
  fee: number
  fee_currency: string
  timestamp: number
}

export async function getTradingMode(): Promise<ApiResponse<{ mode: string }>> {
  return request("/api/v1/trading/mode")
}

export async function setTradingMode(mode: "paper" | "live"): Promise<ApiResponse<{ mode: string }>> {
  return request("/api/v1/trading/mode", {
    method: "PUT",
    body: JSON.stringify({ mode }),
  })
}

export async function placeOrder(params: {
  symbol: string
  side: "buy" | "sell"
  order_type: "market" | "limit" | "stop_market" | "stop_limit"
  quantity: number
  price?: number
  stop_price?: number
  account_id?: string
}): Promise<ApiResponse<TradingOrder>> {
  return request("/api/v1/trading/orders", {
    method: "POST",
    body: JSON.stringify(params),
  })
}

export async function cancelOrder(orderId: string): Promise<ApiResponse<TradingOrder>> {
  return request(`/api/v1/trading/orders/${encodeURIComponent(orderId)}`, {
    method: "DELETE",
  })
}

export async function getOrders(params?: {
  account_id?: string
  status?: string
}): Promise<ApiResponse<TradingOrder[]>> {
  const qs = new URLSearchParams()
  if (params?.account_id) qs.set("account_id", params.account_id)
  if (params?.status) qs.set("status", params.status)
  const query = qs.toString()
  return request(`/api/v1/trading/orders${query ? `?${query}` : ""}`)
}

export async function getPositions(accountId?: string): Promise<ApiResponse<TradingPosition[]>> {
  const qs = accountId ? `?account_id=${accountId}` : ""
  return request(`/api/v1/trading/positions${qs}`)
}

export async function getBalances(accountId?: string): Promise<ApiResponse<TradingBalance[]>> {
  const qs = accountId ? `?account_id=${accountId}` : ""
  return request(`/api/v1/trading/balances${qs}`)
}

export async function getTradeHistory(accountId?: string): Promise<ApiResponse<TradingFill[]>> {
  const qs = accountId ? `?account_id=${accountId}` : ""
  return request(`/api/v1/trading/history${qs}`)
}

export interface AppSettings {
  general: {
    api_url: string
    default_symbol: string
    default_interval: string
  }
  exchange: {
    provider: ExchangeProvider
    market_type: MarketType
    api_key: string
    api_secret: string
    clear_api_key?: boolean
    clear_api_secret?: boolean
    api_key_configured?: boolean
    api_secret_configured?: boolean
    api_key_masked?: string
    api_secret_masked?: string
  }
  llm: {
    provider: string
    api_key: string
    clear_api_key?: boolean
    base_url: string
    model: string
    api_key_configured?: boolean
    api_key_masked?: string
    smart_mode?: boolean
    smart_models?: {
      strategy?: string
      analysis?: string
      quick?: string
    }
  }
  risk: {
    max_position_pct: string
    single_risk_pct: string
    daily_loss_limit_pct: string
    cooldown_seconds: string
  }
  network: {
    proxy_url: string
  }
  security?: {
    secret_backend?: string
    keyring_available?: boolean
    persistence_guarantee?: string
    security_note?: string
  }
}

export async function getSettings(): Promise<ApiResponse<AppSettings>> {
  return request("/api/v1/settings")
}

export async function updateSettings(settings: Partial<AppSettings>): Promise<ApiResponse<AppSettings>> {
  const { encryptIfNonEmpty } = await import("@/lib/crypto")

  const payload = structuredClone(settings)

  try {
    if (payload.exchange) {
      if (payload.exchange.api_key) {
        payload.exchange.api_key = await encryptIfNonEmpty(payload.exchange.api_key)
      }
      if (payload.exchange.api_secret) {
        payload.exchange.api_secret = await encryptIfNonEmpty(payload.exchange.api_secret)
      }
    }
    if (payload.llm) {
      if (payload.llm.api_key) {
        payload.llm.api_key = await encryptIfNonEmpty(payload.llm.api_key)
      }
    }
  } catch {
    // Encryption unavailable — fall through with plaintext as graceful degradation
  }

  return request("/api/v1/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export interface LLMModel {
  id: string
  name: string
  owned_by: string
  created: number
}

export async function getLLMModels(): Promise<ApiResponse<{
  models: LLMModel[]
  current_model: string
  total: number
}>> {
  return request("/api/v1/settings/llm/models")
}

export interface AgentChatContext {
  symbol?: string
  timeframe?: string
  exchange?: string
  market_type?: string
  intent?: string
  mark_price?: number
  contract_symbol?: string
  positions?: Array<Record<string, unknown>>
  backtest_id?: string
  strategy_id?: string
  strategy_name?: string
  metrics?: Record<string, unknown>
  trades?: Array<Record<string, unknown>>
}

export interface AgentChatResult {
  sessionId?: string
}

const _HEARTBEAT_TIMEOUT_MS = 15_000
const _MAX_RECONNECT_ATTEMPTS = 3
const _RECONNECT_BASE_DELAY_MS = 2_000

async function _readSSEStream(
  res: Response,
  onEvent: (event: { type: string; data: unknown }) => void,
  signal?: AbortSignal,
): Promise<{ sessionId?: string; receivedDone: boolean; disconnectReason?: string }> {
  const headerSessionId = res.headers.get("X-Session-ID") ?? undefined
  let sseSessionId: string | undefined
  let receivedDone = false
  let timedOut = false

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let heartbeatTimer: ReturnType<typeof setTimeout> | null = null

  const resetHeartbeat = () => {
    if (heartbeatTimer) clearTimeout(heartbeatTimer)
    heartbeatTimer = setTimeout(() => {
      timedOut = true
      reader.cancel().catch(() => {})
    }, _HEARTBEAT_TIMEOUT_MS)
  }

  resetHeartbeat()

  try {
    while (true) {
      if (signal?.aborted) break
      const { done, value } = await reader.read()
      if (done) break

      resetHeartbeat()
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split("\n")
      buffer = lines.pop() || ""

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6)
          if (data === "[DONE]") {
            receivedDone = true
            return { sessionId: headerSessionId ?? sseSessionId, receivedDone }
          }
          try {
            const parsed = JSON.parse(data)
            if (parsed.type === "done") {
              receivedDone = true
              if (parsed.data?.session_id) {
                sseSessionId = parsed.data.session_id as string
              }
            }
            onEvent(parsed)
          } catch {
            onEvent({ type: "text", data })
          }
        }
      }
    }
  } finally {
    if (heartbeatTimer) clearTimeout(heartbeatTimer)
  }

  const disconnectReason = timedOut
    ? `${_HEARTBEAT_TIMEOUT_MS / 1000}s 内未收到服务器响应（心跳超时）`
    : signal?.aborted
      ? "用户取消"
      : "服务器关闭了连接"

  return { sessionId: headerSessionId ?? sseSessionId, receivedDone, disconnectReason }
}

export async function sendAgentChat(
  message: string,
  onEvent: (event: { type: string; data: unknown }) => void,
  context?: AgentChatContext,
  sessionId?: string,
  signal?: AbortSignal,
  options?: { resume?: boolean },
): Promise<AgentChatResult> {
  let attempt = 0
  let resolvedSessionId: string | undefined = sessionId
  let isResume = options?.resume ?? false

  while (attempt <= _MAX_RECONNECT_ATTEMPTS) {
    try {
      const body: Record<string, unknown> = { message }
      if (context) body.context = context
      if (resolvedSessionId) body.session_id = resolvedSessionId
      if (isResume) body.resume = true

      const res = await fetch(`${API_BASE}/api/v1/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
      })

      if (!res.ok || !res.body) {
        let detail = `HTTP ${res.status}`
        try {
          const errBody = await res.text()
          if (errBody) {
            const parsed = JSON.parse(errBody)
            const msg = parsed?.error?.message || parsed?.detail || parsed?.message || errBody.slice(0, 200)
            detail = `Server error (${res.status}): ${msg}`
          }
        } catch {
          // ignore parse errors
        }
        onEvent({ type: "error", data: detail })
        return { sessionId: resolvedSessionId }
      }

      const sid = res.headers.get("X-Session-ID") ?? undefined
      if (sid) resolvedSessionId = sid

      const { sessionId: streamSid, receivedDone, disconnectReason } = await _readSSEStream(res, onEvent, signal)
      if (streamSid) resolvedSessionId = streamSid

      if (receivedDone) {
        return { sessionId: resolvedSessionId }
      }

      if (signal?.aborted) {
        return { sessionId: resolvedSessionId }
      }

      // Stream ended without done — treat as disconnect
      attempt++
      if (attempt > _MAX_RECONNECT_ATTEMPTS) {
        const reason = disconnectReason || "未知原因"
        onEvent({ type: "error", data: `连接多次中断（${_MAX_RECONNECT_ATTEMPTS} 次重连均失败）\n原因：${reason}\n请检查 LLM 配置和网络后重试。` })
        return { sessionId: resolvedSessionId }
      }

      isResume = true
      const delay = _RECONNECT_BASE_DELAY_MS * Math.pow(2, attempt - 1)
      onEvent({ type: "reconnecting", data: { attempt, maxAttempts: _MAX_RECONNECT_ATTEMPTS, delayMs: delay } })
      await new Promise((r) => setTimeout(r, delay))
      onEvent({ type: "reconnected", data: { attempt } })

    } catch (err: unknown) {
      if (signal?.aborted || (err instanceof DOMException && err.name === "AbortError")) {
        onEvent({ type: "error", data: "请求已取消" })
        return { sessionId: resolvedSessionId }
      }

      const errMsg = err instanceof Error ? err.message : String(err)
      attempt++
      if (attempt > _MAX_RECONNECT_ATTEMPTS) {
        onEvent({ type: "error", data: `连接失败（${errMsg}）。请检查后端服务是否运行、网络是否正常后重试。` })
        return { sessionId: resolvedSessionId }
      }

      isResume = true
      const delay = _RECONNECT_BASE_DELAY_MS * Math.pow(2, attempt - 1)
      onEvent({ type: "reconnecting", data: { attempt, maxAttempts: _MAX_RECONNECT_ATTEMPTS, delayMs: delay } })
      await new Promise((r) => setTimeout(r, delay))
      onEvent({ type: "reconnected", data: { attempt } })
    }
  }

  return { sessionId: resolvedSessionId }
}

// ---------------------------------------------------------------------------
// MCP Server API
// ---------------------------------------------------------------------------

export interface McpServerInfo {
  name: string
  connected: boolean
  tool_count: number
  error: string | null
  transport: string
  tools: { server_name: string; tool_name: string; description: string }[]
}

export interface McpToolInfo {
  server_name: string
  tool_name: string
  registered_name: string
  description: string
}

export async function getMcpServers(): Promise<ApiResponse<{ servers: McpServerInfo[] }>> {
  return request("/api/v1/mcp/servers")
}

export async function addMcpServer(
  name: string,
  config: {
    command?: string
    args?: string[]
    url?: string
    transport?: string
    risk_level?: string
  }
): Promise<ApiResponse<McpServerInfo>> {
  return request(`/api/v1/mcp/servers/${encodeURIComponent(name)}`, {
    method: "POST",
    body: JSON.stringify(config),
  })
}

export async function removeMcpServer(name: string): Promise<ApiResponse<{ status: string }>> {
  return request(`/api/v1/mcp/servers/${encodeURIComponent(name)}`, {
    method: "DELETE",
  })
}

export async function refreshMcpServer(name: string): Promise<ApiResponse<McpServerInfo>> {
  return request(`/api/v1/mcp/servers/${encodeURIComponent(name)}/refresh`, {
    method: "POST",
  })
}

export async function getMcpTools(): Promise<ApiResponse<{ tools: McpToolInfo[] }>> {
  return request("/api/v1/mcp/tools")
}

// ---------------------------------------------------------------------------
// Skills API
// ---------------------------------------------------------------------------

export interface SkillInfo {
  name: string
  description: string
  source: string
  tags: string[]
  user_invocable: boolean
  model_invocable: boolean
  requires_tools: string[]
  file_path: string
  enabled: boolean
}

export interface SkillDetail extends SkillInfo {
  content: string
  version: string
  author: string
  requires_env: string[]
}

export async function getSkills(): Promise<ApiResponse<{ skills: SkillInfo[]; count: number }>> {
  return request("/api/v1/skills")
}

export async function getSkill(name: string): Promise<ApiResponse<SkillDetail>> {
  return request(`/api/v1/skills/${encodeURIComponent(name)}`)
}

export async function createSkill(params: {
  name: string
  description: string
  tags: string[]
  content: string
  user_invocable?: boolean
  model_invocable?: boolean
  requires_tools?: string[]
}): Promise<ApiResponse<{ name: string; file_path: string; created: boolean }>> {
  return request("/api/v1/skills/create", {
    method: "POST",
    body: JSON.stringify(params),
  })
}

export async function updateSkill(name: string, params: {
  description?: string
  tags?: string[]
  content?: string
  user_invocable?: boolean
  model_invocable?: boolean
  requires_tools?: string[]
}): Promise<ApiResponse<{ name: string; updated: boolean }>> {
  return request(`/api/v1/skills/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify(params),
  })
}

export async function deleteSkill(name: string): Promise<ApiResponse<{ name: string; deleted: boolean }>> {
  return request(`/api/v1/skills/${encodeURIComponent(name)}`, {
    method: "DELETE",
  })
}

export async function toggleSkill(name: string, enabled: boolean): Promise<ApiResponse<{ name: string; enabled: boolean }>> {
  return request(`/api/v1/skills/${encodeURIComponent(name)}/enable`, {
    method: "PUT",
    body: JSON.stringify({ enabled }),
  })
}

export async function refreshSkills(): Promise<ApiResponse<{ refreshed: boolean; count: number }>> {
  return request("/api/v1/skills/refresh", { method: "POST" })
}

// ---------------------------------------------------------------------------
// Polymarket
// ---------------------------------------------------------------------------

export interface PolymarketOutcome {
  token_id: string
  outcome: string
  price: number
  winner: boolean
}

export interface PolymarketSubMarket {
  id: string
  question: string
  question_zh: string
  condition_id: string
  slug: string
  active: boolean
  closed: boolean
  volume: number
  liquidity: number
  outcomes: PolymarketOutcome[]
  description?: string
  description_zh?: string
  end_date?: string
  start_date?: string
  neg_risk?: boolean
  best_bid?: number
  best_ask?: number
  spread?: number
  last_trade_price?: number
  volume_24h?: number
}

export interface PolymarketEvent {
  id: string
  title: string
  title_zh: string
  slug: string
  description: string
  description_zh?: string
  category: string
  category_zh: string
  image: string
  icon: string
  active: boolean
  closed: boolean
  volume: number
  volume_24h: number
  liquidity: number
  start_date: string
  end_date: string
  markets: PolymarketSubMarket[]
  market_count: number
  comment_count?: number
  created_at?: string
  updated_at?: string
  competitive?: number
  enableOrderBook?: boolean
  neg_risk?: boolean
}

export type PolymarketCategory =
  | "crypto"
  | "politics"
  | "sports"
  | "finance"
  | "entertainment"
  | "geopolitics"
  | "tech"
  | "science"
  | "other"

export interface PolymarketEventsResponse {
  events: PolymarketEvent[]
  count: number
  categories: PolymarketCategory[]
  categories_zh: Record<PolymarketCategory, string>
}

export interface PolymarketOrderbookData {
  market: string
  asset_id: string
  bids: { price: string; size: string }[]
  asks: { price: string; size: string }[]
  last_trade_price: string
  tick_size: string
  min_order_size: string
}

export async function getPolymarketEvents(
  limit = 20,
  active = true,
  category = ""
): Promise<ApiResponse<PolymarketEventsResponse>> {
  const qs = new URLSearchParams({ limit: String(limit), active: String(active) })
  if (category) qs.set("category", category)
  return request(`/api/v1/polymarket/events?${qs}`)
}

export async function getPolymarketEvent(
  eventId: string
): Promise<ApiResponse<PolymarketEvent>> {
  return request(`/api/v1/polymarket/events/${encodeURIComponent(eventId)}`)
}

export async function getPolymarketOrderbook(
  tokenId: string
): Promise<ApiResponse<PolymarketOrderbookData>> {
  return request(`/api/v1/polymarket/orderbook/${encodeURIComponent(tokenId)}`)
}

export async function getPolymarketPrice(
  tokenId: string,
  side: "BUY" | "SELL" = "BUY"
): Promise<ApiResponse<{ token_id: string; price: number; midpoint: number; side: string }>> {
  return request(`/api/v1/polymarket/price/${encodeURIComponent(tokenId)}?side=${side}`)
}

// Crypto predictions (BTC/ETH 5m/15m/1h/daily rolling markets)

export interface CryptoPrediction {
  id: string
  title: string
  title_zh: string
  slug: string
  asset: string
  asset_zh: string
  timeframe: string
  timeframe_label: { en: string; zh: string }
  active: boolean
  closed: boolean
  start_date: string
  end_date: string
  volume: number
  volume_24h: number
  liquidity: number
  outcomes: PolymarketOutcome[]
  polymarket_url: string
}

export interface CryptoPredictionsResponse {
  predictions: CryptoPrediction[]
  by_asset: Record<string, CryptoPrediction[]>
  by_timeframe: Record<string, CryptoPrediction[]>
  count: number
  available_assets: string[]
  timeframe_labels: Record<string, { en: string; zh: string }>
}

export async function getPolymarketCryptoPredictions(
  limit = 30,
  asset = "",
  timeframe = ""
): Promise<ApiResponse<CryptoPredictionsResponse>> {
  const qs = new URLSearchParams({ limit: String(limit) })
  if (asset) qs.set("asset", asset)
  if (timeframe) qs.set("timeframe", timeframe)
  return request(`/api/v1/polymarket/crypto-predictions?${qs}`)
}

// ---------------------------------------------------------------------------
// Chat Sessions (conversation persistence)
// ---------------------------------------------------------------------------

export interface ChatSession {
  id: string
  strategy_id: string | null
  title: string
  message_count?: number
  created_at: string
  updated_at: string
}

export interface ChatMessageRecord {
  id: string
  session_id: string
  role: "user" | "assistant"
  content: string
  extra: Record<string, unknown>
  created_at: string
}

export async function createChatSession(
  strategyId?: string,
  title?: string,
): Promise<ApiResponse<ChatSession>> {
  return request("/api/v1/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ strategy_id: strategyId ?? null, title: title ?? "" }),
  })
}

export async function listChatSessions(
  strategyId?: string,
  limit = 50,
): Promise<ApiResponse<ChatSession[]>> {
  const qs = new URLSearchParams({ limit: String(limit) })
  if (strategyId) qs.set("strategy_id", strategyId)
  return request(`/api/v1/chat/sessions?${qs}`)
}

export async function getChatSessionMessages(
  sessionId: string,
  limit = 200,
): Promise<ApiResponse<ChatMessageRecord[]>> {
  return request(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages?limit=${limit}`)
}

export async function saveChatSessionMessages(
  sessionId: string,
  messages: Array<{ id: string; role: string; content: string; extra?: unknown }>,
): Promise<ApiResponse<{ status: string }>> {
  return request(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: "PUT",
    body: JSON.stringify({ messages }),
  })
}

export async function deleteChatSession(
  sessionId: string,
): Promise<ApiResponse<{ status: string }>> {
  return request(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  })
}

export async function updateChatSessionTitle(
  sessionId: string,
  title: string,
): Promise<ApiResponse<{ status: string }>> {
  return request(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  })
}

// --------------- Runner Status ---------------

export interface RunnerSlotStatus {
  deployment_id: string
  strategy_id: string
  account_id: string
  symbol: string
  interval: string
  position: string
  bar_count: number
  signals_emitted: number
  orders_placed: number
  errors: number
  last_signal_ts: number
  recent_signals: Array<{
    ts: number
    side: string
    reason: string
    strength?: number | null
    price: number
    symbol: string
  }>
}

export interface RunnerStatusData {
  running: boolean
  deployment_count: number
  deployments: RunnerSlotStatus[]
}

export async function getRunnerStatus(): Promise<ApiResponse<RunnerStatusData>> {
  return request("/api/v1/strategies/runner/status")
}

export interface DeploymentSignalsData {
  deployment_id: string
  signals: Array<{
    ts: number
    side: string
    reason: string
    strength?: number | null
    price: number
    symbol: string
  }>
  total: number
  status: RunnerSlotStatus | null
}

export async function getDeploymentSignals(
  deploymentId: string,
): Promise<ApiResponse<DeploymentSignalsData>> {
  return request(`/api/v1/strategies/runner/${encodeURIComponent(deploymentId)}/signals`)
}
