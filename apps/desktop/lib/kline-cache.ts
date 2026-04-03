/**
 * IndexedDB K-line cache — persistent client-side storage.
 *
 * Key schema:  `{exchange}:{marketType}:{symbol}:{interval}`
 * Each entry stores an array of KlineData sorted by timestamp (ascending).
 *
 * Benefits:
 * - Page refresh loads cached data instantly (< 50ms) before API responds
 * - Incremental fetch via `since` param reduces payload 10-100x
 * - Works offline for historical review
 */

import { openDB, type IDBPDatabase } from "idb"
import type { KlineData } from "./api-client"

const DB_NAME = "pnlclaw-klines"
const DB_VERSION = 1
const STORE_NAME = "klines"
const MAX_CANDLES = 2000

function cacheKey(exchange: string, marketType: string, symbol: string, interval: string): string {
  return `${exchange}:${marketType}:${symbol}:${interval}`
}

let dbPromise: Promise<IDBPDatabase> | null = null

function getDB(): Promise<IDBPDatabase> {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME)
        }
      },
    })
  }
  return dbPromise
}

export async function getCachedKlines(
  exchange: string,
  marketType: string,
  symbol: string,
  interval: string,
): Promise<KlineData[]> {
  try {
    const db = await getDB()
    const key = cacheKey(exchange, marketType, symbol, interval)
    const data = await db.get(STORE_NAME, key)
    if (Array.isArray(data)) return data
    return []
  } catch {
    return []
  }
}

export async function putCachedKlines(
  exchange: string,
  marketType: string,
  symbol: string,
  interval: string,
  candles: KlineData[],
): Promise<void> {
  try {
    const db = await getDB()
    const key = cacheKey(exchange, marketType, symbol, interval)
    const existing = (await db.get(STORE_NAME, key)) as KlineData[] | undefined

    let merged: KlineData[]
    if (existing && existing.length > 0) {
      const map = new Map<number, KlineData>()
      for (const k of existing) map.set(k.timestamp, k)
      for (const k of candles) map.set(k.timestamp, k)
      merged = Array.from(map.values()).sort((a, b) => a.timestamp - b.timestamp)
    } else {
      merged = [...candles].sort((a, b) => a.timestamp - b.timestamp)
    }

    if (merged.length > MAX_CANDLES) {
      merged = merged.slice(merged.length - MAX_CANDLES)
    }

    await db.put(STORE_NAME, merged, key)
  } catch {
    // IndexedDB write failure — non-critical
  }
}

export async function getLatestTimestamp(
  exchange: string,
  marketType: string,
  symbol: string,
  interval: string,
): Promise<number | null> {
  const cached = await getCachedKlines(exchange, marketType, symbol, interval)
  if (cached.length === 0) return null
  return cached[cached.length - 1].timestamp
}
