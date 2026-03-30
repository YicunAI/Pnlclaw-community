"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import type { TradingOrder, TradingPosition, TradingBalance, TradingFill } from "./api-client"

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8080"
const RECONNECT_MS = 3000
const STALE_AFTER_MS = 5000

type StreamState = "live" | "degraded" | "recovering"

interface TradingWSState {
  connected: boolean
  orders: TradingOrder[]
  positions: TradingPosition[]
  balances: TradingBalance[]
  fills: TradingFill[]
  lastMessageAt: number | null
  stale: boolean
  streamState: StreamState
}

function extractSequence(msg: unknown): number | null {
  if (!msg || typeof msg !== "object") return null
  const m = msg as Record<string, unknown>
  const d = (m.data && typeof m.data === "object") ? (m.data as Record<string, unknown>) : null
  const raw = m.seq ?? m.sequence ?? d?.seq ?? d?.sequence ?? d?.update_id ?? d?.u
  const seq = typeof raw === "string" ? Number(raw) : raw
  return typeof seq === "number" && Number.isFinite(seq) ? seq : null
}

export function useTradingWS() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const intentionalCloseRef = useRef(false)
  const lastSeqRef = useRef<number | null>(null)
  const [state, setState] = useState<TradingWSState>({
    connected: false,
    orders: [],
    positions: [],
    balances: [],
    fills: [],
    lastMessageAt: null,
    stale: true,
    streamState: "recovering",
  })

  const applyRealtimePatch = useCallback((updater: (s: TradingWSState) => TradingWSState) => {
    const now = Date.now()
    setState((prev) => {
      const next = updater(prev)
      return {
        ...next,
        lastMessageAt: now,
        stale: false,
        streamState: "live",
      }
    })
  }, [])

  const connect = useCallback(function connectSocket() {
    if (
      wsRef.current?.readyState === WebSocket.OPEN ||
      wsRef.current?.readyState === WebSocket.CONNECTING
    ) {
      return
    }

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    intentionalCloseRef.current = false
    const ws = new WebSocket(`${WS_BASE}/api/v1/ws/trading`)
    wsRef.current = ws

    ws.onopen = () => {
      lastSeqRef.current = null
      setState((s) => ({ ...s, connected: true, stale: true, streamState: "recovering" }))
      ws.send(JSON.stringify({
        action: "subscribe",
        channels: ["orders", "positions", "balances"],
      }))
    }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type === "ping") return

        const seq = extractSequence(msg)
        if (seq !== null) {
          const prev = lastSeqRef.current
          if (prev !== null && seq > prev + 1) {
            setState((s) => ({ ...s, stale: true, streamState: "recovering" }))
            ws.close()
            return
          }
          lastSeqRef.current = seq
        }

        if (msg.type === "order_update") {
          applyRealtimePatch((s) => {
            const order = msg.data as TradingOrder
            const idx = s.orders.findIndex((o) => o.id === order.id)
            const next = [...s.orders]
            if (idx >= 0) next[idx] = order
            else next.unshift(order)
            return { ...s, orders: next }
          })
        } else if (msg.type === "fill") {
          applyRealtimePatch((s) => ({
            ...s,
            fills: [msg.data as TradingFill, ...s.fills],
          }))
        } else if (msg.type === "position_update") {
          applyRealtimePatch((s) => {
            const pos = msg.data as TradingPosition
            const idx = s.positions.findIndex((p) => p.symbol === pos.symbol)
            const next = [...s.positions]
            if (idx >= 0) next[idx] = pos
            else next.push(pos)
            return { ...s, positions: next.filter((p) => p.quantity > 0) }
          })
        } else if (msg.type === "balance_update") {
          applyRealtimePatch((s) => ({
            ...s,
            balances: Array.isArray(msg.data) ? msg.data : [msg.data],
          }))
        }
      } catch {
        // ignore parse errors
      }
    }

    ws.onclose = () => {
      setState((s) => ({ ...s, connected: false, stale: true, streamState: "recovering" }))
      wsRef.current = null

      if (intentionalCloseRef.current) return

      reconnectTimerRef.current = setTimeout(() => {
        connectSocket()
      }, RECONNECT_MS)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [applyRealtimePatch])

  useEffect(() => {
    const timer = setInterval(() => {
      setState((s) => {
        if (!s.connected || !s.lastMessageAt) return s
        if (Date.now() - s.lastMessageAt <= STALE_AFTER_MS) return s
        if (s.stale && s.streamState === "degraded") return s
        return { ...s, stale: true, streamState: "degraded" }
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    connect()
    return () => {
      intentionalCloseRef.current = true
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      wsRef.current?.close()
      wsRef.current = null
      lastSeqRef.current = null
    }
  }, [connect])

  return state
}
