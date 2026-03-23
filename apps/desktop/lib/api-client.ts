const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

interface ApiResponse<T> {
  data: T | null
  error: string | null
}

async function request<T>(path: string, init?: RequestInit): Promise<ApiResponse<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...init?.headers },
      ...init,
    })
    if (!res.ok) {
      const body = await res.text()
      return { data: null, error: `HTTP ${res.status}: ${body}` }
    }
    const json = await res.json()
    return { data: (json.data ?? json) as T, error: null }
  } catch (e) {
    return { data: null, error: e instanceof Error ? e.message : "Unknown error" }
  }
}

export interface TickerData {
  symbol: string
  price: number
  change_24h: number
  volume_24h: number
  high_24h: number
  low_24h: number
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
  bids: [number, number][]
  asks: [number, number][]
}

export interface StrategyData {
  id: string
  name: string
  symbol: string
  interval: string
  created_at: string
}

export interface BacktestData {
  id: string
  strategy_id: string
  strategy_name: string
  status: string
  total_return: number
  sharpe_ratio: number
  max_drawdown: number
  win_rate: number
  profit_factor: number
  total_trades: number
  created_at: string
}

export interface PaperAccountData {
  id: string
  name: string
  balance: number
  equity: number
  unrealized_pnl: number
  realized_pnl: number
  created_at: string
}

export interface PaperPositionData {
  symbol: string
  side: string
  quantity: number
  entry_price: number
  current_price: number
  unrealized_pnl: number
}

export interface PaperOrderData {
  id: string
  symbol: string
  side: string
  type: string
  quantity: number
  price: number | null
  status: string
  created_at: string
}

export async function checkHealth(): Promise<ApiResponse<{ status: string }>> {
  return request("/api/v1/health")
}

export async function getMarkets(): Promise<ApiResponse<string[]>> {
  return request("/api/v1/markets")
}

export async function getTicker(symbol: string): Promise<ApiResponse<TickerData>> {
  return request(`/api/v1/markets/${encodeURIComponent(symbol)}/ticker`)
}

export async function getKlines(
  symbol: string,
  interval = "1h",
  limit = 100
): Promise<ApiResponse<KlineData[]>> {
  return request(`/api/v1/markets/${encodeURIComponent(symbol)}/kline?interval=${interval}&limit=${limit}`)
}

export async function getOrderbook(
  symbol: string,
  depth = 10
): Promise<ApiResponse<OrderbookData>> {
  return request(`/api/v1/markets/${encodeURIComponent(symbol)}/orderbook?depth=${depth}`)
}

export async function getStrategies(): Promise<ApiResponse<StrategyData[]>> {
  return request("/api/v1/strategies")
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

export async function getBacktests(): Promise<ApiResponse<BacktestData[]>> {
  return request("/api/v1/backtests")
}

export async function getBacktest(id: string): Promise<ApiResponse<BacktestData>> {
  return request(`/api/v1/backtests/${id}`)
}

export async function runBacktest(params: {
  strategy_id: string
  data_path?: string
  initial_capital?: number
  commission_rate?: number
}): Promise<ApiResponse<{ task_id: string }>> {
  return request("/api/v1/backtests", {
    method: "POST",
    body: JSON.stringify(params),
  })
}

export async function getPaperAccounts(): Promise<ApiResponse<PaperAccountData[]>> {
  return request("/api/v1/paper/accounts")
}

export async function createPaperAccount(params: {
  name: string
  balance: number
}): Promise<ApiResponse<PaperAccountData>> {
  return request("/api/v1/paper/accounts", {
    method: "POST",
    body: JSON.stringify(params),
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
}): Promise<ApiResponse<PaperOrderData>> {
  return request("/api/v1/paper/orders", {
    method: "POST",
    body: JSON.stringify(params),
  })
}

// ---------------------------------------------------------------------------
// Trading API (unified — works for both paper and live modes)
// ---------------------------------------------------------------------------

export interface TradingOrder {
  id: string
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
  exchange: string
  asset: string
  free: number
  locked: number
  timestamp: number
}

export interface TradingFill {
  id: string
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

export async function sendAgentChat(
  message: string,
  onEvent: (event: { type: string; data: string }) => void
): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/agent/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    })
    if (!res.ok || !res.body) return

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split("\n")
      buffer = lines.pop() || ""

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6)
          if (data === "[DONE]") return
          try {
            onEvent(JSON.parse(data))
          } catch {
            onEvent({ type: "text", data })
          }
        }
      }
    }
  } catch {
    onEvent({ type: "error", data: "Connection failed" })
  }
}
