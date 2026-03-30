"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import useSWR from "swr"
import {
  getKlines,
  type KlineData,
  type ExchangeProvider,
  type MarketType,
} from "../api-client"

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
): Promise<KlineData[]> {
  const source =
    exchange || marketType
      ? { exchange: exchange as ExchangeProvider, market_type: marketType as MarketType }
      : undefined
  const r = await getKlines(symbol, interval, limit, source, endTime)
  if (r.error) throw new Error(r.error)
  if (!r.data) return []
  if (Array.isArray(r.data)) return r.data
  const nested = (r.data as unknown as { klines?: KlineData[] }).klines
  return Array.isArray(nested) ? nested : []
}

/**
 * SWR-backed K-line history hook.
 *
 * Key feature: data is cached per (symbol, interval, exchange, marketType).
 * Switching back to a previously loaded interval returns cached data instantly
 * instead of re-fetching from the API.
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

  const { data, error, isLoading, mutate } = useSWR<KlineData[]>(
    cacheKey,
    async () => dedupAndSort(await fetchKlineData(symbol, interval, 500, exchange, marketType)),
    {
      revalidateOnFocus: false,
      dedupingInterval: 30_000,
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
        await mutate(dedupAndSort([...batch, ...data]), { revalidate: false })
      }
    } finally {
      setIsLoadingMore(false)
    }
  }, [isLoadingMore, noMoreData, data, symbol, interval, exchange, marketType, mutate])

  return {
    klines: data ?? [],
    error: error instanceof Error ? error.message : error ? String(error) : null,
    isLoading,
    isLoadingMore,
    noMoreData,
    loadMore,
  }
}
