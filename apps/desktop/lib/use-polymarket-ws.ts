"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"

const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL ||
  (typeof window !== "undefined" &&
    (window.location.protocol === "tauri:" || window.location.hostname === "tauri.localhost")
    ? "ws://127.0.0.1:8080"
    : process.env.NODE_ENV === "development"
      ? "ws://127.0.0.1:8080"
      : typeof window !== "undefined"
        ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`
        : "ws://localhost:8080")
const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000
const STALE_AFTER_MS = 5000

type StreamState = "live" | "degraded" | "recovering"

export interface PolymarketBookLevel {
  price: string
  size: string
}

export interface PolymarketBookData {
  market: string
  asset_id: string
  bids: PolymarketBookLevel[]
  asks: PolymarketBookLevel[]
  hash: string
  timestamp: string
}

export interface PolymarketPriceData {
  token_id: string
  price: number
}

export interface PolymarketWSState {
  connected: boolean
  books: Record<string, PolymarketBookData>
  prices: Record<string, number>
  lastTrades: Record<string, number>
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

export function usePolymarketWS(tokenIds: string[]): PolymarketWSState {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptRef = useRef(0)
  const subsRef = useRef<string[]>([])
  const intentionalCloseRef = useRef(false)
  const lastSeqRef = useRef<number | null>(null)

  // Stable serialized key to avoid re-renders on identical arrays
  const idsKey = useMemo(() => [...tokenIds].sort().join(","), [tokenIds])
  const stableIds = useMemo(() => tokenIds, [idsKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const [state, setState] = useState<PolymarketWSState>({
    connected: false,
    books: {},
    prices: {},
    lastTrades: {},
    lastMessageAt: null,
    stale: true,
    streamState: "recovering",
  })

  const patchLive = useCallback((updater: (s: PolymarketWSState) => PolymarketWSState) => {
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
    ) return

    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
    }

    intentionalCloseRef.current = false
    const ws = new WebSocket(`${WS_BASE}/api/v1/ws/polymarket`)
    wsRef.current = ws

    ws.onopen = () => {
      attemptRef.current = 0
      lastSeqRef.current = null
      setState((s) => ({ ...s, connected: true, stale: true, streamState: "recovering" }))
      const ids = subsRef.current
      if (ids.length > 0) {
        ws.send(JSON.stringify({ action: "subscribe", token_ids: ids }))
      }
    }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type === "ping" || msg.type === "subscribed" || msg.type === "unsubscribed") return

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

        if (msg.type === "book") {
          const d = msg.data
          const key = d.asset_id || d.market || ""
          if (!key) return

          const rawBids: unknown[] = d.bids || []
          const rawAsks: unknown[] = d.asks || []

          function normalizeLevels(raw: unknown[]): PolymarketBookLevel[] {
            return raw.map((lvl) => {
              if (Array.isArray(lvl)) return { price: String(lvl[0]), size: String(lvl[1] ?? "0") }
              const o = lvl as Record<string, unknown>
              return { price: String(o.price ?? "0"), size: String(o.size ?? "0") }
            })
          }
          const incomingBids = normalizeLevels(rawBids)
          const incomingAsks = normalizeLevels(rawAsks)

          patchLive((s) => {
            const existingBook = s.books[key] || { bids: [], asks: [] }

            // Merge helper: update or remove level based on size
            function mergeLevels(existing: PolymarketBookLevel[], incoming: PolymarketBookLevel[]) {
              const map = new Map<string, string>()
              for (const lvl of existing) map.set(lvl.price, lvl.size)
              for (const lvl of incoming) {
                if (parseFloat(lvl.size) === 0) {
                  map.delete(lvl.price)
                } else {
                  map.set(lvl.price, lvl.size)
                }
              }
              const result: PolymarketBookLevel[] = []
              for (const [price, size] of map.entries()) {
                result.push({ price, size })
              }
              return result
            }

            // Always treat as deltas and merge. If it's a snapshot, the merge will just insert them all.
            const newBids = mergeLevels(existingBook.bids, incomingBids)
            const newAsks = mergeLevels(existingBook.asks, incomingAsks)

            const bidPrices = newBids.map((b) => parseFloat(b.price)).filter((p) => p > 0)
            const askPrices = newAsks.map((a) => parseFloat(a.price)).filter((p) => p > 0)
            const bestBid = bidPrices.length > 0 ? Math.max(...bidPrices) : 0
            const bestAsk = askPrices.length > 0 ? Math.min(...askPrices) : 0
            const midPrice = bestBid > 0 && bestAsk > 0
              ? (bestBid + bestAsk) / 2
              : bestBid > 0 ? bestBid : bestAsk

            return {
              ...s,
              books: {
                ...s.books,
                [key]: {
                  market: d.market || existingBook.market || "",
                  asset_id: d.asset_id || key,
                  bids: newBids,
                  asks: newAsks,
                  hash: d.hash || "",
                  timestamp: d.timestamp || "",
                },
              },
              ...(midPrice > 0 ? { prices: { ...s.prices, [key]: midPrice } } : {}),
            }
          })
        } else if (msg.type === "price_change") {
          const d = msg.data
          const prices: Record<string, number> = {}

          const topId = d.asset_id || ""
          const bestBidPC = parseFloat(d.best_bid || "0")
          const bestAskPC = parseFloat(d.best_ask || "0")
          const topPrice = parseFloat(d.price || "0")

          if (topId) {
            if (bestBidPC > 0 && bestAskPC > 0) {
              prices[topId] = (bestBidPC + bestAskPC) / 2
            } else if (topPrice > 0) {
              prices[topId] = topPrice
            }
          }

          for (const tok of d.price_changes || d.tokens || d.changes || []) {
            if (typeof tok === "object") {
              const tid = tok.asset_id || tok.token_id || ""
              const bb = parseFloat(tok.best_bid || "0")
              const ba = parseFloat(tok.best_ask || "0")
              const p = parseFloat(tok.price || "0")
              if (tid) {
                if (bb > 0 && ba > 0) prices[tid] = (bb + ba) / 2
                else if (p > 0) prices[tid] = p
              }
            }
          }
          if (Object.keys(prices).length > 0) {
            patchLive((s) => ({ ...s, prices: { ...s.prices, ...prices } }))
          }
        } else if (msg.type === "last_trade") {
          const d = msg.data
          const tid = d.asset_id || d.token_id || ""
          const price = parseFloat(d.price || "0")
          if (tid && price > 0) {
            patchLive((s) => ({
              ...s,
              lastTrades: { ...s.lastTrades, [tid]: price },
            }))
          }
        }
      } catch {
        // ignore parse errors
      }
    }

    ws.onclose = () => {
      setState((s) => ({ ...s, connected: false, stale: true, streamState: "recovering" }))
      wsRef.current = null
      if (intentionalCloseRef.current) return
      const delay = Math.min(
        RECONNECT_BASE_MS * 2 ** attemptRef.current,
        RECONNECT_MAX_MS
      )
      attemptRef.current += 1
      reconnectTimer.current = setTimeout(connectSocket, delay)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [patchLive])

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

  // Connect/disconnect when token IDs go from empty <-> non-empty
  const hasIds = stableIds.length > 0
  useEffect(() => {
    if (!hasIds) return
    connect()
    return () => {
      intentionalCloseRef.current = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
      wsRef.current?.close()
      wsRef.current = null
      lastSeqRef.current = null
      setState({
        connected: false,
        books: {},
        prices: {},
        lastTrades: {},
        lastMessageAt: null,
        stale: true,
        streamState: "recovering",
      })
    }
  }, [connect, hasIds])

  // Diff-subscribe when token IDs change
  useEffect(() => {
    const prev = new Set(subsRef.current)
    const next = new Set(stableIds)

    const toSub = stableIds.filter((id) => !prev.has(id))
    const toUnsub = subsRef.current.filter((id) => !next.has(id))

    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      if (toUnsub.length > 0) {
        ws.send(JSON.stringify({ action: "unsubscribe", token_ids: toUnsub }))
      }
      if (toSub.length > 0) {
        ws.send(JSON.stringify({ action: "subscribe", token_ids: toSub }))
      }
    }

    subsRef.current = stableIds
  }, [stableIds])

  return state
}
