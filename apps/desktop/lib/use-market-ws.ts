"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import type { TickerData, KlineData, OrderbookData, ExchangeProvider, MarketType } from "./api-client"

const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL ||
  (process.env.NODE_ENV === "development"
    ? "ws://127.0.0.1:8080"
    : typeof window !== "undefined"
      ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`
      : "ws://localhost:8080")

const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000
const STALE_AFTER_MS = 5000
const UNSUB_DELAY_MS = 5000

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
  interval?: string
}

function extractSequence(msg: unknown): number | null {
  if (!msg || typeof msg !== "object") return null
  const m = msg as Record<string, unknown>
  const d = (m.data && typeof m.data === "object") ? (m.data as Record<string, unknown>) : null
  const raw = m.seq ?? m.sequence ?? d?.seq ?? d?.sequence ?? d?.update_id ?? d?.u
  const seq = typeof raw === "string" ? Number(raw) : raw
  return typeof seq === "number" && Number.isFinite(seq) ? seq : null
}

export function useMarketWS({ symbol, exchange, marketType, interval }: UseMarketWSOptions): MarketWSState {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptRef = useRef(0)
  const intentionalCloseRef = useRef(false)
  const subRef = useRef({ symbol, exchange, marketType })
  const intervalRef = useRef(interval || "1h")
  const lastSeqRef = useRef<number | null>(null)

  // --- RAF throttle buffers for high-frequency data ---
  const pendingTickerRef = useRef<TickerData | null>(null)
  const pendingOrderbookRef = useRef<OrderbookData | null>(null)
  const pendingKlineRef = useRef<WSKlineData | null>(null)
  const rafIdRef = useRef<number | null>(null)

  // --- Delayed unsubscribe ---
  const pendingUnsubRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Keep intervalRef in sync without triggering reconnects
  useEffect(() => { intervalRef.current = interval || "1h" }, [interval])

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

  // Flush all pending RAF updates in a single setState call
  const flushRAF = useCallback(() => {
    rafIdRef.current = null
    const ticker = pendingTickerRef.current
    const orderbook = pendingOrderbookRef.current
    const kline = pendingKlineRef.current
    pendingTickerRef.current = null
    pendingOrderbookRef.current = null
    pendingKlineRef.current = null

    if (!ticker && !orderbook && !kline) return

    const now = Date.now()
    setState((prev) => {
      let next = { ...prev, lastMessageAt: now, stale: false, streamState: "live" as StreamState }
      if (ticker) next.ticker = ticker
      if (orderbook) next.orderbook = orderbook
      if (kline) {
        const arr = [...next.klines]
        if (arr.length > 0 && arr[arr.length - 1].timestamp === kline.timestamp) {
          arr[arr.length - 1] = kline
        } else {
          arr.push(kline)
          if (arr.length > 500) arr.shift()
        }
        next.klines = arr
      }
      return next
    })
  }, [])

  const scheduleRAF = useCallback(() => {
    if (rafIdRef.current === null) {
      rafIdRef.current = requestAnimationFrame(flushRAF)
    }
  }, [flushRAF])

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
          pendingTickerRef.current = {
            symbol: d.symbol,
            last_price: d.last_price,
            change_24h_pct: d.change_24h_pct ?? 0,
            volume_24h: d.volume_24h ?? 0,
            quote_volume_24h: d.quote_volume_24h,
            high_24h: d.high_24h,
            low_24h: d.low_24h,
            bid: d.bid,
            ask: d.ask,
          }
          scheduleRAF()
        } else if (msg.type === "kline") {
          const d = msg.data
          const klineInterval = d.interval
          if (klineInterval && klineInterval !== intervalRef.current) return
          pendingKlineRef.current = {
            timestamp: d.timestamp,
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close,
            volume: d.volume,
            wsInterval: klineInterval,
          }
          scheduleRAF()
        } else if (msg.type === "kline_snapshot") {
          const snapshotInterval = msg.interval
          if (snapshotInterval && snapshotInterval !== intervalRef.current) return
          const snapshotData: WSKlineData[] = (msg.data || []).map((d: any) => ({
            timestamp: d.timestamp,
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close,
            volume: d.volume,
            wsInterval: d.interval || snapshotInterval,
          }))
          if (snapshotData.length > 0) {
            const now = Date.now()
            setState((prev) => ({
              ...prev,
              klines: snapshotData,
              lastMessageAt: now,
              stale: false,
              streamState: "live",
            }))
          }
        } else if (msg.type === "depth") {
          const d = msg.data
          pendingOrderbookRef.current = {
            bids: d.bids ?? [],
            asks: d.asks ?? [],
          }
          scheduleRAF()
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
  }, [scheduleRAF, sendSubscribe])

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
      if (pendingUnsubRef.current) clearTimeout(pendingUnsubRef.current)
      if (rafIdRef.current !== null) cancelAnimationFrame(rafIdRef.current)
      wsRef.current?.close()
      wsRef.current = null
      lastSeqRef.current = null
    }
  }, [connect])

  // Delayed unsubscribe: when symbol/exchange/marketType changes,
  // subscribe new immediately but delay old unsubscribe by 5s.
  // If user switches back within 5s, the old sub stays alive (zero cold-start).
  useEffect(() => {
    const prev = subRef.current
    const changed =
      prev.symbol !== symbol || prev.exchange !== exchange || prev.marketType !== marketType

    if (changed) {
      const ws = wsRef.current
      if (ws && ws.readyState === WebSocket.OPEN) {
        sendSubscribe(ws, symbol, exchange, marketType)

        // Cancel any pending unsub for the NEW target (user switched back)
        if (pendingUnsubRef.current) {
          clearTimeout(pendingUnsubRef.current)
          pendingUnsubRef.current = null
        }

        // Schedule delayed unsub for the OLD target
        const oldSym = prev.symbol
        const oldEx = prev.exchange
        const oldMt = prev.marketType
        pendingUnsubRef.current = setTimeout(() => {
          const currentWs = wsRef.current
          if (currentWs && currentWs.readyState === WebSocket.OPEN) {
            sendUnsubscribe(currentWs, oldSym, oldEx, oldMt)
          }
          pendingUnsubRef.current = null
        }, UNSUB_DELAY_MS)
      }
      subRef.current = { symbol, exchange, marketType }
      lastSeqRef.current = null
      resetData()
    }
  }, [symbol, exchange, marketType, sendSubscribe, sendUnsubscribe, resetData])

  return state
}
