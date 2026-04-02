"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { getAccessToken } from "./auth"

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://127.0.0.1:8080"
const RECONNECT_MS = 3000

export interface StrategySignal {
  ts: number
  deployment_id: string
  strategy_id: string
  signal: {
    side: string
    reason: string
    strength?: number | null
  } | string
  order_id: string
  price?: number
  symbol?: string
}

export interface RunnerSlotWS {
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

interface RunnerWSState {
  connected: boolean
  signals: StrategySignal[]
  slotStatus: RunnerSlotWS | null
}

export function useRunnerWS(accountId: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const closingRef = useRef(false)
  const [state, setState] = useState<RunnerWSState>({
    connected: false,
    signals: [],
    slotStatus: null,
  })

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
        if (msg.type === "ping") return

        if (msg.type === "runner_status") {
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
          return
        }

        if (msg.type === "strategy_signal") {
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

          setState((s) => ({
            ...s,
            signals: [sig, ...s.signals].slice(0, 100),
          }))
        }
      } catch {
        // ignore
      }
    }

    ws.onclose = () => {
      setState((s) => ({ ...s, connected: false }))
      wsRef.current = null
      if (closingRef.current) return
      reconnectRef.current = setTimeout(connect, RECONNECT_MS)
    }

    ws.onerror = () => ws.close()
  }, [accountId])

  useEffect(() => {
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

  return { ...state, clearSignals }
}
