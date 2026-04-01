"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import type { TickerData, KlineData, OrderbookData, ExchangeProvider, MarketType } from "./api-client"

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || (typeof window !== "undefined" ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}` : "ws://localhost:8080")

const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000
const STALE_AFTER_MS = 5000

type StreamState = "live" | "degraded" | "recovering"

export interface WSKlineData extends KlineData {
  wsInterval?: string
}

export interface MarketWSState {
  connected: boolean
  ticker: TickerData | null
  klines: WSKlineData[]
  orderbook: OrderbookData | null
  lastMessageAt: number | null
  stale: boolean
  streamState: StreamState
}

interface UseMarketWSOptions {
  symbol: string
  exchange: ExchangeProvider
  marketType: MarketType
}

function extractSequence(msg: unknown): number | null {
  if (!msg || typeof msg !== "object") return null
  const m = msg as Record<string, unknown>
  const d = (m.data && typeof m.data === "object") ? (m.data as Record<string, unknown>) : null
  const raw = m.seq ?? m.sequence ?? d?.seq ?? d?.sequence ?? d?.update_id ?? d?.u
  const seq = typeof raw === "string" ? Number(raw) : raw
  return typeof seq === "number" && Number.isFinite(seq) ? seq : null
}

export function useMarketWS({ symbol, exchange, marketType }: UseMarketWSOptions): MarketWSState {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptRef = useRef(0)
  const intentionalCloseRef = useRef(false)
  const subRef = useRef({ symbol, exchange, marketType })
  const lastSeqRef = useRef<number | null>(null)

  const [state, setState] = useState<MarketWSState>({
    connected: false,
    ticker: null,
    klines: [],
    orderbook: null,
    lastMessageAt: null,
    stale: true,
    streamState: "recovering",
  })

  const resetData = useCallback(() => {
    setState((s) => ({
      ...s,
      connected: false,
      ticker: null,
      klines: [],
      orderbook: null,
      lastMessageAt: null,
      stale: true,
      streamState: "recovering",
    }))
  }, [])

  const patchLive = useCallback((updater: (s: MarketWSState) => MarketWSState) => {
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

  const sendSubscribe = useCallback((ws: WebSocket, sym: string, ex: string, mt: string) => {
    if (ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({
      action: "subscribe",
      symbols: [sym],
      exchange: ex,
      market_type: mt,
    }))
  }, [])

  const sendUnsubscribe = useCallback((ws: WebSocket, sym: string, ex: string, mt: string) => {
    if (ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({
      action: "unsubscribe",
      symbols: [sym],
      exchange: ex,
      market_type: mt,
    }))
  }, [])

  const connect = useCallback(function connectSocket() {
    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) {
      return
    }

    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
    }

    intentionalCloseRef.current = false
    const ws = new WebSocket(`${WS_BASE}/api/v1/ws/markets`)
    wsRef.current = ws

    ws.onopen = () => {
      attemptRef.current = 0
      lastSeqRef.current = null
      setState((s) => ({ ...s, connected: true, stale: true, streamState: "recovering" }))
      const { symbol: sym, exchange: ex, marketType: mt } = subRef.current
      sendSubscribe(ws, sym, ex, mt)
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

        const evtExchange = msg.data?.exchange
        const evtMarketType = msg.data?.market_type
        const evtSymbol = msg.data?.symbol ?? msg.symbol

        const cur = subRef.current
        if (evtExchange && evtExchange !== cur.exchange) return
        if (evtMarketType && evtMarketType !== cur.marketType) return
        if (evtSymbol && evtSymbol !== cur.symbol) return

        if (msg.type === "ticker") {
          const d = msg.data
          patchLive((s) => ({
            ...s,
            ticker: {
              symbol: d.symbol,
              last_price: d.last_price,
              change_24h_pct: d.change_24h_pct ?? 0,
              volume_24h: d.volume_24h ?? 0,
              quote_volume_24h: d.quote_volume_24h,
              high_24h: d.high_24h,
              low_24h: d.low_24h,
              bid: d.bid,
              ask: d.ask,
            },
          }))
        } else if (msg.type === "kline") {
          const d = msg.data
          const point: WSKlineData = {
            timestamp: d.timestamp,
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close,
            volume: d.volume,
            wsInterval: d.interval,
          }
          patchLive((s) => {
            const arr = [...s.klines]
            if (arr.length > 0 && arr[arr.length - 1].timestamp === point.timestamp) {
              arr[arr.length - 1] = point
            } else {
              arr.push(point)
              if (arr.length > 500) arr.shift()
            }
            return { ...s, klines: arr }
          })
        } else if (msg.type === "depth") {
          const d = msg.data
          patchLive((s) => ({
            ...s,
            orderbook: {
              bids: d.bids ?? [],
              asks: d.asks ?? [],
            },
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
      const delay = Math.min(RECONNECT_BASE_MS * 2 ** attemptRef.current, RECONNECT_MAX_MS)
      attemptRef.current += 1
      reconnectTimer.current = setTimeout(connectSocket, delay)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [patchLive, sendSubscribe])

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

  // Connect on mount, clean up on unmount
  useEffect(() => {
    connect()
    return () => {
      intentionalCloseRef.current = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
      wsRef.current = null
      lastSeqRef.current = null
    }
  }, [connect])

  // When symbol/exchange/marketType changes, switch subscription
  useEffect(() => {
    const prev = subRef.current
    const changed =
      prev.symbol !== symbol || prev.exchange !== exchange || prev.marketType !== marketType

    if (changed) {
      const ws = wsRef.current
      if (ws && ws.readyState === WebSocket.OPEN) {
        sendUnsubscribe(ws, prev.symbol, prev.exchange, prev.marketType)
        sendSubscribe(ws, symbol, exchange, marketType)
      }
      subRef.current = { symbol, exchange, marketType }
      lastSeqRef.current = null
      resetData()
    }
  }, [symbol, exchange, marketType, sendSubscribe, sendUnsubscribe, resetData])

  return state
}
