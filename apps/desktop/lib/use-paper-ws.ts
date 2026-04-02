"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import type {
  PaperAccountData,
  PaperPositionData,
  PaperOrderData,
  PaperFillData,
  PaperEquityPoint,
} from "./api-client"
import { getAccessToken } from "./auth"

const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL ||
  (process.env.NODE_ENV === "development"
    ? "ws://127.0.0.1:8080"
    : typeof window !== "undefined"
      ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`
      : "ws://localhost:8080")
const RECONNECT_MS = 3000

export interface StrategySignal {
  ts: number
  deployment_id: string
  strategy_id: string
  signal: { side: string; reason: string; strength?: number | null } | string
  order_id: string
  price?: number
  symbol?: string
}

export interface RunnerSlotStatus {
  deployment_id: string
  strategy_id: string
  symbol: string
  interval: string
  position: string
  bar_count: number
  signals_emitted: number
  orders_placed: number
  errors: number
  last_signal_ts: number
}

interface PaperWSState {
  connected: boolean
  account: PaperAccountData | null
  positions: PaperPositionData[]
  orders: PaperOrderData[]
  fills: PaperFillData[]
  equityPoints: PaperEquityPoint[]
  signals: StrategySignal[]
  slotStatus: RunnerSlotStatus | null
  /** Increments on each state-changing WS message so consumers can react. */
  version: number
}

export function usePaperWS(accountId: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const closingRef = useRef(false)
  const accountIdRef = useRef(accountId)
  accountIdRef.current = accountId

  const [state, setState] = useState<PaperWSState>({
    connected: false,
    account: null,
    positions: [],
    orders: [],
    fills: [],
    equityPoints: [],
    signals: [],
    slotStatus: null,
    version: 0,
  })

  const bump = useCallback(
    (updater: (s: PaperWSState) => Partial<PaperWSState>) => {
      setState((prev) => ({ ...prev, ...updater(prev), version: prev.version + 1 }))
    },
    [],
  )

  const connect = useCallback(() => {
    if (!accountId) return
    if (
      wsRef.current?.readyState === WebSocket.OPEN ||
      wsRef.current?.readyState === WebSocket.CONNECTING
    ) return

    if (reconnectRef.current) {
      clearTimeout(reconnectRef.current)
      reconnectRef.current = null
    }

    closingRef.current = false
    const token = getAccessToken()
    const wsUrl = token
      ? `${WS_BASE}/api/v1/ws/paper?token=${encodeURIComponent(token)}`
      : `${WS_BASE}/api/v1/ws/paper`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setState((s) => ({ ...s, connected: true }))
      ws.send(JSON.stringify({ action: "subscribe", account_id: accountId }))
    }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type === "ping" || msg.type === "subscribed" || msg.type === "unsubscribed") return
        if (msg.account_id && msg.account_id !== accountIdRef.current) return

        switch (msg.type) {
          case "fill": {
            const fill = msg.data as PaperFillData
            bump((s) => ({ fills: [fill, ...s.fills] }))
            break
          }
          case "order_update": {
            const order = msg.data as PaperOrderData
            bump((s) => {
              const idx = s.orders.findIndex((o) => o.id === order.id)
              const next = [...s.orders]
              if (idx >= 0) next[idx] = order
              else next.unshift(order)
              return { orders: next }
            })
            break
          }
          case "position_update": {
            const pos = msg.data as PaperPositionData
            bump((s) => {
              const idx = s.positions.findIndex(
                (p) => p.symbol === pos.symbol && (p.pos_side ?? p.side) === (pos.pos_side ?? pos.side),
              )
              const next = [...s.positions]
              if (idx >= 0) next[idx] = pos
              else next.push(pos)
              return { positions: next }
            })
            break
          }
          case "balance_update": {
            bump(() => ({}))
            break
          }
          case "account_snapshot": {
            const snap = msg.data as PaperAccountData & { positions?: PaperPositionData[] }
            bump((s) => {
              const result: Partial<PaperWSState> = { account: snap }
              if (snap.positions) {
                result.positions = snap.positions
              }
              return result
            })
            break
          }
          case "equity_point": {
            const pt = msg.data as PaperEquityPoint
            bump((s) => ({
              equityPoints: [...s.equityPoints, pt].slice(-200),
            }))
            break
          }
          case "runner_status": {
            const d = msg.data ?? {}
            setState((s) => ({
              ...s,
              slotStatus: {
                deployment_id: d.deployment_id ?? "",
                strategy_id: d.strategy_id ?? "",
                symbol: d.symbol ?? "",
                interval: d.interval ?? "",
                position: d.position ?? "flat",
                bar_count: d.bar_count ?? 0,
                signals_emitted: d.signals_emitted ?? 0,
                orders_placed: d.orders_placed ?? 0,
                errors: d.errors ?? 0,
                last_signal_ts: d.last_signal_ts ?? 0,
              },
            }))
            break
          }
          case "strategy_signal": {
            const data = msg.data ?? {}
            const sig: StrategySignal = {
              ts: msg.timestamp ?? Date.now(),
              deployment_id: data.deployment_id ?? "",
              strategy_id: data.strategy_id ?? "",
              signal: data.signal ?? "",
              order_id: data.order_id ?? "",
              price: typeof data.signal === "object" ? data.signal.price : undefined,
              symbol: typeof data.signal === "object" ? data.signal.symbol : undefined,
            }
            bump((s) => ({ signals: [sig, ...s.signals].slice(0, 100) }))
            break
          }
          default:
            break
        }
      } catch {
        // ignore parse errors
      }
    }

    ws.onclose = () => {
      setState((s) => ({ ...s, connected: false }))
      wsRef.current = null
      if (closingRef.current) return
      reconnectRef.current = setTimeout(connect, RECONNECT_MS)
    }

    ws.onerror = () => ws.close()
  }, [accountId, bump])

  useEffect(() => {
    setState({
      connected: false,
      account: null,
      positions: [],
      orders: [],
      fills: [],
      equityPoints: [],
      signals: [],
      slotStatus: null,
      version: 0,
    })
    connect()
    return () => {
      closingRef.current = true
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current)
        reconnectRef.current = null
      }
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect])

  const clearSignals = useCallback(() => {
    setState((s) => ({ ...s, signals: [] }))
  }, [])

  const setEquityHistory = useCallback((points: PaperEquityPoint[]) => {
    setState((s) => ({ ...s, equityPoints: points }))
  }, [])

  return { ...state, clearSignals, setEquityHistory }
}
