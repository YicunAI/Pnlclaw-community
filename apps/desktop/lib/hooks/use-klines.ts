"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import useSWR from "swr"
import {
  getKlines,
  type KlineData,
  type ExchangeProvider,
  type MarketType,
} from "../api-client"
import {
  getCachedKlines,
  putCachedKlines,
  getLatestTimestamp,
} from "../kline-cache"

function dedupAndSort(klines: KlineData[]): KlineData[] {
  const map = new Map<number, KlineData>()
  for (const k of klines) map.set(k.timestamp, k)
  return Array.from(map.values()).sort((a, b) => a.timestamp - b.timestamp)
}

async function fetchKlineData(
  symbol: string,
  interval: string,
  limit: number,
  exchange?: ExchangeProvider,
  marketType?: MarketType,
  endTime?: number,
  since?: number,
): Promise<KlineData[]> {
  const source =
    exchange || marketType
      ? { exchange: exchange as ExchangeProvider, market_type: marketType as MarketType }
      : undefined

  const params = new URLSearchParams()
  params.set("interval", interval)
  params.set("limit", String(limit))
  if (endTime !== undefined) params.set("end_time", String(endTime))
  if (since !== undefined) params.set("since", String(since))

  const r = await getKlines(symbol, interval, limit, source, endTime, since)
  if (r.error) throw new Error(r.error)
  if (!r.data) return []
  if (Array.isArray(r.data)) return r.data
  const nested = (r.data as unknown as { klines?: KlineData[] }).klines
  return Array.isArray(nested) ? nested : []
}

/**
 * Cache-first K-line history hook.
 *
 * Strategy:
 * 1. Read IndexedDB cache instantly (< 50ms)
 * 2. Determine `since` = latest cached timestamp
 * 3. Fetch only incremental data from API (`?since=xxx`)
 * 4. Merge + write back to IndexedDB
 * 5. SWR handles deduplication and stale-while-revalidate
 */
export function useKlineHistory(
  symbol: string,
  interval: string,
  exchange?: ExchangeProvider,
  marketType?: MarketType,
) {
  const cacheKey =
    symbol && interval
      ? ["api:klines", symbol, interval, exchange ?? "", marketType ?? ""]
      : null

  const ex = exchange ?? "binance"
  const mt = marketType ?? "futures"

  const { data, error, isLoading, mutate } = useSWR<KlineData[]>(
    cacheKey,
    async () => {
      // Step 1: Read IndexedDB cache
      const cached = await getCachedKlines(ex, mt, symbol, interval)

      // Step 2: Determine incremental fetch boundary
      let since: number | undefined
      if (cached.length > 0) {
        since = cached[cached.length - 1].timestamp
      }

      // Step 3: Fetch from API (incremental if cache exists)
      let fresh: KlineData[]
      try {
        fresh = await fetchKlineData(
          symbol,
          interval,
          since ? 200 : 500,
          exchange,
          marketType,
          undefined,
          since,
        )
      } catch (e) {
        // API failed but cache is available — return stale data
        if (cached.length > 0) return cached
        throw e
      }

      // Step 4: Merge and persist
      const merged = dedupAndSort([...cached, ...fresh])
      putCachedKlines(ex, mt, symbol, interval, merged).catch(() => {})

      return merged
    },
    {
      revalidateOnFocus: false,
      dedupingInterval: 30_000,
      refreshInterval: (latestData: KlineData[] | undefined) =>
        !latestData || latestData.length === 0 ? 3_000 : 0,
      errorRetryCount: 3,
    },
  )

  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [noMoreData, setNoMoreData] = useState(false)

  const prevKeyStr = useRef(cacheKey?.join("|"))
  useEffect(() => {
    const keyStr = cacheKey?.join("|")
    if (keyStr !== prevKeyStr.current) {
      prevKeyStr.current = keyStr
      setNoMoreData(false)
    }
  }, [cacheKey])

  const loadMore = useCallback(async () => {
    if (isLoadingMore || noMoreData || !data || data.length === 0) return
    setIsLoadingMore(true)
    try {
      const oldestTs = data[0].timestamp
      const batch = await fetchKlineData(
        symbol,
        interval,
        500,
        exchange,
        marketType,
        oldestTs - 1,
      )
      if (batch.length === 0) {
        setNoMoreData(true)
      } else {
        const merged = dedupAndSort([...batch, ...data])
        putCachedKlines(ex, mt, symbol, interval, merged).catch(() => {})
        await mutate(merged, { revalidate: false })
      }
    } finally {
      setIsLoadingMore(false)
    }
  }, [isLoadingMore, noMoreData, data, symbol, interval, exchange, marketType, mutate, ex, mt])

  return {
    klines: data ?? [],
    error: error instanceof Error ? error.message : error ? String(error) : null,
    isLoading,
    isLoadingMore,
    noMoreData,
    loadMore,
  }
}
