"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import type { TradingOrder, TradingPosition, TradingBalance, TradingFill } from "./api-client"

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000"

interface TradingWSState {
  connected: boolean
  orders: TradingOrder[]
  positions: TradingPosition[]
  balances: TradingBalance[]
  fills: TradingFill[]
}

export function useTradingWS() {
  const wsRef = useRef<WebSocket | null>(null)
  const [state, setState] = useState<TradingWSState>({
    connected: false,
    orders: [],
    positions: [],
    balances: [],
    fills: [],
  })

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(`${WS_BASE}/api/v1/ws/trading`)
    wsRef.current = ws

    ws.onopen = () => {
      setState((s) => ({ ...s, connected: true }))
      ws.send(JSON.stringify({
        action: "subscribe",
        channels: ["orders", "positions", "balances"],
      }))
    }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type === "order_update") {
          setState((s) => {
            const order = msg.data as TradingOrder
            const idx = s.orders.findIndex((o) => o.id === order.id)
            const next = [...s.orders]
            if (idx >= 0) next[idx] = order
            else next.unshift(order)
            return { ...s, orders: next }
          })
        } else if (msg.type === "fill") {
          setState((s) => ({
            ...s,
            fills: [msg.data as TradingFill, ...s.fills],
          }))
        } else if (msg.type === "position_update") {
          setState((s) => {
            const pos = msg.data as TradingPosition
            const idx = s.positions.findIndex((p) => p.symbol === pos.symbol)
            const next = [...s.positions]
            if (idx >= 0) next[idx] = pos
            else next.push(pos)
            return { ...s, positions: next.filter((p) => p.quantity > 0) }
          })
        } else if (msg.type === "balance_update") {
          setState((s) => ({
            ...s,
            balances: Array.isArray(msg.data) ? msg.data : [msg.data],
          }))
        }
      } catch {
        // ignore parse errors
      }
    }

    ws.onclose = () => {
      setState((s) => ({ ...s, connected: false }))
      setTimeout(connect, 3000)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
    }
  }, [connect])

  return state
}
